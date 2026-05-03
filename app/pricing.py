from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone
from app.config import settings
from app.db import RequestLog, ImageBatch, PendingPaper, PaperChunk, PendingPaperChunk

def estimate_request_cost_usd(flash_in: int, flash_out: int) -> float:
    return (flash_in * settings.price_flash_input_per_1m_usd / 1_000_000) + \
           (flash_out * settings.price_flash_output_per_1m_usd / 1_000_000)

def estimate_pro_cost_usd(pro_in: int, pro_out: int) -> float:
    return (pro_in * settings.price_pro_input_per_1m_usd / 1_000_000) + \
           (pro_out * settings.price_pro_output_per_1m_usd / 1_000_000)

def estimate_embedding_cost_usd(emb_tokens: int) -> float:
    return (emb_tokens * settings.price_embedding_per_1m_usd / 1_000_000)

def estimate_daily_spend_usd(session: Session) -> float:
    """Sum the last 24h of activity from request_log + image_batches + pending_papers.
    Returns total estimated $ across all three model classes.
    Uses settings.price_*_per_1m_usd as the per-1M USD rates.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    # 1. Flash costs from RequestLog
    flash_costs = session.execute(
        select(
            func.sum(RequestLog.flash_input_tokens) * settings.price_flash_input_per_1m_usd / 1_000_000 +
            func.sum(RequestLog.flash_output_tokens) * settings.price_flash_output_per_1m_usd / 1_000_000
        ).where(RequestLog.received_at >= cutoff)
    ).scalar() or 0.0

    # 2. Pro costs from ImageBatch (Heuristic: 5660 tokens per 'ocr_done' batch)
    # 4 pages * 1290 in + 500 out = 5160 + 500 = 5660
    # We'll split this as 5160 in, 500 out for better accuracy if prices differ
    pro_batch_count = session.execute(
        select(func.count(ImageBatch.id))
        .where(ImageBatch.status == 'ocr_done', ImageBatch.sealed_at >= cutoff)
    ).scalar() or 0

    # Also count PendingPapers from cli_images or wa_intake
    pro_pending_count = session.execute(
        select(func.count(PendingPaper.id))
        .where(
            PendingPaper.uploaded_at >= cutoff,
            PendingPaper.source.in_(['cli_images', 'wa_intake'])
        )
    ).scalar() or 0
    
    # Avoid double counting if a batch is ocr_done AND has a pending paper (it usually does)
    # But ImageBatch.sealed_at is the trigger for the OCR work.
    total_pro_events = max(pro_batch_count, pro_pending_count)
    pro_costs = total_pro_events * (
        (5160 * settings.price_pro_input_per_1m_usd / 1_000_000) +
        (500 * settings.price_pro_output_per_1m_usd / 1_000_000)
    )

    # 3. Embedding costs (Heuristic: 200 tokens per chunk)
    chunk_count = session.execute(
        select(func.count(PaperChunk.id))
        .where(PaperChunk.created_at >= cutoff)
    ).scalar() or 0
    
    pending_chunk_count = session.execute(
        select(func.count(PendingPaperChunk.id))
        .where(PendingPaperChunk.created_at >= cutoff)
    ).scalar() or 0
    
    emb_costs = (chunk_count + pending_chunk_count) * (200 * settings.price_embedding_per_1m_usd / 1_000_000)

    # Add embedding cost for queries (30 tokens per query)
    query_count = session.execute(
        select(func.count(RequestLog.id))
        .where(RequestLog.received_at >= cutoff)
    ).scalar() or 0
    emb_costs += query_count * (30 * settings.price_embedding_per_1m_usd / 1_000_000)

    return float(flash_costs + pro_costs + emb_costs)
