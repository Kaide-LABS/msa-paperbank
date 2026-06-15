# -*- coding: utf-8 -*-
"""Offline / admin step (NOT per-request): embed the distinct course titles into `title_embeddings`
for the in-memory mini semantic search. Re-runnable + idempotent (upsert by course_code) — re-run
after new courses are approved. Uses the project's existing Vertex embedding (gemini-embedding-001,
RETRIEVAL_DOCUMENT). ~332 courses, one batch, fractions of a cent."""
from sqlalchemy import text
from app.db import SessionLocal
from app.config import settings
from app.embeddings import embed_many
from app.serve_index import _slug_title

DDL = """CREATE TABLE IF NOT EXISTS title_embeddings (
    course_code  TEXT PRIMARY KEY,
    course_title TEXT,
    embed_text   TEXT NOT NULL,
    embedding    double precision[] NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now())"""


def build():
    s = SessionLocal()
    s.execute(text(DDL)); s.commit()
    rows = s.execute(text(
        "SELECT course_code, (array_agg(course_title ORDER BY course_title) "
        "FILTER (WHERE course_title IS NOT NULL))[1] AS title "
        "FROM pending_papers WHERE student_visible AND source = :src GROUP BY course_code"
    ), {"src": settings.serve_source_tag}).mappings().all()
    courses = [(r["course_code"], r["title"]) for r in rows]
    # embed_text: the human title when present, else the de-slugged code words (best available signal)
    texts = [(t or _slug_title(c)) for c, t in courses]
    print(f"embedding {len(texts)} distinct courses (RETRIEVAL_DOCUMENT)...")
    vecs = embed_many(texts)
    for (code, title), et, vec in zip(courses, texts, vecs):
        s.execute(text(
            "INSERT INTO title_embeddings (course_code, course_title, embed_text, embedding, updated_at) "
            "VALUES (:c,:t,:et,:e, now()) ON CONFLICT (course_code) DO UPDATE SET "
            "course_title=:t, embed_text=:et, embedding=:e, updated_at=now()"
        ), {"c": code, "t": title, "et": et, "e": vec})
    s.commit()
    n = s.execute(text("SELECT count(*) FROM title_embeddings")).scalar()
    print(f"upserted {len(courses)} courses; title_embeddings now holds {n} rows")
    s.close()


if __name__ == "__main__":
    build()
