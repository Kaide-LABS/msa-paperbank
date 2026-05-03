ALTER TABLE courses
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS pending_papers (
    id BIGSERIAL PRIMARY KEY,
    course_code TEXT NOT NULL REFERENCES courses(code),
    course_title TEXT,
    semester TEXT NOT NULL CHECK (semester IN ('harmattan','rain')),
    exam_session TEXT,
    year INT NOT NULL,
    gcs_object TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active_risk BOOLEAN NOT NULL DEFAULT FALSE,
    held_until DATE NULL,
    pdf_was_generated BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT NOT NULL DEFAULT 'drive_import',     -- 'drive_import' | 'manual_admin' | 'cli_images'
    review_status TEXT NOT NULL DEFAULT 'awaiting_review' CHECK (review_status IN ('awaiting_review','approved','rejected','deferred')),
    reviewer TEXT NULL,
    reviewed_at TIMESTAMPTZ NULL,
    review_notes TEXT NULL,
    UNIQUE (course_code, semester, year, exam_session)
);
CREATE INDEX IF NOT EXISTS pending_papers_status ON pending_papers (review_status, uploaded_at DESC);

CREATE TABLE IF NOT EXISTS pending_paper_chunks (
    id BIGSERIAL PRIMARY KEY,
    pending_paper_id BIGINT NOT NULL REFERENCES pending_papers(id) ON DELETE CASCADE,
    chunk_no INT NOT NULL,
    chunk_kind TEXT NOT NULL DEFAULT 'question',
    text TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pending_paper_id, chunk_no)
);

CREATE INDEX IF NOT EXISTS courses_code_trgm ON courses USING gin (code gin_trgm_ops);
