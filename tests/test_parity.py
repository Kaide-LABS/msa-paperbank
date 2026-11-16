import json

from app.parity import jaccard_at_k, rank_correlation


def test_parity_metrics():
    assert jaccard_at_k([1, 2, 3], [1, 2, 3], 3) == 1.0
    assert jaccard_at_k([1, 2], [3, 4], 2) == 0.0
    assert jaccard_at_k([1, 2, 3], [1, 4, 5], 3) == 1 / 5
    assert rank_correlation([1, 2, 3], [1, 2, 3]) == 1.0
    assert rank_correlation([1, 2, 3], [3, 2, 1]) == -1.0


def test_fixed_query_set_is_nonempty():
    with open("data/parity_queries.json", encoding="utf-8") as fh:
        queries = json.load(fh)
    assert 15 <= len(queries) <= 25
