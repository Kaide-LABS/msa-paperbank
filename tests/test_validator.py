import pytest
from app.schemas import OcrPaperExtraction, OcrQuestion
from app.validator import (
    compare_reads, extract_numbers, is_spotcheck_selected, numeric_divergence_counts,
    Outcome, CurationTier, FlagType, FlagSeverity, DEFAULT_PRIMARY_READER,
)

# Authoritative folder-derived metadata (the code lives HERE, not on the page).
FM = {"course_code": "ACC201", "school": "SST", "dept": "Accounting",
      "level": "100 level", "semester": "harmattan", "year": "2023-2024"}
FM_NOCODE = {k: (None if k == "course_code" else v) for k, v in FM.items()}

# A long-enough question sentence to clear the index retrievability bar (>=40 chars of text).
LONG = "Explain the doctrine of separation of powers in full detail."


def read(qs=None, year=2023, session="exam", code=None, error=None):
    return OcrPaperExtraction(
        course_code=code, exam_year=year, exam_session=session,
        questions=[OcrQuestion(number=n, text=t) for n, t in (qs or [])], error=error,
    )

def nq(n, base="Define and discuss term"):
    return read([(i, f"{base} number {i} as fully as you can.") for i in range(1, n + 1)])


# ======================= extract_numbers (mode-agnostic) =======================

def test_extract_numbers_normalizes():
    assert extract_numbers("Pay N10,000 at 5% for 2 units.") == ["10000", "5%", "2"]
    assert extract_numbers("price is 2,023. or 0.2") == ["2023", "0.2"]
    assert extract_numbers("") == []

def test_extract_numbers_folds_cosmetic_noise():
    assert extract_numbers("₦5,000 (5 marks)") == ["5000", "5"]
    assert extract_numbers("N5000 5marks") == ["5000", "5"]
    assert extract_numbers("05 and 5.0 and 5.50") == ["5", "5", "5.5"]
    assert extract_numbers("5%") == ["5%"] and extract_numbers("5%") != extract_numbers("5")


# ======================= READ-HEALTH GATE (shared, both modes) =======================

def test_single_read_quarantines():
    r = compare_reads(read([(1, "x")]), None, FM)
    assert r.outcome is Outcome.QUARANTINE_REOCR
    assert r.curation_tier is CurationTier.NONE
    assert any(f.type is FlagType.CONTENT_PRESENCE_MISMATCH for f in r.flags)
    assert "pro=missing" in r.reason

def test_both_reads_fail_quarantines():
    assert compare_reads(None, None, FM).outcome is Outcome.QUARANTINE_REOCR

def test_errored_read_quarantines():
    r = compare_reads(read([], error="image unreadable"), read([(1, "x")]), FM)
    assert r.outcome is Outcome.QUARANTINE_REOCR
    assert "errored" in r.reason

def test_read_health_fail_quarantines_in_index_mode():
    r = compare_reads(read([(1, LONG)]), None, FM, curation_mode="index")
    assert r.outcome is Outcome.QUARANTINE_REOCR  # gate runs first, in index mode too


# ======================= PUBLISH MODE (old text-trust gating) =======================

def test_publish_question_count_mismatch_is_full():
    r = compare_reads(read([(1, "a"), (2, "b")]), read([(1, "a")]), FM, curation_mode="publish")
    assert r.outcome is Outcome.ROUTE_CURATION and r.curation_tier is CurationTier.FULL
    assert any(f.type is FlagType.QUESTION_COUNT_MISMATCH and f.severity is FlagSeverity.HIGH for f in r.flags)

def test_publish_numeric_x1_is_light():
    r = compare_reads(read([(1, "answer 5")]), read([(1, "answer")]), FM, curation_mode="publish")
    assert r.outcome is Outcome.ROUTE_CURATION and r.curation_tier is CurationTier.LIGHT
    nf = [f for f in r.flags if f.type is FlagType.NUMERIC_MISMATCH]
    assert len(nf) == 1 and nf[0].severity is FlagSeverity.LOW

def test_publish_numeric_x12_is_full():
    r = compare_reads(read([(1, "1 2 3 4 5 6")]), read([(1, "7 8 9 10 11 12")]), FM, curation_mode="publish")
    assert r.outcome is Outcome.ROUTE_CURATION and r.curation_tier is CurationTier.FULL
    assert [x for x in r.flags if x.type is FlagType.NUMERIC_MISMATCH][0].severity is FlagSeverity.HIGH

def test_publish_cosmetic_unit_difference_is_zero_divergence():
    f = read([(1, "worth 5 marks")]); p = read([(1, "worth 5marks")])
    r = compare_reads(f, p, FM, curation_mode="publish")
    assert not any(fl.type is FlagType.NUMERIC_MISMATCH for fl in r.flags)
    assert r.outcome in (Outcome.AUTO_ACCEPT, Outcome.AUTO_ACCEPT_SPOTCHECK)
    assert numeric_divergence_counts(f, p)["aligned"] == 0

