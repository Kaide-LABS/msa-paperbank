CREATE TABLE IF NOT EXISTS courses (
    code TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    level INT NOT NULL,
    department TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    id BIGSERIAL PRIMARY KEY,
    course_code TEXT NOT NULL REFERENCES courses(code),
    semester TEXT NOT NULL CHECK (semester IN ('harmattan','rain')),
    year INT NOT NULL,
    gcs_object TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_quarantined BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (course_code, semester, year)
);

CREATE INDEX IF NOT EXISTS papers_lookup ON papers (course_code, year DESC, semester);

CREATE TABLE IF NOT EXISTS request_log (
    id BIGSERIAL PRIMARY KEY,
    wa_message_id TEXT UNIQUE NOT NULL,
    wa_from TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_text TEXT NOT NULL,
    routed_course TEXT,
    routed_year INT,
    routed_semester TEXT,
    matched_paper_id BIGINT REFERENCES papers(id),
    outcome TEXT NOT NULL,
    flash_input_tokens INT,
    flash_output_tokens INT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS request_log_recent ON request_log (received_at DESC);
CREATE INDEX IF NOT EXISTS request_log_outcome ON request_log (outcome);

-- Seed for Phase 1
INSERT INTO courses(code, title, level, department) VALUES
  ('MTH102', 'General Mathematics II', 100, 'Mathematics')
ON CONFLICT (code) DO NOTHING;