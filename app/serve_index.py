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
    score: float = 0.0              # fuzzy (pg_trgm) score
    sem: float = 0.0                # semantic (cosine) score, hybrid only — 0 if not scored
    page_count: int = 1             # >1 when this candidate is a grouped multi-page exam

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
        base = f"{head} ({', '.join(meta)})" if meta else head
        if self.page_count > 1:
            base += f" — {self.page_count} pages"
        return base


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


def _grouping_map(session: Session, ids: list[int]) -> dict[int, tuple[int, int]]:
    """page_row_id -> (logical_exam_id, page_count) for candidate ids that belong to a grouped exam."""
    if not ids:
        return {}
    rows = session.execute(text(
        "SELECT page_row_id, logical_exam_id FROM exam_group WHERE page_row_id = ANY(:ids)"
    ), {"ids": ids}).mappings().all()
    if not rows:
        return {}
    lexes = list({r["logical_exam_id"] for r in rows})
    counts = dict(session.execute(text(
        "SELECT logical_exam_id, count(*) FROM exam_group WHERE logical_exam_id = ANY(:lx) GROUP BY 1"
    ), {"lx": lexes}).all())
    return {r["page_row_id"]: (r["logical_exam_id"], int(counts.get(r["logical_exam_id"], 1))) for r in rows}


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

    # Collapse to logical exams (highest-scored representative first; cands is score-sorted).
    # Grouped page-rows (exam_group) collapse by logical_exam_id into ONE multi-page exam candidate
    # — the real grouping supersedes the fragment-dedup hack for these. Ungrouped rows fall back to
    # the (code,title,year,session) near-dup dedup that still cleans up un-grouped duplicate scans.
    gmap = _grouping_map(session, [c.id for c in cands]) if settings.serve_multipage_enabled else {}
    seen_groups, seen_key, deduped = set(), set(), []
    for c in cands:
        g = gmap.get(c.id)
        if g:
            lex, pages = g
            if lex in seen_groups:
                continue
            seen_groups.add(lex)
            c.id = lex                 # representative id = logical_exam_id; served as the whole exam
            c.page_count = pages
            deduped.append(c)
            continue
        key = (c.course_code, (c.course_title or "").lower().strip(), c.year, _norm_session(c.exam_session))
        if key in seen_key:
            continue
        seen_key.add(key)
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

    # ---- L4/L5: decide. The semantic embed (~11s cold) is DEFERRED until we know it can actually
    # change the answer — exact-code and decisively-dominant fuzzy matches skip it entirely. ----
    hyb = settings.serve_hybrid_enabled
    eff_school = None if fellback else scope
    # A3: a result that came from the all-PAU widen (fellback) must NEVER auto-serve.
    force_disambig = fellback and settings.serve_fallback_disambiguate_enabled
    bar, sbar = settings.serve_confident_bar, settings.serve_semantic_bar

    # EXACT code match is decisive and NEVER reads semantic -> resolve here, skipping the embed.
    if exact_hit:
        exact = [c for c in cands if c.score >= 1.0] or cands
        if routed.year:
            yr = [c for c in exact if str(routed.year) in (c.year or "")]
            if yr:
                exact = yr
        if len(exact) == 1 and not force_disambig:
            return SearchResult("serve", exact[0], exact, fellback=fellback, scoped_school=eff_school)
        return SearchResult("disambiguate", None, exact[:settings.serve_max_candidates],
                            fellback=fellback, scoped_school=eff_school)

    # SKIP-EMBED fast path: a near-exact top (score >= skip bar) that dominates the runner-up can't be
    # unseated by the semantic re-rank -> serving it is outcome-identical to the hybrid (verified by a
    # skip-on-vs-off comparison), so don't pay the ~11s embed cold-init. Ambiguous/weak/paraphrase
    # queries do NOT match this and fall through to the embed below (correctness over speed).
    fz_top = cands[0]
    fz_second = cands[1].score if len(cands) > 1 else 0.0
    fuzzy_dominant = (len(cands) == 1) or (fz_top.score - fz_second) >= settings.serve_dominance_gap
    if (hyb and settings.serve_skip_embed_when_dominant and not force_disambig
            and fuzzy_dominant and fz_top.score >= settings.serve_skip_dominant_bar):
        return SearchResult("serve", fz_top, [fz_top], fellback=fellback, scoped_school=eff_school)

    # Not decisive -> NOW embed (the minority of queries where semantic genuinely matters).
    if hyb and cands:
        from app import title_index
        sem = title_index.semantic_scores(session, phrase or user_text, list({c.course_code for c in cands}))
        for c in cands:
            c.sem = sem.get(c.course_code, 0.0)

    f_strong = lambda c: c.score >= bar
    s_strong = lambda c: hyb and c.sem >= sbar
    either = lambda c: f_strong(c) or s_strong(c)            # strong on at least one signal
    if hyb:                                                  # rank by the combined signal
        cands.sort(key=lambda c: -max(c.score, c.sem))
    top = cands[0]
    rank = (lambda c: max(c.score, c.sem)) if hyb else (lambda c: c.score)
    second = rank(cands[1]) if len(cands) > 1 else 0.0
    dominant = len(cands) == 1 or (rank(top) - second) >= settings.serve_dominance_gap

    # A1 clean-miss (generalised): nothing strong on EITHER signal + no clear winner -> honest miss.
    # (Hybrid off -> either() == fuzzy-only, so this is exactly the prior A1 behaviour.)
    if settings.serve_clean_miss_enabled and not dominant and not any(either(c) for c in cands):
        return SearchResult("none", None, [], scoped_school=scope)

    # CONSENSUS: auto-serve ONLY on agreement — top strong on BOTH signals AND a clear winner. A
    # paraphrase that's fuzzy-weak/semantic-strong is OFFERED (signals disagree), never silently served.
    if hyb:
        both_strong = lambda c: f_strong(c) and s_strong(c)
        if dominant and not force_disambig and both_strong(top):
            return SearchResult("serve", top, [top], fellback=fellback, scoped_school=eff_school)
        shortlist = [c for c in cands if either(c)] or cands
        # exactly one viable, agreeing match -> serve it (no pointless 1-item list)
        if len(shortlist) == 1 and not force_disambig and both_strong(shortlist[0]):
            return SearchResult("serve", shortlist[0], shortlist, fellback=fellback, scoped_school=eff_school)
        return SearchResult("disambiguate", None, shortlist[:settings.serve_max_candidates],
                            fellback=fellback, scoped_school=eff_school)
    # hybrid OFF -> prior pure A1/A3 behaviour
    if dominant and not force_disambig:
        return SearchResult("serve", top, [top], fellback=fellback, scoped_school=eff_school)
    return SearchResult("disambiguate", None, cands[:settings.serve_max_candidates],
                        fellback=fellback, scoped_school=eff_school)


def candidate_by_id(session: Session, pending_id: int) -> Candidate | None:
    r = session.execute(text(
        f"SELECT {_SELECT_COLS} FROM pending_papers WHERE id = :id"
    ), {"id": pending_id}).mappings().first()
    return _row_to_candidate(r) if r else None