def test_publish_single_aligned_digit_diff_is_one_light():
    f = read([(1, "intro text"), (2, "the rate is 73")])
    p = read([(1, "intro text"), (2, "the rate is 78")])
    assert numeric_divergence_counts(f, p)["aligned"] == 1
    r = compare_reads(f, p, FM, curation_mode="publish")
    assert r.outcome is Outcome.ROUTE_CURATION and r.curation_tier is CurationTier.LIGHT
    assert [fl for fl in r.flags if fl.type is FlagType.NUMERIC_MISMATCH][0].severity is FlagSeverity.LOW

def test_publish_question_count_numeric_only_over_shared():
    f = read([(1, "rate 73"), (2, "extra 999 888 777")]); p = read([(1, "rate 78")])
    assert numeric_divergence_counts(f, p)["aligned"] == 1
    r = compare_reads(f, p, FM, curation_mode="publish")
    assert any(fl.type is FlagType.QUESTION_COUNT_MISMATCH and fl.severity is FlagSeverity.HIGH for fl in r.flags)
    nf = [fl for fl in r.flags if fl.type is FlagType.NUMERIC_MISMATCH]
    assert len(nf) == 1 and nf[0].severity is FlagSeverity.LOW

def test_publish_pooled_noise_but_per_question_agreement_is_auto():
    f = read([(1, "shared 50"), (2, "flash-only 111")])
    p = read([(1, "shared 50"), (3, "pro-only 222")])
    counts = numeric_divergence_counts(f, p)
    assert counts["pooled"] > 0 and counts["aligned"] == 0
    r = compare_reads(f, p, FM, curation_mode="publish")
    assert not any(fl.type is FlagType.NUMERIC_MISMATCH for fl in r.flags)
    assert r.outcome in (Outcome.AUTO_ACCEPT, Outcome.AUTO_ACCEPT_SPOTCHECK)
    r_old = compare_reads(f, p, FM, numeric_mode="pooled", curation_mode="publish")
    assert any(fl.type is FlagType.NUMERIC_MISMATCH for fl in r_old.flags)

def test_publish_metadata_only_is_light():
    f = read([(1, "same 5")], year=2023); p = read([(1, "same 5")], year=2024)
    r = compare_reads(f, p, FM, curation_mode="publish")
    assert r.outcome is Outcome.ROUTE_CURATION and r.curation_tier is CurationTier.LIGHT
    assert any(f.type is FlagType.METADATA_MISMATCH and f.field == "exam_year" for f in r.flags)
    assert not any(f.severity is FlagSeverity.HIGH for f in r.flags)

def test_publish_course_code_difference_creates_no_flag():
    f = read([(1, "agree 5")], code="ACC201"); p = read([(1, "agree 5")], code="ECO101")
    r = compare_reads(f, p, FM, curation_mode="publish")
    assert all(fl.field != "course_code" for fl in r.flags)
    assert r.outcome in (Outcome.AUTO_ACCEPT, Outcome.AUTO_ACCEPT_SPOTCHECK)
    assert r.folder_meta["course_code"] == "ACC201"

def test_publish_spotcheck_band_is_deterministic():
    rate = 0.15
    sha_in = next(s for s in (f"sha-{i}" for i in range(10000)) if is_spotcheck_selected(s, rate))
    sha_out = next(s for s in (f"sha-{i}" for i in range(10000)) if not is_spotcheck_selected(s, rate))
    f = read([(1, "agree 5")]); p = read([(1, "agree 5")])
    assert compare_reads(f, p, FM, paper_sha=sha_in, spotcheck_rate=rate, curation_mode="publish").outcome is Outcome.AUTO_ACCEPT_SPOTCHECK
    assert compare_reads(f, p, FM, paper_sha=sha_out, spotcheck_rate=rate, curation_mode="publish").outcome is Outcome.AUTO_ACCEPT

def test_primary_extraction_passed_through_unmodified():
    f = read([(1, "price 10")]); p = read([(1, "price 11")])
    f_snapshot = f.model_copy(deep=True)
    r = compare_reads(f, p, FM, curation_mode="publish")
    assert r.primary_reader == DEFAULT_PRIMARY_READER == "flash"
    assert r.primary is f and r.primary == f_snapshot
    assert r.flash is f and r.pro is p


# ======================= INDEX MODE (OCR is a search index) =======================

def test_index_sparse_read_quarantines():
    # near-empty primary read -> can't be indexed -> quarantine (OCR failed without erroring).
    r = compare_reads(read([(1, "?")]), read([(1, "?")]), FM, curation_mode="index")
    assert r.outcome is Outcome.QUARANTINE_REOCR
    assert any(f.type is FlagType.NOT_RETRIEVABLE for f in r.flags)
    assert compare_reads(read([]), read([]), FM, curation_mode="index").outcome is Outcome.QUARANTINE_REOCR

