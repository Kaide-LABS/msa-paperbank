import logging
import time
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func
from pgvector.sqlalchemy import Vector
from app.db import Paper, PaperChunk, Course
from app.config import settings
from app.ports import ObjectStore, Embedder
from app.providers import get_embedder
from app.errors import EmbeddingError

log = logging.getLogger(__name__)

# Phase 4 seam: obtain the active embedder via the factory instead of importing
# `app.embeddings` directly, so the provider setting selects the embedder (GCP by
# default — identical behaviour — or the local CPU model). Cached for non-request
# callers; request paths may pass `request.app.state.embedder` explicitly.
_default_embedder: Embedder | None = None


def _get_default_embedder() -> Embedder:
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = get_embedder(settings)
    return _default_embedder


@dataclass
class RetrievalResult:
    """Channel-neutral retrieval outcome. Carries the matched paper (if any) plus the routed
    intent/course so the future tool endpoint (Phase 3) and the handler core share one shape.
    Imports no WhatsApp types."""
    paper: Paper | None
    intent: str
    course_code: str | None = None
    year: int | None = None
    semester: str | None = None
    course_known: bool | None = None

_courses_cache = None
_courses_cache_time = 0

def known_courses(session: Session) -> set[str]:
    global _courses_cache, _courses_cache_time
    now = time.time()
    if _courses_cache is not None and (now - _courses_cache_time) < settings.course_catalog_cache_seconds:
        return _courses_cache

    rows = session.execute(select(Course.code).where(Course.is_active == True)).scalars().all()
    _courses_cache = {c.upper() for c in rows}
    _courses_cache_time = now
    return _courses_cache

