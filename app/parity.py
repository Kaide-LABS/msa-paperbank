"""Offline top-k parity calculations and harness."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Paper, PaperChunk
from app.ports import Embedder


def jaccard_at_k(old_ids: Sequence, new_ids: Sequence, k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    a, b = set(old_ids[:k]), set(new_ids[:k])
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def rank_correlation(old_ranks: Sequence, new_ranks: Sequence) -> float:
    common = set(old_ranks) & set(new_ranks)
    if len(common) < 2:
        return 1.0 if common else 0.0
    old = {v: i for i, v in enumerate(old_ranks)}
    new = {v: i for i, v in enumerate(new_ranks)}
    n = len(common)
    d2 = sum((old[v] - new[v]) ** 2 for v in common)
    return max(-1.0, min(1.0, 1 - (6 * d2) / (n * (n * n - 1))))


def _ids(session: Session, vector: list[float], k: int) -> list[int]:
    stmt = (select(Paper.id).join(PaperChunk, PaperChunk.paper_id == Paper.id)
            .order_by(PaperChunk.embedding.cosine_distance(vector)).limit(k))
    return list(session.execute(stmt).scalars())


def run_parity(session: Session, embedder_old_snapshot: Callable[[str], list[float]] | Embedder,
               embedder_new: Embedder, queries: Sequence[str], *, k: int = 10) -> dict:
    rows = []
    for query in queries:
        old_vec = (embedder_old_snapshot.embed_query(query) if hasattr(embedder_old_snapshot, "embed_query")
                   else embedder_old_snapshot(query))
        old_ids = _ids(session, old_vec, k)
        new_ids = _ids(session, embedder_new.embed_query(query), k)
        rows.append({"query": query, "old_ids": old_ids, "new_ids": new_ids,
                     "jaccard": jaccard_at_k(old_ids, new_ids, k),
                     "rank_correlation": rank_correlation(old_ids, new_ids)})
    return {"k": k, "queries": rows,
            "mean_jaccard": mean([r["jaccard"] for r in rows]) if rows else 1.0,
            "mean_rank_correlation": mean([r["rank_correlation"] for r in rows]) if rows else 1.0}


def main() -> None:
    """Operator CLI: run the parity harness over the fixed query set and print JSON.

    Reuses ``run_parity`` unchanged. The "old" side is a pre-captured snapshot file
    mapping each query to its stored (Vertex-era) top-k query vector; the "new" side is
    the configured local embedder. Both come from the self-hosted stack — no GCP import,
    no network beyond the local model. The report threshold lives in
    ``docs/parity_report.md`` (mean Jaccard@10 >= 0.70, mean rank correlation >= 0.60).
    """
    import argparse
    import json

    from app.config import settings
    from app.providers import get_embedder, get_engine_provider

    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", default="data/parity_queries.json")
    parser.add_argument("--old-snapshot", required=True,
                        help="JSON object mapping each query to its old top-k query vector")
    parser.add_argument("-k", type=int, default=10)
    args = parser.parse_args()

    if settings.provider == "gcp":
        raise SystemExit("parity is run against the self-hosted provider, not gcp")

    with open(args.queries, encoding="utf-8") as fh:
        queries = json.load(fh)
    with open(args.old_snapshot, encoding="utf-8") as fh:
        snapshot = json.load(fh)

    def old_vec(query: str) -> list[float]:
        if query not in snapshot:
            raise SystemExit(f"old snapshot missing vector for query: {query!r}")
        return snapshot[query]

    provider = get_engine_provider(settings)
    try:
        from app.db import SessionLocal
        report = run_parity(SessionLocal(), old_vec, get_embedder(settings), queries, k=args.k)
    finally:
        provider.dispose()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
