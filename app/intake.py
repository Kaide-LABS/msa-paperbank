import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
import httpx
from app.db import Uploader, ImageBatch, ImageBatchItem, IntakeNotification, PendingPaper, PendingPaperChunk
from app.ports import ObjectStore
from app.schemas import WAMessage, Reply, TextReply
from app.config import settings
from app import whatsapp
from app.preprocess import prepare_images_for_ocr
from app.ocr import ocr_paper
from app.embeddings import embed_many
from app.pdfgen import stitch_images_to_pdf
import logging

log = logging.getLogger(__name__)

def is_whitelisted(session: Session, phone_number: str) -> bool:
    return session.execute(
        select(1).where(Uploader.phone_number == phone_number, Uploader.revoked_at == None).limit(1)
    ).scalar() is not None

def handle_image(
    session: Session,
    http_client: httpx.Client,
    store: ObjectStore,
    msg: WAMessage,
) -> Reply:
    """Backward-compatible WhatsApp entrypoint. Delegates to the channel-neutral
    ``handle_image_inbound`` so callers holding a channel-agnostic envelope (the Phase-2
    ``InboundMessage`` path) do not need WhatsApp wire types."""
    return handle_image_inbound(
        session,
        http_client,
        store,
        phone=msg.from_,
        media_id=msg.image.id,
        message_id=msg.id,
    )