def test_index_numeric_x12_with_text_and_folder_code_is_AUTO():
    # THE HEADLINE CHANGE: 12 divergent numbers, but both reads have real text and folder has the
    # course_code -> AUTO_ACCEPT. (Was FULL under publish.) Student reads the image, not the number.
    f = read([(1, "Calculate each of the following quantities precisely: 1 2 3 4 5 6")])
    p = read([(1, "Calculate each of the following quantities precisely: 7 8 9 10 11 12")])
    c = numeric_divergence_counts(f, p)
    assert c["aligned"] == 6 and c["pooled"] == 12 and c["aligned"] >= 3  # large divergence (HIGH in publish)
    r = compare_reads(f, p, FM, curation_mode="index")
    assert r.outcome in (Outcome.AUTO_ACCEPT, Outcome.AUTO_ACCEPT_SPOTCHECK)
    # numeric IS recorded, but only as INFO diagnostic — it does not gate.
    nf = [x for x in r.flags if x.type is FlagType.NUMERIC_MISMATCH]
    assert len(nf) == 1 and nf[0].severity is FlagSeverity.INFO
    assert not any(x.severity in (FlagSeverity.LOW, FlagSeverity.HIGH) for x in r.flags)

def test_index_missing_course_code_everywhere_is_light():
    # folder lacks course_code AND neither read recovered one -> can't be filed -> LIGHT.
    f = read([(1, LONG)], code=None); p = read([(1, LONG)], code=None)
    r = compare_reads(f, p, FM_NOCODE, curation_mode="index")
    assert r.outcome is Outcome.ROUTE_CURATION and r.curation_tier is CurationTier.LIGHT
    assert any(fl.type is FlagType.METADATA_MISSING for fl in r.flags)

def test_index_course_code_from_read_when_folder_missing_is_AUTO():
    # folder lacks code but a read recovered one -> filable -> AUTO (no human).
    f = read([(1, LONG)], code="ACC201"); p = read([(1, LONG)], code=None)
    r = compare_reads(f, p, FM_NOCODE, curation_mode="index")
    assert r.outcome in (Outcome.AUTO_ACCEPT, Outcome.AUTO_ACCEPT_SPOTCHECK)
    assert not any(fl.type is FlagType.METADATA_MISSING for fl in r.flags)

def test_index_huge_count_gap_is_light_split_integrity():
    # 1 vs 15 -> likely fused/fragmented split -> LIGHT review.
    r = compare_reads(nq(15), read([(1, LONG)]), FM, curation_mode="index")
    assert r.outcome is Outcome.ROUTE_CURATION and r.curation_tier is CurationTier.LIGHT
    qf = [fl for fl in r.flags if fl.type is FlagType.QUESTION_COUNT_MISMATCH][0]
    assert qf.severity is FlagSeverity.LOW and "SEVERE" in qf.detail

def test_index_small_count_gap_is_auto():
    # 10 vs 11 -> not a split problem -> AUTO (recorded INFO only).
    r = compare_reads(nq(10), nq(11), FM, curation_mode="index")
    assert r.outcome in (Outcome.AUTO_ACCEPT, Outcome.AUTO_ACCEPT_SPOTCHECK)
    qf = [fl for fl in r.flags if fl.type is FlagType.QUESTION_COUNT_MISMATCH]
    assert (not qf) or qf[0].severity is FlagSeverity.INFO

def test_index_metadata_session_diff_does_not_gate():
    # exam_session/year disagreement is filing-precision only -> INFO, still AUTO.
    f = read([(1, LONG)], year=2023, session="exam"); p = read([(1, LONG)], year=2024, session="CA1")
    r = compare_reads(f, p, FM, curation_mode="index")
    assert r.outcome in (Outcome.AUTO_ACCEPT, Outcome.AUTO_ACCEPT_SPOTCHECK)
    assert all(fl.severity is not FlagSeverity.LOW for fl in r.flags)

def test_index_slug_filing_is_auto_not_light():
    # A dept+title SLUG as course_code (no official registrar code) is FILABLE -> AUTO, not LIGHT.
    # (A human reading the same path has no more info than the slug already encodes.)
    meta = {"course_code": "FIN-INTRODUCTION-TO-FINANCE", "course_title": "Introduction to Finance",
            "dept": "Finance", "level": "100 level", "semester": "harmattan", "year": "2024-2025"}
    f = read([(1, LONG)]); p = read([(1, LONG)])
    r = compare_reads(f, p, meta, curation_mode="index")
    assert r.outcome in (Outcome.AUTO_ACCEPT, Outcome.AUTO_ACCEPT_SPOTCHECK)
    assert not any(fl.type is FlagType.METADATA_MISSING for fl in r.flags)

def test_index_default_mode_from_config_is_index():
    # No explicit curation_mode -> config default ("index"): numeric x12 with text -> AUTO, not FULL.
    f = read([(1, "Calculate each of the following quantities precisely: 1 2 3 4 5 6")])
    p = read([(1, "Calculate each of the following quantities precisely: 7 8 9 10 11 12")])
    r = compare_reads(f, p, FM)   # mode resolved from settings.curation_mode
    assert r.outcome in (Outcome.AUTO_ACCEPT, Outcome.AUTO_ACCEPT_SPOTCHECK)
