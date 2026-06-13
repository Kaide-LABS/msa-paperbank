# -*- coding: utf-8 -*-
"""V1 retrieval over the corpus-index table (cloud_ingest `pending_papers`).

Layered, best-match-wins matching against `student_visible` rows. RETRIEVAL-ONLY (AI-3 firewall):
find papers, disambiguate, or honestly miss — never tutor/answer.

The index is denormalized and messy on purpose (it IS the product): 322 distinct course_codes,
~half slugs (FIN-INTRODUCTION-TO-FINANCE) or dept_fallback (ACC-L100), year is TEXT ('2023-2024'),
exam_session is free ('exam'/'first'/'second'/'CA1'/...). So we match by, in order:
  L1 EXACT code   -> upper(course_code) == the router's code (hits direct_code/catalog rows)
  L2 FUZZY title  -> pg_trgm similarity on course_title + the slug tail vs the student's phrase
  L3 NARROW       -> soft filter surviving candidates by semester / inferred level
  L4 DISAMBIGUATE -> >1 comparable candidate => numbered list (caller stores it for tap-to-choose)
  L5 MISS         -> nothing above threshold
"""
import re
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings

_CODE_RE = re.compile(r"[A-Z]{2,}\s?\d{2,}")     # a real-looking course code, e.g. GST111 / EEE 321
_LEVEL_RE = re.compile(r"\b([1-6])00\s*(?:level|lvl|l)?\b|\bl\s?([1-6])00\b", re.I)

_SELECT_COLS = ("id, course_code, course_title, dept, school, level, semester, year, "
                "exam_session, gcs_object")


@dataclass
class Candidate:
    id: int
    course_code: str
    course_title: str | None
    dept: str | None
    school: str | None
    level: str | None
    semester: str | None
    year: str | None
    exam_session: str | None
    gcs_object: str
    score: float = 0.0

    def label(self) -> str:
        """One-line human label for a disambiguation list / caption."""
        title = self.course_title or _slug_title(self.course_code)
        head = self.course_code
        if title and title.lower() not in self.course_code.lower():
            head = f"{self.course_code} — {title}"
        meta = []
        if self.level:
            meta.append(self.level if "level" in (self.level or "").lower() else f"{self.level}L")
        if self.year:
            meta.append(str(self.year))
        sess = _norm_session(self.exam_session)
        if sess:
            meta.append(sess)
        return f"{head} ({', '.join(meta)})" if meta else head


@dataclass
class SearchResult:
    kind: str                       # "serve" | "disambiguate" | "none"
    match: Candidate | None
    candidates: list[Candidate]
    fellback: bool = False          # True when school scope found nothing and we widened to all-PAU
    scoped_school: str | None = None


def _norm_session(s: str | None) -> str | None:
    """Real exam sessions are CA1/CA2/exam. OCR leaked the semester words 'first'/'second' into
    exam_session on some rows; treat those (and blanks) as 'no specific session' so page-fragments
    of one paper collapse while genuinely distinct CA1/CA2/exam papers stay separate."""
    s = (s or "").strip().lower()
    return s.upper() if s in ("ca1", "ca2") else ("exam" if s == "exam" else None)


def _slug_title(code: str) -> str:
    """FIN-INTRODUCTION-TO-FINANCE -> 'Introduction To Finance'; ACC-L100 -> 'Acc L100'."""
    if not code:
        return ""
    tail = re.sub(r"^[A-Za-z]+-", "", code)         # strip a single dept prefix
    return tail.replace("-", " ").title()


def _row_to_candidate(r, score: float = 0.0) -> Candidate:
    return Candidate(
        id=r["id"], course_code=r["course_code"], course_title=r["course_title"],
        dept=r["dept"], school=r["school"], level=r["level"], semester=r["semester"],
        year=r["year"], exam_session=r["exam_session"], gcs_object=r["gcs_object"], score=score,
    )


def _infer_level(user_text: str) -> str | None:
    m = _LEVEL_RE.search(user_text or "")
    if not m:
        return None
    return (m.group(1) or m.group(2))               # '1'..'6' (hundreds)


