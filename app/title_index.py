# -*- coding: utf-8 -*-
"""In-memory mini semantic index for the hybrid matcher (Plan B). Loads the precomputed
`title_embeddings` (~322 vectors, ~1MB) into RAM once per process — one SELECT, NO Vertex at boot.
Per query: embed the query once (RETRIEVAL_QUERY) and cosine ONLY against the course_codes the
fuzzy layer already surfaced (semantic never introduces new courses → absent courses fuzzy gave low
scores can't be rescued; A1's clean-miss gate holds). Enrichment only: any failure -> empty scores,
retrieval falls back to pure fuzzy."""
import threading
import numpy as np
from sqlalchemy import text
from app.config import settings
from app.providers import get_embedder

_LOCK = threading.Lock()
_CODES: list[str] | None = None
_MAT: np.ndarray | None = None          # (N, dim), L2-normalised
_IDX: dict[str, int] | None = None


def _load(session) -> None:
    global _CODES, _MAT, _IDX
    dim = settings.embedding_dim
    # Fast path: select ONLY the bytea column (never transfer/deserialise the slow double[]).
    rows = session.execute(text(
        "SELECT course_code, embedding_f32 FROM title_embeddings"
    )).mappings().all()
    codes, vecs, missing = [], [], []
    for r in rows:
        buf = r["embedding_f32"]
        if buf is None:
            missing.append(r["course_code"])                      # pre-bytea row -> fallback below
            continue
        v = np.frombuffer(bytes(buf), dtype=np.float32)
        if v.shape[0] == dim:
            codes.append(r["course_code"]); vecs.append(v)
    if missing:
        # rare: fetch the old double[] only for rows not yet re-embedded (enrichment, never crash)
        fb = session.execute(text(
            "SELECT course_code, embedding FROM title_embeddings WHERE course_code = ANY(:m)"
        ), {"m": missing}).mappings().all()
        for r in fb:
            if r["embedding"] is not None:
                v = np.asarray(r["embedding"], dtype=np.float32)
                if v.shape[0] == dim:
                    codes.append(r["course_code"]); vecs.append(v)
    if not codes:
        _CODES, _MAT, _IDX = [], np.zeros((0, 1), dtype=np.float32), {}
        return
    mat = np.array(vecs, dtype=np.float32)
    mat /= (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)     # normalise at load, exactly as before
    _CODES, _MAT, _IDX = codes, mat, {c: i for i, c in enumerate(codes)}


def ensure_loaded(session) -> None:
    if _MAT is None:
        with _LOCK:
            if _MAT is None:
                _load(session)


def semantic_scores(session, query: str, codes: list[str]) -> dict[str, float]:
    """{course_code: cosine} for the given codes only. Embeds the query once. Empty on any failure."""
    if not query or not codes:
        return {}
    try:
        ensure_loaded(session)
        if not _CODES:
            return {}
        v = np.array(get_embedder(settings).embed_query(query), dtype=np.float32)
        v /= (np.linalg.norm(v) + 1e-9)
        out = {}
        for c in codes:
            i = _IDX.get(c)
            if i is not None:
                out[c] = float(_MAT[i] @ v)
        return out
    except Exception:
        return {}   # semantic is an enrichment — never break retrieval if embedding fails
