"""
Multi-paper PDF splitter (Decision B, 2026-06 OCR probe).

WHY
---
The probe proved the corpus's multi-page PDFs are NOT single papers — they bundle several
distinct papers scanned back-to-back (e.g. an ACC201 "First Semester CA" and an ACC201
"First Semester Examination" in one file). Reading the whole bundle as one paper produced
false consensus flags: the "5% vs 6% cost of capital" disagreement was two DIFFERENT
sub-papers being read correctly, not an OCR error. So bundles must be split into their
constituent papers BEFORE OCR/consensus.

WHERE
-----
Runs in scripts/drive_import.py's PDF-OCR branch, AFTER rasterization to page images and
prepare_images_for_ocr (preprocess still off by default), BEFORE ocr_paper. Each resulting
PaperGroup is OCR'd on its own. NOT wired into intake.py / admin upload — those are
single-paper WhatsApp/admin flows.

HOW (cheap)
-----------
Boundary detection uses a lightweight per-page Flash probe (app.llm.probe_page_boundary,
thinking_budget=0, tiny schema, small token cap) — NOT a full 4096-token OCR per page.
Assembly is a pure, deterministic Python function (split_pages_into_papers) that partitions
page indices using those flags. Invariant: every input page appears in exactly one output
group — the splitter NEVER discards a page.

BOUNDARY SIGNAL: MASTHEAD ONLY
------------------------------
The split decision uses `is_new_paper_header` (a fresh PAU exam masthead) and NOTHING ELSE.
The real-data diagnostic (c:\\tmp\\pau-probe\\splitter_check.py, on probe files 7 & 8) proved
the masthead signal is reliable and did all the real work: file 8 -> 2 papers (CA|Exam),
file 7 -> 3 papers (CA1|CA2|Exam), both correct, every genuine boundary carrying a masthead.

`has_question_one_reset` was DROPPED from the split decision. The probe showed it is
semantically broken: it returns True on ANY page that begins at "Question 1" — including
every paper's own first page (and page 0) — not on a genuine "restart after higher-numbered
questions." On files 7/8 it caused no damage only because it always coincided with a
masthead. Left in the split decision it is a latent silent-fragmentation risk: a continuation
page showing "Section B / Question 1" would falsely split one real paper into fragments. The
field is still captured on PageBoundaryProbe as an unused diagnostic hint (see schemas.py).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from app.schemas import PageBoundaryProbe
from app.llm import probe_page_boundary


def rasterize_pdf_to_pngs(pdf_bytes: bytes, scale: float = 2.0) -> list[bytes]:
    """Rasterize a PDF to one PNG (bytes) per page using pypdfium2.

    Replaces pdf2image.convert_from_bytes, which needs the poppler BINARY — a container/runtime
    dependency headache. The OCR probe and the 40-file trial both proved pypdfium2 (a self-
    contained wheel, no system binary) renders these scans correctly. scale=2.0 ~= 200 DPI for a
    typical page, matching the trial. This is the rasterizer for the ENTIRE ingest path (local
    drive_import and the cloud job) so it is identical end-to-end.
    """
    import pypdfium2 as pdfium  # local import: keeps module import light for non-PDF callers

    doc = pdfium.PdfDocument(pdf_bytes)
    out: list[bytes] = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            pil = page.render(scale=scale).to_pil()
            if pil.mode != "RGB":
                pil = pil.convert("RGB")
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            out.append(buf.getvalue())
            page.close()
    finally:
        doc.close()
    return out


@dataclass
class PaperGroup:
    """One constituent paper carved out of a bundle: its page-image bytes (in reading order)
    plus the header hints gathered from its first (masthead) page."""

    images: list[bytes]
    page_indices: list[int]
    course_code: str | None = None
    session_hint: str | None = None  # "CA" | "exam" | None, from the header page


def split_pages_into_papers(page_flags: list[PageBoundaryProbe]) -> list[list[int]]:
    """Partition page indices into one-or-more papers from per-page boundary flags. PURE.

    A new paper starts at page i (i > 0) ONLY when that page carries a fresh PAU masthead
    (`is_new_paper_header`). Page 0 always opens the first paper. If no masthead is detected
    anywhere the whole PDF is still treated as a single paper (safe fallback — pages are never
    dropped).

    `has_question_one_reset` is deliberately NOT consulted: the real-data diagnostic showed it
    fires on any page beginning at Question 1 (every paper's first page included), so using it
    here would silently fragment real papers (e.g. a "Section B / Question 1" continuation).
    The masthead signal alone produced the correct partition on both real bundles.

    Returns a list of index-lists that PARTITIONS range(len(page_flags)): every index appears
    in exactly one group, in order, with no duplicates and no gaps.
    """
    n = len(page_flags)
    if n == 0:
        return []

    groups: list[list[int]] = []
    current: list[int] = [0]
    for i in range(1, n):
        f = page_flags[i]
        is_boundary = bool(getattr(f, "is_new_paper_header", False))  # masthead only
        if is_boundary:
            groups.append(current)
            current = [i]
        else:
            current.append(i)
    groups.append(current)
    return groups


def split_pdf_pages(page_images: list[bytes]) -> list[PaperGroup]:
    """Probe each page (cheap Flash boundary call), then deterministically partition into
    PaperGroups. Each group carries its page bytes + the header hints from its first page.

    A single-paper PDF -> exactly one PaperGroup containing every page. Empty input -> [].
    """
    if not page_images:
        return []

    flags = [probe_page_boundary(img) for img in page_images]
    index_groups = split_pages_into_papers(flags)

    groups: list[PaperGroup] = []
    for idxs in index_groups:
        header = flags[idxs[0]]
        groups.append(
            PaperGroup(
                images=[page_images[i] for i in idxs],
                page_indices=list(idxs),
                course_code=getattr(header, "course_code", None),
                session_hint=getattr(header, "session_hint", None),
            )
        )
    return groups