def _collect(session: Session, src: str, code: str, phrase: str, scope: str | None):
    """Run L1 (exact code) + L2 (fuzzy title/slug) optionally scoped to a school. The school is
    matched on the FIRST token of pending_papers.school (raw values are 'SMSS (School of ...)'),
    so a new department under an existing school needs NO code change — its rows already carry the
    school from the ingest folder path. Returns (by_id, exact_hit)."""
    by_id: dict[int, Candidate] = {}
    scope_sql = " AND split_part(school, ' ', 1) = :school" if scope else ""
    base = {"src": src, **({"school": scope} if scope else {})}

    exact_hit = False
    if code and _CODE_RE.search(code):
        rows = session.execute(text(
            f"SELECT {_SELECT_COLS} FROM pending_papers "
            "WHERE student_visible AND source = :src AND upper(course_code) = :code" + scope_sql
        ), {**base, "code": code}).mappings().all()
        for r in rows:
            by_id[r["id"]] = _row_to_candidate(r, score=1.0)
        exact_hit = bool(rows)

    if phrase:
        rows = session.execute(text(
            f"SELECT {_SELECT_COLS}, GREATEST("
            "  COALESCE(similarity(lower(course_title), lower(:phrase)), 0),"
            "  COALESCE(similarity(lower(replace(regexp_replace(course_code, '^[A-Za-z]+-', ''), '-', ' ')),"
            "                      lower(:phrase)), 0)"
            ") AS score "
            "FROM pending_papers WHERE student_visible AND source = :src" + scope_sql + " "
            "ORDER BY score DESC LIMIT :k"
        ), {**base, "phrase": phrase, "k": settings.serve_candidate_k}).mappings().all()
        for r in rows:
            if r["score"] >= settings.serve_fuzzy_threshold:
                if r["id"] in by_id:
                    by_id[r["id"]].score = max(by_id[r["id"]].score, float(r["score"]))
                else:
                    by_id[r["id"]] = _row_to_candidate(r, score=float(r["score"]))
    return by_id, exact_hit


def search_index(session: Session, routed, user_text: str, school: str | None = None) -> SearchResult:
    src = settings.serve_source_tag
    code = (routed.course_code or "").upper().replace(" ", "")
    phrase = (routed.course_phrase or "").strip()
    if not phrase and not _CODE_RE.search((routed.course_code or "").upper()):
        # router gave no clean code and no phrase -> fall back to the raw text as the phrase
        phrase = (user_text or "").strip()

    scope = school if (school and settings.serve_school_scoping_enabled) else None
    by_id, exact_hit = _collect(session, src, code, phrase, scope)
    fellback = False
    if scope and not by_id:               # SOFT fallback: never leave a student empty-handed
        by_id, exact_hit = _collect(session, src, code, phrase, None)
        fellback = bool(by_id)

    cands = sorted(by_id.values(), key=lambda c: -c.score)
    if not cands:
        return SearchResult("none", None, [], scoped_school=scope)

    # Collapse page-fragments / duplicate scans that share the same logical paper, so a
    # disambiguation list shows distinct papers, not near-identical rows. (Multi-page exams are
    # fragmented into per-page rows at ingest — a known V2 cleanup; here we keep one representative,
    # highest-scored first since cands is score-sorted.)
    seen, deduped = set(), []
    for c in cands:
        key = (c.course_code, (c.course_title or "").lower().strip(), c.year, _norm_session(c.exam_session))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    cands = deduped

    # ---- L3: soft narrowing (never empties the set) ----
    if routed.semester:
        narrowed = [c for c in cands if (c.semester or "").lower() == routed.semester]
        if narrowed:
            cands = narrowed
    lvl = _infer_level(user_text)
    if lvl:
        narrowed = [c for c in cands if lvl in (c.level or "")]
        if narrowed:
            cands = narrowed

    # ---- L4/L5: decide ----
    eff_school = None if fellback else scope
    if exact_hit:
        exact = [c for c in cands if c.score >= 1.0] or cands
        if routed.year:
            yr = [c for c in exact if str(routed.year) in (c.year or "")]
            if yr:
                exact = yr
        if len(exact) == 1:
            return SearchResult("serve", exact[0], exact, fellback=fellback, scoped_school=eff_school)
        return SearchResult("disambiguate", None, exact[:settings.serve_max_candidates],
                            fellback=fellback, scoped_school=eff_school)

    top = cands[0]
    if len(cands) == 1 or (top.score - cands[1].score) >= settings.serve_dominance_gap:
        return SearchResult("serve", top, [top], fellback=fellback, scoped_school=eff_school)
    return SearchResult("disambiguate", None, cands[:settings.serve_max_candidates],
                        fellback=fellback, scoped_school=eff_school)


def candidate_by_id(session: Session, pending_id: int) -> Candidate | None:
    r = session.execute(text(
        f"SELECT {_SELECT_COLS} FROM pending_papers WHERE id = :id"
    ), {"id": pending_id}).mappings().first()
    return _row_to_candidate(r) if r else None
