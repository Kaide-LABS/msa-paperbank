CREATE TABLE IF NOT EXISTS users (
    phone_number TEXT PRIMARY KEY,
    inferred_courses JSONB NOT NULL DEFAULT '{}'::jsonb,
    interaction_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    privacy_notice_sent_at TIMESTAMPTZ NULL,
    opted_out_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS users_last_seen ON users (last_seen_at DESC);

CREATE TABLE IF NOT EXISTS user_tombstones (
    phone_number TEXT PRIMARY KEY,
    opted_out_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_keyword TEXT NULL
);
