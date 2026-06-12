import pytest
from app.schemas import PageBoundaryProbe
from app.paper_splitter import split_pages_into_papers, split_pdf_pages, PaperGroup


def hdr(course=None, session=None):
    return PageBoundaryProbe(is_new_paper_header=True, course_code=course, session_hint=session)

def cont():
    return PageBoundaryProbe(is_new_paper_header=False)

def qreset():
    return PageBoundaryProbe(is_new_paper_header=False, has_question_one_reset=True)


# ---- split_pages_into_papers (pure) ----

def test_single_paper_no_header_one_group():
    # No masthead anywhere (even page 0): safe fallback -> the whole PDF is one paper.
    flags = [cont(), cont(), cont()]
    assert split_pages_into_papers(flags) == [[0, 1, 2]]

def test_single_paper_with_header_one_group():
    flags = [hdr("ACC201", "exam"), cont(), cont()]
    assert split_pages_into_papers(flags) == [[0, 1, 2]]

def test_two_paper_bundle_splits_at_header():
    # Fresh masthead on page 0 and again on page 3 -> two papers split at 3.
    flags = [hdr("ACC201", "CA"), cont(), cont(), hdr("ACC201", "exam"), cont()]
    assert split_pages_into_papers(flags) == [[0, 1, 2], [3, 4]]

def test_question_one_reset_alone_does_NOT_split():
    # Masthead-only split: a page with has_question_one_reset=True but is_new_paper_header=False
    # must NOT start a new group — it stays in the current paper. (The reset signal is a broken
    # per-page heuristic; see app.paper_splitter / PageBoundaryProbe. This prevents the latent
    # "Section B / Question 1" continuation page from silently fragmenting a real paper.)
    flags = [hdr("ACC201", "CA"), cont(), qreset(), cont()]
    assert split_pages_into_papers(flags) == [[0, 1, 2, 3]]

def test_partition_invariant():
    flags = [hdr(), cont(), hdr(), qreset(), cont(), hdr(), cont(), cont()]
    groups = split_pages_into_papers(flags)
    flat = [i for g in groups for i in g]
    assert sorted(flat) == list(range(len(flags)))  # every page used
    assert len(flat) == len(set(flat))              # no duplicates
    assert len(flat) == len(flags)                  # no drops

def test_empty_pages_no_groups():
    assert split_pages_into_papers([]) == []


# ---- split_pdf_pages (probe mocked — no network) ----

def test_split_pdf_pages_maps_bytes_and_hints(monkeypatch):
    pages = [b"p0", b"p1", b"p2", b"p3"]
    flags = {
        b"p0": hdr("ACC201", "CA"),
        b"p1": cont(),
        b"p2": hdr("ACC201", "exam"),
        b"p3": cont(),
    }
    import app.paper_splitter as ps
    monkeypatch.setattr(ps, "probe_page_boundary", lambda b: flags[b])

    groups = ps.split_pdf_pages(pages)
    assert len(groups) == 2
    assert isinstance(groups[0], PaperGroup)
    assert groups[0].images == [b"p0", b"p1"]
    assert groups[0].page_indices == [0, 1]
    assert groups[0].course_code == "ACC201"
    assert groups[0].session_hint == "CA"
    assert groups[1].images == [b"p2", b"p3"]
    assert groups[1].session_hint == "exam"
    # partition invariant at the bytes level: every page in exactly one group, in order
    assert [b for g in groups for b in g.images] == pages

def test_split_pdf_pages_single_paper(monkeypatch):
    pages = [b"a", b"b", b"c"]
    import app.paper_splitter as ps
    monkeypatch.setattr(ps, "probe_page_boundary",
                        lambda b: PageBoundaryProbe(is_new_paper_header=(b == b"a")))
    groups = ps.split_pdf_pages(pages)
    assert len(groups) == 1
    assert groups[0].images == pages

def test_split_pdf_pages_empty():
    assert split_pdf_pages([]) == []