def nearest_courses(session: Session, query_code: str, limit: int) -> list[str]:
    stmt = (
        select(Course.code)
        .where(Course.is_active == True)
        .order_by(func.similarity(Course.code, query_code).desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())

def find_paper(session: Session, course_code: str, year: int | None, semester: str | None) -> Paper | None:
    query = select(Paper).where(Paper.course_code.ilike(course_code))
    
    # Phase 3: exclude retired papers
    query = query.where(Paper.is_retired == False)

    # Soft active-risk filter
    query = query.where(
        or_(
            Paper.is_active_risk == False,
            Paper.held_until == None,
            Paper.held_until <= func.current_date()
        )
    )

    if year is not None:
        query = query.where(Paper.year == year)
    if semester is not None:
        query = query.where(Paper.semester.ilike(semester))

    query = query.order_by(Paper.year.desc()).limit(1)
    return session.execute(query).scalar_one_or_none()

def find_paper_by_semantic_query(
    session: Session,
    course_code: str,
    query_text: str,
    top_k: int | None = None,
    prefer_courses: list[str] | None = None,
    embedder: Embedder | None = None,
) -> Paper | None:
    qvec = (embedder or _get_default_embedder()).embed_query(query_text)
    
    limit_k = top_k or settings.semantic_fallback_top_k
    fetch_k = limit_k * 2 if prefer_courses else limit_k

    stmt = (
        select(Paper, PaperChunk.embedding.cosine_distance(qvec).label("distance"))
        .join(PaperChunk, PaperChunk.paper_id == Paper.id)
        .where(Paper.course_code.ilike(course_code))
        .where(Paper.is_retired == False)
        .where(
            or_(
                Paper.is_active_risk == False,
                Paper.held_until == None,
                Paper.held_until <= func.current_date()
            )
        )
        .order_by(text("distance"))
        .limit(fetch_k)
    )
    results = session.execute(stmt).all()
    if not results:
        return None
        
    if not prefer_courses:
        return results[0][0]
        
    best_dist = results[0][1]
    
    for paper, dist in results:
        if paper.course_code in prefer_courses and (dist - best_dist) <= settings.personalization_tie_band:
            return paper
            
    return results[0][0]

def answer_query(
    session: Session,
    query: str,
    *,
    prefer_courses: list[str] | None = None,
) -> RetrievalResult:
    """Channel-neutral retrieval: route a plain text query, apply the course guard, and look up
    the paper (with the semantic fallback), returning a `RetrievalResult`. Composes the existing
    `find_paper` / `find_paper_by_semantic_query` so the future tool endpoint (Phase 3) and the
    channel-neutral handler core can share one callable. Imports no WhatsApp types.

    `llm` is imported lazily so this module stays free of import-time vendor coupling and the
    retrieval helpers remain callable without routing."""
    from app import llm

    routed, _in_tok, _out_tok = llm.route(query)

    if routed.intent != "paper_request":
        return RetrievalResult(paper=None, intent=routed.intent)

    course_code = (routed.course_code or "").upper().replace(" ", "")
    known = known_courses(session)
    if not course_code or course_code not in known:
        return RetrievalResult(
            paper=None, intent="paper_request", course_code=course_code or None,
            year=routed.year, semester=routed.semester, course_known=False,
        )

    paper = find_paper(session, course_code, routed.year, routed.semester)
    if paper is None and routed.confidence >= settings.semantic_fallback_min_router_confidence:
        try:
            paper = find_paper_by_semantic_query(
                session, course_code, query, prefer_courses=prefer_courses
            )
        except EmbeddingError:
            paper = None

    return RetrievalResult(
        paper=paper, intent="paper_request", course_code=course_code,
        year=routed.year, semester=routed.semester, course_known=True,
    )


def render_served_pdf(raw_pdf_bytes: bytes) -> bytes:
    """Transform the stored RAW paper PDF into the human-display version: rasterize each page,
    auto_rotate -> enhance_for_display (greyscale, diagram-safe), re-stitch to a PDF.

    Change A: students receive the IMAGE on retrieval (diagrams), so the SERVED artifact is the
    enhanced one — but the OCR path is untouched (OCR still reads raw upstream) and the GCS raw is
    never modified (this works on the downloaded copy in memory).

    Clean function boundary: this is the one place enhancement happens. Default wiring is
    ON-THE-FLY at serve time (below). To move to ingest-time precompute instead, call this once at
    ingest, store the result alongside raw, and serve the stored copy — a one-line switch.

    Safety: PDFs that already carry a real text layer (digital, ~10% of the corpus) are served
    UNCHANGED — rasterising clean vector text would only degrade it. Any per-page failure falls
    back to that raw page, never dropping content.
    """
    import io
    from pypdf import PdfReader
    from app.paper_splitter import rasterize_pdf_to_pngs
    from app.display_enhance import auto_rotate, enhance_for_display
    from app.pdfgen import stitch_images_to_pdf

    # skip clean digital PDFs (don't rasterise vector text). pypdf (already a dep) reads the first
    # 1-2 pages' text layer; >=200 chars => born-digital, serve raw untouched.
    try:
        reader = PdfReader(io.BytesIO(raw_pdf_bytes))
        txt = (reader.pages[0].extract_text() or "")
        if len(reader.pages) > 1:
            txt += (reader.pages[1].extract_text() or "")
        if len(txt.strip()) >= 200:
            return raw_pdf_bytes
    except Exception:
        pass

    pages = rasterize_pdf_to_pngs(raw_pdf_bytes)
    if not pages:
        return raw_pdf_bytes
    out = []
    for p in pages:
        try:
            out.append(enhance_for_display(auto_rotate(p), color=False))
        except Exception:
            out.append(p)        # any failure -> keep the raw page (never drop content)
    return stitch_images_to_pdf(out)


def load_pdf_bytes(paper: Paper, store: ObjectStore) -> tuple[bytes, str]:
    raw_pdf_bytes = store.download_bytes(paper.gcs_object)   # RAW ground truth — never overwritten
    filename = f"{paper.course_code}_{paper.semester}_{paper.year}.pdf"
    served = render_served_pdf(raw_pdf_bytes) if settings.serve_enhance_enabled else raw_pdf_bytes
    return served, filename


def _image_to_enhanced_png(raw: bytes, ext: str) -> bytes:
    """One image artifact -> enhanced PNG bytes (HEIC decoded first; auto_rotate + enhance_for_display).
    Any failure falls back to the original bytes — never drop content."""
    import io
    img = raw
    if ext in ("heic", "heif"):                      # cv2 can't read HEIC; decode to PNG first
        from pillow_heif import register_heif_opener
        from PIL import Image
        register_heif_opener()
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        buf = io.BytesIO(); im.save(buf, format="PNG"); img = buf.getvalue()
    if settings.serve_enhance_enabled:
        from app.display_enhance import auto_rotate, enhance_for_display
        try:
            img = enhance_for_display(auto_rotate(img), color=False)
        except Exception:
            pass
    return img


def load_served_bytes_v1(session, pending_id: int, store: ObjectStore) -> tuple[bytes, str]:
    """V1 serve loader over the corpus-index `pending_papers`. Returns (served_pdf_bytes, filename).

    V1.2: if `pending_id` is a logical_exam_id in exam_group, assemble ALL its page rows in
    page_order into ONE multi-page PDF (each image enhanced, then stitched). Otherwise serve the
    single row: PDFs -> render_served_pdf (born-digital pass through); images -> enhanced 1-page PDF.
    Raw GCS objects are never modified (all work is on the in-memory copy)."""
    from sqlalchemy import text
    from app.pdfgen import stitch_images_to_pdf

    # --- grouped multi-page exam? ---
    if settings.serve_multipage_enabled:
        grp = session.execute(text(
            "SELECT pp.object_key, pp.course_code FROM exam_group eg "
            "JOIN pending_papers pp ON pp.id = eg.page_row_id "
            "WHERE eg.logical_exam_id = :lex ORDER BY eg.page_order"
        ), {"lex": pending_id}).mappings().all()
        if grp:
            code = grp[0]["course_code"]
            pages = []
            for r in grp:
                praw = store.download_bytes(r["object_key"])
                pext = r["object_key"].rsplit(".", 1)[-1].lower() if "." in r["object_key"] else ""
                pages.append(_image_to_enhanced_png(praw, pext))
            return stitch_images_to_pdf(pages), f"{(code or 'paper').replace('/', '_')}.pdf"

    # --- single row ---
    row = session.execute(
        text("SELECT course_code, object_key FROM pending_papers WHERE id = :id"),
        {"id": pending_id},
    ).mappings().first()
    if row is None:
        raise ValueError(f"pending_paper {pending_id} not found")
    course_code, gcs_object = row["course_code"], row["object_key"]
    raw = store.download_bytes(gcs_object)
    filename = f"{(course_code or 'paper').replace('/', '_')}.pdf"
    ext = gcs_object.rsplit(".", 1)[-1].lower() if "." in gcs_object else ""

    if ext == "pdf":
        served = render_served_pdf(raw) if settings.serve_enhance_enabled else raw
        return served, filename
    return stitch_images_to_pdf([_image_to_enhanced_png(raw, ext)]), filename


def precompute_served_pdf(session, served_id: int, store: ObjectStore) -> tuple[str, str]:
    """Render the served PDF for `served_id` ONCE (reusing the EXACT live render path,
    load_served_bytes_v1) and store it at served/<id>.pdf, recording (served_object, served_filename)
    on the pending_papers row. Idempotent: re-running overwrites the GCS object and the columns.

    `served_id` is whatever the bot serves: a logical_exam_id (grouped multi-page exam) OR a single
    pending_papers.id — both are pending_papers.id values, so the cache lives on that one row.
    The caller commits. Heavy (does the full rasterize/enhance/stitch) -> call OFFLINE or at approval,
    never in the serve request path."""
    from sqlalchemy import text
    pdf_bytes, filename = load_served_bytes_v1(session, served_id, store)
    obj = f"{settings.serve_precompute_prefix}{served_id}.pdf"
    # Some multi-page image exams render to tens of MB -> resumable upload + a generous timeout and a
    # single retry so a slow/flaky link doesn't abort the (one-time) precompute. timeout is per-chunk.
    last_err = None
    for attempt in range(3):
        try:
            store.upload_bytes(obj, pdf_bytes, content_type="application/pdf", timeout=600)
            last_err = None
            break
        except Exception as e:                       # transient write/socket timeout -> retry
            last_err = e
            log.warning("served_upload_retry", extra={"served_id": served_id, "attempt": attempt})
    if last_err is not None:
        raise last_err
    session.execute(
        text("UPDATE pending_papers SET served_object_key = :o, served_filename = :f WHERE id = :id"),
        {"o": obj, "f": filename, "id": served_id},
    )
    return obj, filename


def load_served_cached(session, served_id: int, store: ObjectStore) -> tuple[bytes, str]:
    """Serve-path loader: if a pre-rendered served/ PDF exists for `served_id`, DOWNLOAD it (~0.5s,
    no rasterize) and return it — this is the hardening fast path (kills render latency AND the
    concurrency OOM/SIGABRT risk, since no live render runs). Otherwise FALL BACK to the live render
    (load_served_bytes_v1) so an un-backfilled paper, or one whose precompute failed, never fails to
    serve. Flag serve_precompute_enabled=False forces the legacy always-live-render behaviour."""
    if settings.serve_precompute_enabled:
        from sqlalchemy import text
        try:
            row = session.execute(
                text("SELECT served_object_key, served_filename FROM pending_papers WHERE id = :id"),
                {"id": served_id},
            ).mappings().first()
            if row and row["served_object_key"]:
                data = store.download_bytes(row["served_object_key"])
                return data, (row["served_filename"] or f"paper.pdf")
        except Exception:
            log.warning("served_cache_miss_fallback", extra={"served_id": served_id}, exc_info=True)
    return load_served_bytes_v1(session, served_id, store)
