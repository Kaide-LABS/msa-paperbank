"""Operator-only in-place regeneration of stored chunk embeddings."""
from __future__ import annotations

import argparse
from collections.abc import Iterable

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import PaperChunk, PendingPaperChunk
from app.ports import Embedder
from app.providers import get_embedder, get_engine_provider

_TABLES = {"paper_chunks": PaperChunk, "pending_paper_chunks": PendingPaperChunk}


def reembed_all(
    session: Session,
    embedder: Embedder,
    *,
    batch_size: int = 32,
    tables: Iterable[str] = ("paper_chunks", "pending_paper_chunks"),
    fast_path: bool = False,
) -> int:
    """Re-encode every row, changing only its embedding value.

    ``fast_path`` is deliberately explicit: it is PostgreSQL-only and recreates
    the exact index from migration 002. No DDL is issued by the default path.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    names = tuple(tables)
    if any(name not in _TABLES for name in names):
        raise ValueError("unknown embedding table")
    if fast_path:
        session.execute(text("DROP INDEX IF EXISTS paper_chunks_hnsw"))
    total = 0
    try:
        for name in names:
            model = _TABLES[name]
            rows = session.execute(select(model).order_by(model.id)).scalars()
            batch = []
            for row in rows:
                batch.append(row)
                if len(batch) == batch_size:
                    total += _update_batch(session, model, batch, embedder)
                    batch.clear()
            if batch:
                total += _update_batch(session, model, batch, embedder)
        if fast_path:
            # Recreate the exact index from migration 002 (E2: identical definition).
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS paper_chunks_hnsw ON paper_chunks "
                "USING hnsw (embedding vector_cosine_ops) "
                "WITH (m = 16, ef_construction = 64)"
            ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return total


def _update_batch(session, model, rows, embedder: Embedder) -> int:
    vectors = embedder.embed_documents([row.text for row in rows])
    if len(vectors) != len(rows):
        raise ValueError("embedder returned the wrong number of vectors")
    for row, vector in zip(rows, vectors):
        session.execute(update(model).where(model.id == row.id).values(embedding=vector))
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--fast-path", action="store_true")
    args = parser.parse_args()
    if settings.provider == "gcp":
        raise SystemExit("re-embed is disabled for provider=gcp")
    provider = get_engine_provider(settings)
    try:
        from app.db import SessionLocal
        reembed_all(SessionLocal(), get_embedder(settings), batch_size=args.batch_size, fast_path=args.fast_path)
    finally:
        provider.dispose()


if __name__ == "__main__":
    main()
