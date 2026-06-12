"""
Dual-read OCR consensus validator (Decision 3 — IMPLEMENTED 2026-06 after the 40-file trial).

WHAT THIS IS
------------
The validator is DUAL-READ CONSENSUS, NOT "Flash validates Pro". Every paper is OCR'd
independently by BOTH readers (gemini-3.5-flash primary + gemini-3.1-pro-preview second). A
DETERMINISTIC Python comparator (compare_reads) diffs the two OcrPaperExtraction results,
emits typed flags, and ROUTES the paper to one of four outcomes. It NEVER silently rewrites,
auto-merges, or "corrects" a read — it flags and routes; the human decides. NO LLM runs in
this decision layer (the two reads already happened upstream); this is pure Python.

WHY EACH RULE EXISTS (40-file trial, c:\\tmp\\pau-probe\\trial_batch_1_report.html)
----------------------------------------------------------------------------------
- 24% of papers were full Flash≡Pro agreement; 76% diverged. Divergence was dominated by
  NUMERIC tokens (60% of papers), then question-count (19%), exam_session (12%), exam_year (10%).
- course_code disagreed 0% — BOTH reads consistently leave it null; the code lives in the
  FOLDER PATH, not on the page. So course_code is IGNORED as a divergence signal, and the
  FOLDER-DERIVED code/metadata is carried onto the result as authoritative.
- A hand-curated paper (GST111) showed BOTH reads skipping the SAME question (1,2,4,5) — a
  shared omission "full agreement" cannot catch. Hence full-agreement papers get a sampled
  spot-check (spotcheck_rate), not blind acceptance.
- A network-dropped paper (Test1 A) had only Flash's read of a 30-question exam. A single or
  failed read must NEVER reach the curation queue as "approve" — it goes to QUARANTINE_REOCR.

OUTCOMES
--------
QUARANTINE_REOCR      — read-health failure (missing/errored/one-read-only). Re-OCR, don't curate.
ROUTE_CURATION        — real divergence; human review. curation_tier FULL (any HIGH flag) or LIGHT.
AUTO_ACCEPT_SPOTCHECK — full agreement, deterministically sampled for a human spot-check.
AUTO_ACCEPT           — full agreement, not sampled.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from app.schemas import OcrPaperExtraction


# Primary reader = the curator's editable base in dual-read consensus (Pro still runs as the
# second read). SETTLED to Flash after Hafeedh's eyes-on review of the probe's file-7/8 pages:
# on the only legible head-to-head digit (Ironhide "13kobo per share on application") Flash read
# 13 correctly where Pro-raw misread 11, and Flash is 2-6x faster/cheaper. Revisit if a larger
# run shows Flash drifting — this is a default flip, NOT a redesign; both reads still run.
DEFAULT_PRIMARY_READER = "flash"  # one of {"pro", "flash"}


class FlagType(str, Enum):
    """Taxonomy of dual-read disagreements surfaced to the curation gate."""

    # count of divergent numeric/figure tokens between the two reads (the 60% case).
    NUMERIC_MISMATCH = "numeric_mismatch"
    # paper-level metadata differs: exam_year / exam_session. (course_code is NOT compared.)
    METADATA_MISMATCH = "metadata_mismatch"
    # the two reads extracted a different number of questions (split/structure: 11≠10, 9A-9B).
    QUESTION_COUNT_MISMATCH = "question_count_mismatch"
    # read-health failure: a read is missing/errored while the other exists (or both failed).
    CONTENT_PRESENCE_MISMATCH = "content_presence_mismatch"
    # non-numeric question text differs beyond a trivial threshold (reserved; not yet emitted).
    TEXT_DIVERGENCE = "text_divergence"
    # index-mode: primary read too sparse to index/retrieve (OCR basically failed without erroring).
    NOT_RETRIEVABLE = "not_retrievable"
    # index-mode: no course_code available anywhere (folder path nor either read) -> can't be filed.
    METADATA_MISSING = "metadata_missing"


class FlagSeverity(str, Enum):
    """How strongly a flag gates. HIGH => mandatory full review; LOW => quick-glance tier."""

    HIGH = "high"
    LOW = "low"
    INFO = "info"


class Outcome(str, Enum):
    """Where compare_reads routes a paper. See module header."""

    QUARANTINE_REOCR = "quarantine_reocr"
    ROUTE_CURATION = "route_curation"
    AUTO_ACCEPT_SPOTCHECK = "auto_accept_spotcheck"
    AUTO_ACCEPT = "auto_accept"


class CurationTier(str, Enum):
    """Human-review depth for ROUTE_CURATION papers (none for the auto/quarantine outcomes)."""

    NONE = "none"
    LIGHT = "light"  # only LOW flags — quick glance (numeric 1-2, metadata)
    FULL = "full"    # at least one HIGH flag — mandatory review


@dataclass(frozen=True)
class ConsensusFlag:
    """A single disagreement between the two reads, for the curation UI."""

    type: FlagType
    severity: FlagSeverity
    field: str                # e.g. "exam_year", "questions[].text", "read_health"
    pro_value: object | None    # value from the Pro read (None if absent/errored)
    flash_value: object | None  # value from the Flash read (None if absent/errored)
    detail: str = ""          # human-readable note, e.g. "10 vs 11"


@dataclass
class DualReadResult:
    """Outcome of comparing two reads. Carries both extractions, the routing decision, the
    folder-derived (authoritative) metadata, the typed flags, and a human-readable reason.

    `primary` is the chosen read VERBATIM — NOT an auto-merged or corrected paper. The validator
    never mutates a read; the curator edits from the primary.
    """

    pro: OcrPaperExtraction | None
    flash: OcrPaperExtraction | None
    primary_reader: str            # which read the curator edits ("flash"|"pro")
    outcome: Outcome
    curation_tier: CurationTier
    folder_meta: dict              # authoritative metadata derived from the FOLDER PATH
    reason: str
    flags: list[ConsensusFlag] = field(default_factory=list)

    @property
    def primary(self) -> OcrPaperExtraction | None:
        return self.flash if self.primary_reader == "flash" else self.pro

    @property
    def requires_human(self) -> bool:
        return self.outcome is Outcome.ROUTE_CURATION


# --------------------------------------------------------------------------------------------
# numeric tokenisation
# --------------------------------------------------------------------------------------------
# A number is a digit-run (with optional thousands commas + decimals) optionally trailed by '%'.
# The regex naturally STOPS at a trailing alpha-suffix, so "5marks" -> "5", "10kobo" -> "10",
# "2nd" -> "2" — folding the "5marks"/"5 marks" cosmetic difference. Currency symbols (₦, N, #, $)
# precede the digit and are not captured, so magnitudes are currency-stripped.
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def _canon(tok: str) -> str:
    """Canonical value-form so two spellings of the SAME number collapse: drop thousands commas,
    leading zeros, and trailing-zero decimal noise. '10,000'->'10000', '05'->'5', '5.0'->'5',
    '5.50'->'5.5', '0.2'->'0.2'. Keeps a trailing '%'. Conservative: only folds same-value
    spellings, never different digits."""
    pct = tok.endswith("%")
    body = (tok[:-1] if pct else tok).replace(",", "")
    try:
        if "." in body:
            s = ("%f" % float(body)).rstrip("0").rstrip(".")
        else:
            s = str(int(body))
    except ValueError:
        s = body
    return s + ("%" if pct else "")


def extract_numbers(text: str) -> list[str]:
    """Tokenise the numeric/figure content of `text` into a normalized MULTISET (list).

    Cosmetic noise is folded so it does NOT read as divergence: currency symbols/letters and
    trailing unit words are excluded ('N10,000'->'10000', '5 marks'/'5marks'->'5'), and each
    magnitude is canonicalised to a single value-form ('05'->'5', '5.0'->'5'). A trailing '%' is
    kept ('5%'!='5'). Only same-value spellings collapse — genuinely different digits never fold.
    """
    if not text:
        return []
    return [c for c in (_canon(m.group(0)) for m in _NUM_RE.finditer(text)) if c]


def _q_text(q) -> str:
    return q.text if hasattr(q, "text") else (q.get("text", "") if isinstance(q, dict) else "")


def _q_number(q):
    return q.number if hasattr(q, "number") else (q.get("number") if isinstance(q, dict) else None)


def _paper_number_set(questions) -> set[str]:
    """OLD pooled measure: set of all numeric tokens across the paper. Kept ONLY for the
    side-by-side comparison (pooled symmetric difference over-counts structural + cosmetic noise);
    routing no longer uses it by default."""
    s: set[str] = set()
    for q in questions or []:
        s.update(extract_numbers(_q_text(q)))
    return s


def _q_numbers_by_number(questions) -> dict:
    """Map question.number -> SET of distinct numeric tokens in that question. Distinct, NOT a
    multiset: the count of times a number repeats inside a dense formula/table question is noise,
    not divergence (a multiset measure reported ~25 'divergences' on a paper with ~2 real digit
    differences because repeated 10/2/3 multiplicities differed). Duplicate q-numbers union."""
    out: dict = {}
    for q in questions or []:
        num = _q_number(q)
        out[num] = out.get(num, set()) | set(extract_numbers(_q_text(q)))
    return out


def _aligned_numeric(flash_qs, pro_qs):
    """POSITION-ALIGNED numeric divergence. Align questions by `number`; for questions present in
    BOTH reads, compare their DISTINCT numeric tokens and count divergence WITHIN that question as
    max(|flash-only|, |pro-only|) so a single changed digit ('73'->'78') counts as 1, not 2.
    Questions in only one read are NOT counted here (that is QUESTION_COUNT_MISMATCH's job — no
    double-penalty).

    Returns (total_divergence, flash_only:[(qnum,tok)], pro_only:[(qnum,tok)])."""
    fmap, pmap = _q_numbers_by_number(flash_qs), _q_numbers_by_number(pro_qs)
    total = 0
    flash_only, pro_only = [], []
    for num in set(fmap) & set(pmap):
        fo = sorted(fmap[num] - pmap[num])
        po = sorted(pmap[num] - fmap[num])
        d = max(len(fo), len(po))
        if d:
            total += d
            flash_only += [(num, t) for t in fo]
            pro_only += [(num, t) for t in po]
    return total, flash_only, pro_only


def _pooled_numeric_count(flash_qs, pro_qs) -> int:
    """OLD pooled count: |set symmetric difference| of all numeric tokens. Comparison only."""
    return len(_paper_number_set(flash_qs) ^ _paper_number_set(pro_qs))


def numeric_divergence_counts(flash_result, pro_result) -> dict:
    """Public helper for the replay: returns {'aligned': int, 'pooled': int} for one paper."""
    fq = flash_result.questions if flash_result is not None else []
    pq = pro_result.questions if pro_result is not None else []
    aligned, _, _ = _aligned_numeric(fq, pq)
    return {"aligned": aligned, "pooled": _pooled_numeric_count(fq, pq)}


def _norm_field(v) -> object | None:
    if v is None:
        return None
    s = str(v).strip()
    return s.lower() if s else None


def _read_ok(r: OcrPaperExtraction | None) -> bool:
    """A read is healthy iff it exists AND carries no error field (failed-validation -> None
    upstream; a model 'unreadable' decline sets .error). Empty-but-clean reads are 'ok' here;
    a 0-vs-N question count is caught downstream as a QUESTION_COUNT_MISMATCH."""
    return r is not None and getattr(r, "error", None) in (None, "")


def _why(r: OcrPaperExtraction | None) -> str:
    if r is None:
        return "missing"
    err = getattr(r, "error", None)
    return f"errored({err})" if err else "ok"


def _normalize_meta(folder_meta: dict | None) -> dict:
    fm = dict(folder_meta or {})
    return {
        "course_code": fm.get("course_code"),
        "school": fm.get("school"),
        "dept": fm.get("dept"),
        "level": fm.get("level"),
        "semester": fm.get("semester"),
        "year": fm.get("year"),
    }


def is_spotcheck_selected(paper_sha: str, rate: float) -> bool:
    """Deterministic spot-check selection: hash(sha) % 100 < rate*100. Reproducible across runs
    (not random), so the same paper is always selected-or-not for a given rate."""
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    h = int(hashlib.sha256((paper_sha or "").encode("utf-8")).hexdigest()[:8], 16)
    return (h % 100) < round(rate * 100)


def _content_sha(read: OcrPaperExtraction | None) -> str:
    if read is None:
        return ""
    try:
        return hashlib.sha256(read.model_dump_json().encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(repr(read).encode("utf-8")).hexdigest()


def _spotcheck_rate(override: float | None) -> float:
    if override is not None:
        return override
    from app.config import settings  # lazy: avoid config import at module load
    return settings.spotcheck_rate


# index-mode: below this many chars of primary-read question text, the read is too sparse to be a
# usable search index (OCR effectively failed without erroring). The bar is deliberately LOW —
# one real question sentence clears it; a paper with text is retrievable even if numbers differ.
_INDEX_MIN_QUESTION_CHARS = 40


def _resolve_mode(curation_mode):
    if curation_mode is not None:
        return curation_mode
    from app.config import settings  # lazy: avoid config import at module load
    return settings.curation_mode


def _auto_or_spotcheck(flash_result, pro_result, meta, paper_sha, spotcheck_rate, flags, reason):
    """Shared AUTO_ACCEPT tail: deterministic sampled spot-check as cheap insurance. `flags` may
    carry INFO diagnostics (index-mode numeric/metadata nits) even though nothing gates."""
    rate = _spotcheck_rate(spotcheck_rate)
    sha = paper_sha if paper_sha is not None else _content_sha(
        flash_result if DEFAULT_PRIMARY_READER == "flash" else pro_result)
    if is_spotcheck_selected(sha, rate):
        return DualReadResult(
            pro=pro_result, flash=flash_result, primary_reader=DEFAULT_PRIMARY_READER,
            outcome=Outcome.AUTO_ACCEPT_SPOTCHECK, curation_tier=CurationTier.NONE, folder_meta=meta,
            reason=f"{reason}; sampled for spot-check (rate={rate})", flags=flags)
    return DualReadResult(
        pro=pro_result, flash=flash_result, primary_reader=DEFAULT_PRIMARY_READER,
        outcome=Outcome.AUTO_ACCEPT, curation_tier=CurationTier.NONE, folder_meta=meta,
        reason=f"{reason}; auto-accepted (not sampled)", flags=flags)


def _route_publish(flash_result, pro_result, meta, paper_sha, spotcheck_rate, numeric_mode):
    """OLD text-trust gating: the OCR text was the PUBLISHED artifact, so numeric/structure
    disagreements gated hard. QUESTION_COUNT -> HIGH; NUMERIC aligned 1-2 LOW / 3+ HIGH; metadata
    LOW. any HIGH -> FULL, any LOW -> LIGHT, else AUTO."""
    flags: list[ConsensusFlag] = []
    fq, pq = flash_result.questions, pro_result.questions
    if len(fq) != len(pq):
        flags.append(ConsensusFlag(
            type=FlagType.QUESTION_COUNT_MISMATCH, severity=FlagSeverity.HIGH, field="questions[]",
            pro_value=len(pq), flash_value=len(fq), detail=f"question count {len(fq)} (flash) vs {len(pq)} (pro)"))
    aligned_count, flash_only, pro_only = _aligned_numeric(fq, pq)
    pooled_count = _pooled_numeric_count(fq, pq)
    chosen = pooled_count if numeric_mode == "pooled" else aligned_count
    if chosen > 0:
        sev = FlagSeverity.HIGH if chosen >= 3 else FlagSeverity.LOW
        routed_on = "pooled" if numeric_mode == "pooled" else "aligned"
        flags.append(ConsensusFlag(
            type=FlagType.NUMERIC_MISMATCH, severity=sev, field="questions[].text",
            pro_value=sorted(t for _, t in pro_only), flash_value=sorted(t for _, t in flash_only),
            detail=f"{aligned_count} aligned divergent numeric token(s) [pooled={pooled_count}; routed on {routed_on}]"))
    for fld in ("exam_year", "exam_session"):
        fv, pv = getattr(flash_result, fld), getattr(pro_result, fld)
        if _norm_field(fv) != _norm_field(pv):
            flags.append(ConsensusFlag(
                type=FlagType.METADATA_MISMATCH, severity=FlagSeverity.LOW, field=fld,
                pro_value=pv, flash_value=fv, detail=f"{fv} (flash) vs {pv} (pro)"))
    if flags:
        has_high = any(f.severity is FlagSeverity.HIGH for f in flags)
        tier = CurationTier.FULL if has_high else CurationTier.LIGHT
        reason = ("divergence -> curation [" + tier.value + "]: "
                  + "; ".join(f"{f.type.value}/{f.severity.value}({f.detail})" for f in flags))
        return DualReadResult(
            pro=pro_result, flash=flash_result, primary_reader=DEFAULT_PRIMARY_READER,
            outcome=Outcome.ROUTE_CURATION, curation_tier=tier, folder_meta=meta, reason=reason, flags=flags)
    return _auto_or_spotcheck(flash_result, pro_result, meta, paper_sha, spotcheck_rate, [],
                              "full Flash≡Pro agreement")


def _route_index(flash_result, pro_result, meta, paper_sha, spotcheck_rate):
    """NEW index-mode: OCR is an internal SEARCH INDEX (students get the enhanced IMAGE). Only two
    things matter — can we RETRIEVE this paper, and is it FILED right. Numeric/structure
    disagreements are DIAGNOSTIC (INFO), never human work."""
    fq, pq = flash_result.questions, pro_result.questions
    primary = flash_result if DEFAULT_PRIMARY_READER == "flash" else pro_result

    # 2. RETRIEVABILITY GATE — primary read too sparse to index -> re-OCR (couldn't error, but failed).
    text_chars = sum(len(_q_text(q).strip()) for q in (primary.questions or []))
    if text_chars < _INDEX_MIN_QUESTION_CHARS:
        flag = ConsensusFlag(
            type=FlagType.NOT_RETRIEVABLE, severity=FlagSeverity.HIGH, field="questions[].text",
            pro_value=None, flash_value=None,
            detail=f"primary read has {text_chars} chars of question text (< {_INDEX_MIN_QUESTION_CHARS}) — too sparse to index")
        return DualReadResult(
            pro=pro_result, flash=flash_result, primary_reader=DEFAULT_PRIMARY_READER,
            outcome=Outcome.QUARANTINE_REOCR, curation_tier=CurationTier.NONE, folder_meta=meta,
            reason=f"index: not retrievable ({text_chars} chars of text) -> re-OCR", flags=[flag])

    flags: list[ConsensusFlag] = []
    route_light = False

    # 3a. FILING — course_code comes from the FOLDER PATH. Flag only if it's missing everywhere.
    if not _norm_field(meta.get("course_code")):
        read_code = (_norm_field(getattr(flash_result, "course_code", None))
                     or _norm_field(getattr(pro_result, "course_code", None)))
        if not read_code:
            flags.append(ConsensusFlag(
                type=FlagType.METADATA_MISSING, severity=FlagSeverity.LOW, field="course_code",
                pro_value=getattr(pro_result, "course_code", None),
                flash_value=getattr(flash_result, "course_code", None),
                detail="no course_code in folder path or either read — needs a human to categorise"))
            route_light = True

    # 3b. session / year — filing precision only -> INFO (recorded, never gates: student finds it by course+topic).
    for fld in ("exam_year", "exam_session"):
        fv, pv = getattr(flash_result, fld), getattr(pro_result, fld)
        if _norm_field(fv) != _norm_field(pv):
            flags.append(ConsensusFlag(
                type=FlagType.METADATA_MISMATCH, severity=FlagSeverity.INFO, field=fld,
                pro_value=pv, flash_value=fv, detail=f"{fv} (flash) vs {pv} (pro) — filing precision only"))

    # 4. NUMERIC divergence — DEMOTED to INFO. Recorded for diagnostics; never routes (student reads the image).
    aligned_count, flash_only, pro_only = _aligned_numeric(fq, pq)
    if aligned_count > 0:
        flags.append(ConsensusFlag(
            type=FlagType.NUMERIC_MISMATCH, severity=FlagSeverity.INFO, field="questions[].text",
            pro_value=sorted(t for _, t in pro_only), flash_value=sorted(t for _, t in flash_only),
            detail=f"{aligned_count} aligned numeric token(s) differ — DIAGNOSTIC ONLY (not human work in index mode)"))

    # 5. QUESTION-COUNT — DEMOTED. Small gap -> INFO. A huge gap implies the splitter fused/fragmented
    #    papers (mis-split -> mis-retrievable) -> LIGHT split-integrity review.
    if len(fq) != len(pq):
        a, b = len(fq), len(pq)
        mx, mn = max(a, b), min(a, b)
        severe = (mn <= 1 and mx >= 5) or (mx - mn >= 8)
        sev = FlagSeverity.LOW if severe else FlagSeverity.INFO
        detail = f"count {a} (flash) vs {b} (pro)" + (
            " — SEVERE: likely a mis-split (fused/fragmented) paper" if severe else " — diagnostic only")
        flags.append(ConsensusFlag(
            type=FlagType.QUESTION_COUNT_MISMATCH, severity=sev, field="questions[]",
            pro_value=b, flash_value=a, detail=detail))
        if severe:
            route_light = True

    # ROUTING — only can't-file or severe split-integrity gate (to LIGHT). Everything else is AUTO.
    if route_light:
        why = "; ".join(f.detail for f in flags if f.severity is FlagSeverity.LOW)
        return DualReadResult(
            pro=pro_result, flash=flash_result, primary_reader=DEFAULT_PRIMARY_READER,
            outcome=Outcome.ROUTE_CURATION, curation_tier=CurationTier.LIGHT, folder_meta=meta,
            reason="index: light review -> " + why, flags=flags)
    return _auto_or_spotcheck(flash_result, pro_result, meta, paper_sha, spotcheck_rate, flags,
                              "index: retrievable + filed (numeric/metadata diffs are diagnostic)")


def compare_reads(
    flash_result: OcrPaperExtraction | None,
    pro_result: OcrPaperExtraction | None,
    folder_meta: dict | None,
    paper_sha: str | None = None,
    spotcheck_rate: float | None = None,
    numeric_mode: str = "aligned",
    curation_mode: str | None = None,
) -> DualReadResult:
    """Deterministically compare the two reads and ROUTE the paper. Pure Python: no LLM/I/O/DB.
    Never mutates the reads.

    READ-HEALTH GATE runs first in BOTH modes: a missing/errored/single read -> QUARANTINE_REOCR.

    curation_mode (config default "index"):
      - "index"   : OCR is an internal SEARCH INDEX (students receive the enhanced IMAGE). Gate only
                    on RETRIEVABILITY (enough text to find it) and FILING (course_code available).
                    Numeric & question-count disagreements are DIAGNOSTIC (INFO), not human work.
      - "publish" : OLD text-trust gating (numeric/structure -> curation). Kept for comparison.

    course_code is taken from folder_meta (the page is not a reliable source).
    """
    meta = _normalize_meta(folder_meta)
    mode = _resolve_mode(curation_mode)

    # ---- READ-HEALTH GATE (shared) -------------------------------------------------------
    f_ok, p_ok = _read_ok(flash_result), _read_ok(pro_result)
    if not (f_ok and p_ok):
        detail = f"flash={_why(flash_result)}; pro={_why(pro_result)}"
        flag = ConsensusFlag(
            type=FlagType.CONTENT_PRESENCE_MISMATCH, severity=FlagSeverity.HIGH,
            field="read_health", pro_value=("ok" if p_ok else None),
            flash_value=("ok" if f_ok else None), detail=detail)
        return DualReadResult(
            pro=pro_result, flash=flash_result, primary_reader=DEFAULT_PRIMARY_READER,
            outcome=Outcome.QUARANTINE_REOCR, curation_tier=CurationTier.NONE, folder_meta=meta,
            reason=f"read-health gate: {detail} -> re-OCR (never approve a single/failed read)", flags=[flag])

    if mode == "publish":
        return _route_publish(flash_result, pro_result, meta, paper_sha, spotcheck_rate, numeric_mode)
    return _route_index(flash_result, pro_result, meta, paper_sha, spotcheck_rate)


def dual_read(image_bytes_list: list[bytes]) -> DualReadResult:
    """Orchestrate the two OCR reads then delegate to compare_reads().

    This is the only part that touches the network: OCR `image_bytes_list` through Flash AND Pro
    (both thinking_budget=0, per Decision 1), then call compare_reads() with the folder-derived
    metadata. The trial used a throwaway runner for this; wiring it into the app requires a
    model-parameterised OCR entry point (app.ocr currently hardcodes the Pro call). Out of scope
    for the decision-layer work — kept as a stub. compare_reads() below is the real, tested logic.
    """
    raise NotImplementedError("dual_read (LLM orchestration) is intentionally not wired here; "
                              "compare_reads() is the implemented decision layer.")
