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
from app.embeddings import embed_query

_LOCK = threading.Lock()
_CODES: list[str] | None = None
_MAT: np.ndarray | None = None          # (N, dim), L2-normalised
_IDX: dict[str, int] | None = None


def _load(session) -> None:
    global _CODES, _MAT, _IDX
    rows = session.execute(text("SELECT course_code, embedding FROM title_embeddings")).mappings().all()
    if not rows:
        _CODES, _MAT, _IDX = [], np.zeros((0, 1), dtype=np.float32), {}
        return
    mat = np.array([r["embedding"] for r in rows], dtype=np.float32)
    mat /= (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    _CODES = [r["course_code"] for r in rows]
    _MAT = mat
    _IDX = {c: i for i, c in enumerate(_CODES)}


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
        v = np.array(embed_query(query), dtype=np.float32)
        v /= (np.linalg.norm(v) + 1e-9)
        out = {}
        for c in codes:
            i = _IDX.get(c)
            if i is not None:
                out[c] = float(_MAT[i] @ v)
        return out
    except Exception:
        return {}   # semantic is an enrichment — never break retrieval if embedding fails
