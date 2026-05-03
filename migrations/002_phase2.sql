CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE papers RENAME COLUMN is_quarantined TO is_active_risk;

ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS course_title TEXT,
    ADD COLUMN IF NOT EXISTS exam_session TEXT,
    ADD COLUMN IF NOT EXISTS held_until DATE NULL,
    ADD COLUMN IF NOT EXISTS pdf_was_generated BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS paper_chunks (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    chunk_no INT NOT NULL,
    chunk_kind TEXT NOT NULL DEFAULT 'question',
    text TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (paper_id, chunk_no)
);

CREATE INDEX IF NOT EXISTS paper_chunks_by_paper ON paper_chunks (paper_id);
CREATE INDEX IF NOT EXISTS paper_chunks_hnsw
    ON paper_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
