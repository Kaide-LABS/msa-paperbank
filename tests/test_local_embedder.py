# -*- coding: utf-8 -*-
"""Phase 4 Part A — LocalCpuEmbedder unit tests (network-free).

Every test here drives the adapter through an injected, deterministic fake encoder:
no model is downloaded and no network client is opened (AC 2 / E1). The real
`sentence_transformers` package is never imported by these tests — the adapter only
imports it lazily inside `_get_encoder`, which the fake path never reaches.
"""
import math
import types

import pytest

from app.errors import EmbeddingError
from app.ports import Embedder
from app.providers import get_embedder
from app.providers.local.embedder import LocalCpuEmbedder


def _fake_encoder(dim=768):
    """A stand-in for SentenceTransformer: `.encode(list[str])` -> list of vectors.

    Returns deterministic, NON-normalized vectors so the adapter's own L2
    normalization (E4) is observable on the output.
    """

    class _Enc:
        def encode(self, texts, normalize_embeddings=False, batch_size=32):
            # Deterministic per-text vector; magnitude != 1 so normalization shows, and
            # the leading component varies per input so the DIRECTION differs per row
            # (normalization preserves direction, not magnitude).
            return [
                [float(i + 1 if j == 0 else 1) for j in range(dim)]
                for i, _ in enumerate(texts)
            ]

    return _Enc()


def _local_settings(**over):
    base = dict(
        embedding_dim=768,
        embedding_normalize=True,
        embedding_batch_size=32,
        embedding_model_name="sentence-transformers/all-mpnet-base-v2",
        embedding_model_path=None,
        embedding_device="cpu",
        provider="local",
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def test_is_embedder_instance():
    emb = LocalCpuEmbedder(_fake_encoder())
    assert isinstance(emb, Embedder)


def test_embed_one_and_query_return_768_list():
    emb = LocalCpuEmbedder(_fake_encoder(), dim=768)
    v = emb.embed_one("hello")
    assert isinstance(v, list)
    assert len(v) == 768
    assert all(isinstance(x, float) for x in v)
    # embed_query is symmetric with embed_one for this model.
    assert emb.embed_query("hello") == v


def test_embed_documents_preserves_order_and_shape():
    emb = LocalCpuEmbedder(_fake_encoder(), dim=768)
    out = emb.embed_documents(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(row) == 768 for row in out)
    # The fake scales each row by its index, so normalized rows still differ per input,
    # preserving order-sensitivity.
    assert out[0] != out[1] != out[2]


def test_embed_documents_empty_is_empty():
    emb = LocalCpuEmbedder(_fake_encoder(), dim=768)
    assert emb.embed_documents([]) == []


def test_vectors_are_unit_norm():
    emb = LocalCpuEmbedder(_fake_encoder(), dim=768, normalize=True)
    v = emb.embed_one("x")
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-6)


def test_dim_property():
    assert LocalCpuEmbedder(_fake_encoder(), dim=768).dim == 768


def test_wrong_dim_raises_embedding_error():
    # Encoder yields 5-dim vectors but the adapter expects 768 -> EmbeddingError (AC 8).
    emb = LocalCpuEmbedder(_fake_encoder(dim=5), dim=768)
    with pytest.raises(EmbeddingError):
        emb.embed_one("x")


def test_factory_returns_local_embedder_without_loading_model():
    emb = get_embedder(_local_settings())
    assert isinstance(emb, LocalCpuEmbedder)
    # E1: selection/construction is lazy — no SentenceTransformer built, no download.
    assert emb._encoder is None


def test_from_settings_is_lazy_no_model_constructed():
    emb = LocalCpuEmbedder.from_settings(_local_settings())
    # The real model is built only on first encode, never at construction (E1).
    assert emb._encoder is None
    assert emb.dim == 768


def test_import_does_not_pull_sentence_transformers():
    # Importing the adapter module must not import the heavy package (E1 / AC 2).
    import sys

    import app.providers.local.embedder  # noqa: F401 — already imported above, asserting state

    assert "sentence_transformers" not in sys.modules