def handle_image_inbound(
    session: Session,
    http_client: httpx.Client,
    store: ObjectStore,
    *,
    phone: str,
    media_id: str,
    message_id: str,
) -> Reply:

    if not is_whitelisted(session, phone):
        log.warning("image_from_non_whitelisted", extra={"wa_from": phone, "phase": "intake"})
        # Outcome will be set in pipeline.py
        return TextReply(body="This number isn't approved to submit photos. Ask Hafeedh to add you.")
        
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    batches_today = session.execute(
        select(func.count(ImageBatch.id))
        .where(ImageBatch.phone_number == phone, ImageBatch.opened_at >= today)
    ).scalar()
    
    if batches_today >= settings.image_intake_max_open_batches_per_phone_per_day:
        return TextReply(body="You've submitted enough today. Try again tomorrow, in shaa Allah.")
        
    now = datetime.now(timezone.utc)
    
    batch = session.execute(
        select(ImageBatch)
        .where(ImageBatch.phone_number == phone, ImageBatch.status == 'open')
        .order_by(ImageBatch.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    
    if not batch or (now - batch.last_item_at.replace(tzinfo=timezone.utc)).total_seconds() > settings.image_batch_seal_seconds:
        batch = ImageBatch(phone_number=phone)
        session.add(batch)
        session.flush()
        
    items_count = session.execute(
        select(func.count(ImageBatchItem.id))
        .where(ImageBatchItem.batch_id == batch.id)
    ).scalar()
    
    if items_count >= settings.ocr_max_images_per_paper:
        # Force seal
        sweep_and_seal_single(session, store, batch.id)
        
        batch = ImageBatch(phone_number=phone)
        session.add(batch)
        session.flush()
        items_count = 0
        reply_prefix = "That batch is full — starting a new one. "
    else:
        reply_prefix = ""
        
    try:
        download_url, mime, size = whatsapp.get_media_metadata(http_client, media_id)
        if size > settings.ocr_max_image_bytes:
            return TextReply(body="That image is too large. Try a smaller photo.")

        pdf_bytes = whatsapp.download_media(http_client, download_url)
        sha = hashlib.sha256(pdf_bytes).hexdigest()

        ext = "jpg" if mime in ["image/jpeg", "image/jpg"] else "png" if mime == "image/png" else "bin"
        key = f"{settings.media_prefix}{message_id}.{ext}"

        store.upload_bytes(key, pdf_bytes, content_type=mime)

        ord_val = items_count + 1
        item = ImageBatchItem(
            batch_id=batch.id,
            wa_media_id=media_id,
            wa_message_id=message_id,
            gcs_object=key,
            mime_type=mime,
            sha256=sha,
            ord=ord_val
        )
        session.add(item)
        batch.last_item_at = now
        session.commit()
        return TextReply(body=f"{reply_prefix}got page {ord_val}")
        
    except Exception as e:
        log.error("handle_image_error", extra={"wa_message_id": message_id, "wa_from": phone, "phase": "intake", "err": str(e)})
        session.rollback()
        # Ensure we don't crash the pipeline, let the IntegrityError or other bubble up if it's dedupe
        raise

def sweep_and_seal_single(session: Session, store: ObjectStore, batch_id: int):
    # This is a helper to force seal one batch inline
    batch = session.execute(
        select(ImageBatch).where(ImageBatch.id == batch_id).with_for_update(skip_locked=True)
    ).scalar_one_or_none()

    if not batch or batch.status != 'open':
        return

    _process_batch(session, store, batch)

def sweep_and_seal(session: Session, store: ObjectStore) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.image_batch_seal_seconds)
    
    candidates = session.execute(
        select(ImageBatch)
        .where(ImageBatch.status == 'open')
        .where(ImageBatch.last_item_at < cutoff)
        .order_by(ImageBatch.id)
        .limit(10)
        .with_for_update(skip_locked=True)
    ).scalars().all()
    
    for batch in candidates:
        try:
            _process_batch(session, store, batch)
        except Exception as e:
            log.exception("sweep_and_seal_batch_failed", extra={"batch_id": batch.id, "phase": "sealer"})
            session.rollback()
            
    return len(candidates)

def _process_batch(session: Session, store: ObjectStore, batch: ImageBatch):
    items = session.execute(
        select(ImageBatchItem).where(ImageBatchItem.batch_id == batch.id).order_by(ImageBatchItem.ord)
    ).scalars().all()
    
    if len(items) == 0:
        batch.status = 'failed'
        batch.failure_reason = 'empty'
        session.commit()
        return
        
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    ocr_done_today = session.execute(
        select(func.count(ImageBatch.id))
        .where(ImageBatch.status == 'ocr_done', ImageBatch.sealed_at >= today)
    ).scalar()
    
    if ocr_done_today >= settings.image_intake_ocr_per_day:
        batch.status = 'deferred_ocr'
        session.commit()
        return
        
    raw_bytes_list = []

    try:
        for item in items:
            b = store.download_bytes(item.gcs_object)
            raw_bytes_list.append(b)

        # Decision 2: preprocessing off by default; raw images go straight to OCR.
        images = prepare_images_for_ocr(raw_bytes_list)

        ocr_result = ocr_paper(images)
        if ocr_result.error or not ocr_result.questions:
            batch.status = 'failed'
            batch.failure_reason = 'ocr_empty'
            session.add(IntakeNotification(
                phone_number=batch.phone_number,
                body="We couldn't read those photos clearly. Try retaking them."
            ))
            session.commit()
            return
            
        vectors = embed_many([q.text for q in ocr_result.questions])
        
        pdf_bytes = stitch_images_to_pdf(images)
        # Use first item sha for the object name suffix
        sha_part = items[0].sha256[:8]
        gcs_object = f"papers/_intake/{batch.id}-{sha_part}.pdf"
        store.upload_bytes(gcs_object, pdf_bytes, content_type="application/pdf")
        
        from app.retrieval import known_courses
        known = known_courses(session)
        proposed_course = (ocr_result.course_code or "UNKNOWN").upper().replace(" ", "")
        
        if proposed_course not in known:
            batch.status = 'failed'
            batch.failure_reason = 'unknown_course'
            session.add(IntakeNotification(
                phone_number=batch.phone_number,
                body="Couldn't tell which course that is — Hafeedh will follow up."
            ))
            session.commit()
            return
            
        year = ocr_result.exam_year or datetime.now(timezone.utc).year
        is_active_risk = (year >= datetime.now(timezone.utc).year - 1)
        
        paper = PendingPaper(
            course_code=proposed_course,
            course_title=ocr_result.course_title,
            semester="rain", # default fallback
            exam_session=ocr_result.exam_session,
            year=year,
            gcs_object=gcs_object,
            sha256=items[0].sha256, # best effort sha
            uploaded_by=batch.phone_number,
            is_active_risk=is_active_risk,
            source='wa_intake',
            pdf_was_generated=True
        )
        session.add(paper)
        session.flush()
        
        for i, (txt, vec) in enumerate(zip([q.text for q in ocr_result.questions], vectors)):
            session.add(PendingPaperChunk(
                pending_paper_id=paper.id,
                chunk_no=i+1,
                text=txt,
                embedding=vec
            ))
            
        batch.pending_paper_id = paper.id
        batch.status = 'ocr_done'
        batch.sealed_at = datetime.now(timezone.utc)
        
        session.add(IntakeNotification(
            phone_number=batch.phone_number,
            body=f"Got {len(items)} pages. Submitted for review — Hafeedh will approve and you'll see it in the bank soon, in shaa Allah."
        ))
        
        session.commit()
        
    except Exception as e:
        log.exception("batch_processing_error", extra={"batch_id": batch.id, "phase": "sealer"})
        batch.status = 'failed'
        batch.failure_reason = 'processing_failed'
        session.commit()
