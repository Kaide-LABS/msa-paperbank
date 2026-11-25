import json
from unittest.mock import MagicMock

import app.parity as parity
from app.parity import jaccard_at_k, rank_correlation, run_parity


def test_parity_metrics():
    assert jaccard_at_k([1, 2, 3], [1, 2, 3], 3) == 1.0
    assert jaccard_at_k([1, 2], [3, 4], 2) == 0.0
    assert jaccard_at_k([1, 2, 3], [1, 4, 5], 3) == 1 / 5
    assert rank_correlation([1, 2, 3], [1, 2, 3]) == 1.0
    assert rank_correlation([1, 2, 3], [3, 2, 1]) == -1.0
    # Partial overlap, same order among the common ids -> positive correlation.
    assert rank_correlation([1, 2, 3, 4], [1, 2, 9, 8]) == 1.0


class _ListEmbedder:
    """Fake embedder whose per-query vector IS the ranked id list to return; used
    with a monkeypatched _ids so run_parity needs no pgvector/cosine SQL."""

    def __init__(self, mapping):
        self._mapping = mapping

    def embed_query(self, query):
        return list(self._mapping[query])


def test_run_parity_over_seeded_corpus_yields_in_range_metrics(monkeypatch):
    # Rank by the "vector" directly: the fake vectors are the top-k id lists. No
    # cosine_distance / pgvector needed, so the aggregation runs on any DB (none here).
    monkeypatch.setattr(parity, "_ids", lambda session, vec, k: list(vec)[:k])

    queries = ["q_same", "q_reversed", "q_partial"]
    old = _ListEmbedder({
        "q_same": [1, 2, 3],
        "q_reversed": [1, 2, 3],
        "q_partial": [1, 2, 3],
    })
    new = _ListEmbedder({
        "q_same": [1, 2, 3],       # identical -> jaccard 1, corr 1
        "q_reversed": [3, 2, 1],   # reversed  -> jaccard 1, corr -1
        "q_partial": [2, 3, 4],    # partial   -> jaccard 1/2
    })

    report = run_parity(MagicMock(), old, new, queries, k=3)

    assert report["k"] == 3
    assert [r["query"] for r in report["queries"]] == queries
    assert report["queries"][0]["jaccard"] == 1.0
    assert report["queries"][0]["rank_correlation"] == 1.0
    assert report["queries"][1]["rank_correlation"] == -1.0
    assert report["queries"][2]["jaccard"] == 1 / 2
    # Set means land in their valid ranges.
    assert 0.0 <= report["mean_jaccard"] <= 1.0
    assert -1.0 <= report["mean_rank_correlation"] <= 1.0


def test_run_parity_accepts_callable_old_snapshot(monkeypatch):
    monkeypatch.setattr(parity, "_ids", lambda session, vec, k: list(vec)[:k])
    report = run_parity(MagicMock(), lambda q: [1, 2], _ListEmbedder({"a": [2, 1]}),
                        ["a"], k=2)
    assert report["queries"][0]["jaccard"] == 1.0
    assert -1.0 <= report["mean_rank_correlation"] <= 1.0


def test_fixed_query_set_is_nonempty():
    with open("data/parity_queries.json", encoding="utf-8") as fh:
        queries = json.load(fh)
    assert 15 <= len(queries) <= 25
