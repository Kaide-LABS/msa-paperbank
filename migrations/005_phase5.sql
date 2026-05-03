-- Whitelist of approved photo contributors.
CREATE TABLE IF NOT EXISTS uploaders (
    phone_number TEXT PRIMARY KEY,           -- E.164 without '+'
    display_name TEXT NULL,
    added_by TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ NULL,             -- soft-revoke (NULL = active)
    revoke_reason TEXT NULL
);
CREATE INDEX IF NOT EXISTS uploaders_active ON uploaders (phone_number) WHERE revoked_at IS NULL;

-- One logical paper assembled from N photos sent in a burst.
CREATE TABLE IF NOT EXISTS image_batches (
    id BIGSERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    pending_paper_id BIGINT REFERENCES pending_papers(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN (
        'open', 'sealed', 'ocr_done', 'deferred_ocr', 'failed'
    )),
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_item_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sealed_at TIMESTAMPTZ NULL,
    failure_reason TEXT NULL
);
CREATE INDEX IF NOT EXISTS image_batches_open_per_phone
    ON image_batches (phone_number) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS image_batches_open_globally
    ON image_batches (last_item_at) WHERE status = 'open';

-- One row per inbound image attached to a batch.
CREATE TABLE IF NOT EXISTS image_batch_items (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES image_batches(id) ON DELETE CASCADE,
    wa_media_id TEXT NOT NULL,
    wa_message_id TEXT NOT NULL,                -- for dedupe + audit
    gcs_object TEXT NOT NULL,                   -- gs://.../media/<wa_message_id>.jpg
    mime_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,                       -- of the downloaded payload
    ord INT NOT NULL,                           -- 1-based order within the batch
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (batch_id, ord),
    UNIQUE (wa_message_id)                      -- Meta retries dedupe
);

-- Notifications queued by the synchronous sealer
CREATE TABLE IF NOT EXISTS intake_notifications (
    id BIGSERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ NULL
);
