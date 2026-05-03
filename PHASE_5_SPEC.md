# PHASE 5 — Technical Spec (Execution Blueprint)

**Source of truth:** `PRD.md` (canonical, narrow V1 scope). `MASTER_PRD.md` is reference-only; this phase consumes its `§2.2 Yusuf` persona, `§4.3` ingestion flow (user-triggered branch), `§6` `image_batches` schema, and `§7.2` two-hop media download.
**Audience:** the execution agent that will write the code. Do not deviate without amending this file first.
**Predecessors:** `PHASE_1_SPEC.md`, `PHASE_2_SPEC.md`, `PHASE_3_SPEC.md`, `PHASE_4_SPEC.md`. All merged.

---

## 0. Phase 5 mission (one sentence)

Let an **explicitly whitelisted** PAU contributor (Yusuf the paper-contributor persona) WhatsApp a burst of paper photos to the bot, have them stitched into one logical submission, OCR'd, embedded, and parked in the existing `pending_papers` curation queue — without introducing any queue, scheduler, background worker, or new Cloud service.

---

## 1. Scope (locked)

**In Phase 5:**

1. **Uploader whitelist.** New table `uploaders`. New CLI: `python -m admin.uploaders {allow,revoke,list}`. Only whitelisted phone numbers may submit images via WhatsApp; everyone else gets a polite text reply.
2. **Image batches.** New tables `image_batches` and `image_batch_items` per `MASTER_PRD §6`. A batch represents one logical paper assembled from N photos sent in quick succession.
3. **Inbound image handler.** `app/intake.py` — for whitelisted senders, downloads media via the two-hop Graph API (`MASTER_PRD §7.2`), uploads bytes to GCS, appends to the sender's open batch (or opens a new one). Replies with a one-line ack (`"got page 3"`).
4. **Seal-on-inactivity.** Every webhook request runs a tiny **eager sealer** at the start: any `image_batches.status='open'` row whose latest item is older than `IMAGE_BATCH_SEAL_SECONDS` (default `90`) is sealed → preprocess → OCR → embed → insert one `pending_papers` + N `pending_paper_chunks` rows. **No scheduler, no Cloud Tasks, no background thread.** All work runs synchronously inside the Cloud Run request that triggered the sweep.
5. **Sealed-batch reply.** When a batch is successfully sealed and admitted to the curation queue, the contributor receives a single text message: `"Got 4 pages. Submitted for review — Hafeedh will approve and you'll see it in the bank soon, in shaa Allah."`. Errors get a different short text.
6. **Per-day OCR budget guard.** A new setting `image_intake_ocr_per_day` (default `100`). When the day's OCR count is exceeded, sealing is skipped and the batch is left in `status='deferred_ocr'` for admin to drain via `admin batches seal <id>`.
7. **Abuse caps.** Max `12` items per batch (existing `ocr_max_images_per_paper`). Max `3` open-or-sealed-today batches per phone per UTC day. Beyond that, new images get rejected with a "you've submitted enough today" text and *no* media is downloaded.
8. **Admin batches CLI.** `python -m admin.batches {list,seal,clear}`.
9. **Tests** for whitelist gate, batch open/append/seal, and the eager sealer.

**Out of Phase 5 (do not build):**

- Any queue, scheduler, Cloud Tasks, Pub/Sub, BackgroundTasks, or asyncio task. Sealing runs synchronously on the next inbound webhook.
- A `users` table or any read of inferred profile fields. (V1.2.)
- BM25 / hybrid retrieval. (V2.)
- A web UI. The whitelist and batches commands stay terminal-only.
- Auto-PDF combine for arbitrary contributor uploads — we still use `app.pdfgen.stitch_images_to_pdf` from Phase 2 with the same image-order semantics (received order). No "smart" reordering.
- Multi-paper detection within one batch. One batch = one paper.
- A separate moderation queue. Sealed batches go directly to the existing `pending_papers` table; the existing `admin curate` workflow handles them.

---

## 2. Repository layout (delta from Phase 4)

Files added (✦) or modified (∆):

```
msa-paperbank/
├── PHASE_5_SPEC.md             ✦
├── README.md                   ∆ (one-paragraph note: contributors are whitelisted)
├── RUNBOOK.md                  ∆ (whitelist + batch troubleshooting section)
├── requirements.txt            ∆ (no new deps)
├── app/
│   ├── config.py               ∆ (intake settings)
│   ├── db.py                   ∆ (Uploader, ImageBatch, ImageBatchItem)
│   ├── schemas.py              ∆ (WAImage payload subset)
│   ├── whatsapp.py             ∆ (download_media: 2-hop Graph API helper)
│   ├── intake.py               ✦
│   ├── pipeline.py             ∆ (eager sealer + image branch)
│   └── main.py                 ∆ (no signature/auth changes; only widens type guard)
├── admin/
│   ├── uploaders.py            ✦
│   └── batches.py              ✦
├── migrations/
│   └── 005_phase5.sql          ✦
└── tests/
    ├── test_uploaders.py             ✦
    ├── test_intake_batch.py          ✦
    ├── test_intake_seal.py           ✦
    └── test_pipeline.py              ∆ (new: image-from-non-whitelisted branch)
```

No other files change.

---

## 3. Pinned dependency additions

None. The Graph API media-download path uses the existing `httpx` client; preprocess/OCR/embeddings/pdfgen are already present from Phases 2–4.

---

## 4. Schema migration (`migrations/005_phase5.sql`)

Run order: must be applied after `004_phase4.sql`.

```sql
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
```

No backfill. The `pending_papers.source` CHECK was already widened in Phase 4 to include `'cli_images'`; for Phase 5 we add `'wa_intake'` as an allowed value via:

```sql
-- Phase 4 left source as a free TEXT column (no CHECK). Phase 5 just uses 'wa_intake' as a literal.
-- If a CHECK has been added by the executor between phases, replace it with one that includes
-- 'drive_import','manual_admin','cli_images','wa_intake'.
```

---

## 5. Configuration delta (`app/config.py`)

Add the following fields. All have defaults.

| Field | Env var | Type | Default |
|---|---|---|---|
| `image_batch_seal_seconds` | `IMAGE_BATCH_SEAL_SECONDS` | `int` | `90` |
| `image_intake_ocr_per_day` | `IMAGE_INTAKE_OCR_PER_DAY` | `int` | `100` |
| `image_intake_max_open_batches_per_phone_per_day` | `IMAGE_INTAKE_MAX_OPEN_BATCHES_PER_PHONE_PER_DAY` | `int` | `3` |
| `media_gcs_prefix` | `MEDIA_GCS_PREFIX` | `str` | `"media/"` |

`ocr_max_images_per_paper` (Phase 2) is reused as the per-batch item cap.

---

## 6. Schemas (`app/schemas.py`)

Extend `WAMessage` to model image payloads:

```python
class WAImage(BaseModel):
    id: str                   # the media_id
    mime_type: str
    sha256: str | None = None
    caption: str | None = None

class WAMessage(BaseModel):
    id: str
    from_: str = Field(validation_alias="from")
    timestamp: str
    type: Literal[...]                 # unchanged
    text: WAText | None = None
    image: WAImage | None = None       # NEW
```

No change to `RouterOutput` / `Reply` types.

---

## 7. Whatsapp client (`app/whatsapp.py`) extension

Add **two** functions; keep all existing helpers byte-identical.

```python
def get_media_metadata(http_client: httpx.Client, media_id: str) -> tuple[str, str, int]:
    """GET /<wa_graph_version>/<media_id> → returns (download_url, mime_type, file_size_bytes).
    The download_url expires in ~5 minutes — caller must use it immediately.
    Raises WhatsAppError on non-2xx."""

def download_media(http_client: httpx.Client, download_url: str) -> bytes:
    """GET <download_url> with the same Bearer token. Returns the binary body.
    The Authorization header is required even on the lookaside CDN URL.
    Raises WhatsAppError on non-2xx."""
```

Implementations are 6–10 lines each. Timeouts use the existing `httpx.Client`. No retries beyond the existing single connect-error retry.

---

## 8. Intake module (`app/intake.py`)

This is the single owner of "what to do with an image webhook." It is called from `app/pipeline.py`'s image branch.

### 8.1 Public functions

```python
def is_whitelisted(session: Session, phone_number: str) -> bool: ...

def handle_image(
    session: Session,
    http_client: httpx.Client,
    gcs_client: storage.Client,
    msg: WAMessage,
) -> Reply: ...

def sweep_and_seal(
    session: Session,
    gcs_client: storage.Client,
) -> int:
    """Find every status='open' batch where last_item_at is older than the
    seal threshold, run preprocess+OCR+embed, insert pending_papers + chunks.
    Returns the number of batches sealed in this call."""
```

### 8.2 `is_whitelisted`

`SELECT 1 FROM uploaders WHERE phone_number=:phone AND revoked_at IS NULL LIMIT 1`. Returns bool. No caching — admin add/revoke must take effect immediately.

### 8.3 `handle_image` sequence

1. **Whitelist check.** If `is_whitelisted(session, msg.from_) is False`: log `image_from_non_whitelisted`, set `RequestLog.outcome="not_whitelisted"` (this is a NEW outcome string — add to the docs but no schema change), return `TextReply("This number isn't approved to submit photos. Ask Hafeedh to add you.")`.
2. **Per-day cap.** Count batches owned by this phone whose `opened_at >= today_utc_midnight`. If `>= settings.image_intake_max_open_batches_per_phone_per_day`: return `TextReply("You've submitted enough today. Try again tomorrow, in shaa Allah.")` with `outcome="rate_limited"`. Do not download media.
3. **Find or open a batch.** `SELECT * FROM image_batches WHERE phone_number=:phone AND status='open' ORDER BY id DESC LIMIT 1`. If absent or `last_item_at` is older than `image_batch_seal_seconds`: open a new batch. Otherwise reuse.
4. **Per-batch item cap.** Count items in the chosen batch. If `>= settings.ocr_max_images_per_paper`: seal the batch immediately (call into the same logic as `sweep_and_seal` for that single id), then open a new batch and treat this image as item #1 of the new batch. Reply `"That batch is full — starting a new one. got page 1"`.
5. **Download media.**
   - `download_url, mime, size = whatsapp.get_media_metadata(http_client, msg.image.id)`.
   - Reject if `size > settings.ocr_max_image_bytes` → `outcome="error"`, reply `"That image is too large. Try a smaller photo."`.
   - `pdf_bytes = whatsapp.download_media(http_client, download_url)`.
   - `sha = hashlib.sha256(pdf_bytes).hexdigest()`.
6. **GCS upload.** Object key: `f"{settings.media_gcs_prefix}{msg.id}.jpg"` (use `.bin` if mime is unknown). `bucket.blob(key).upload_from_string(pdf_bytes, content_type=mime)`.
7. **Append item.** `ord = (current item count) + 1`. Insert `ImageBatchItem(batch_id=batch.id, wa_media_id=msg.image.id, wa_message_id=msg.id, gcs_object=key, mime_type=mime, sha256=sha, ord=ord)`. On `IntegrityError` (`wa_message_id` UNIQUE) → Meta retry, do nothing more, return `TextReply(body="")` (the route layer skips empty replies).
8. **Update batch.** `batch.last_item_at = now()`. Commit.
9. **Reply.** `TextReply(f"got page {ord}")`.

### 8.4 `sweep_and_seal` sequence

For each open batch with `last_item_at < now - seal_seconds`:

1. `items = SELECT * FROM image_batch_items WHERE batch_id=:id ORDER BY ord`.
2. If `len(items) == 0`: mark `status='failed', failure_reason='empty'`, commit, continue.
3. Daily-OCR-budget check: count `image_batches.sealed_at` rows with `status='ocr_done'` that completed in the last 24h. If `>= settings.image_intake_ocr_per_day`: mark `status='deferred_ocr'`, commit, continue. The contributor is **not** notified for deferred batches; admin drains via `admin batches seal`.
4. Read each item's bytes from GCS. `preprocess_paper_image(b)` for each.
5. `ocr_result = ocr_paper(preprocessed)`. On error or empty questions: `status='failed', failure_reason='ocr_empty'`, commit, send the contributor a `TextReply("We couldn't read those photos clearly. Try retaking them.")` via the route layer's outbound path. (This message is queued by the sealer — see §9.)
6. `vectors = embed_many([q.text for q in ocr_result.questions])`. On error: `status='failed', failure_reason='embedding_failed'`, commit.
7. `pdf_bytes = stitch_images_to_pdf(preprocessed)`. Object key: `papers/_intake/{batch.id}-{sha[:8]}.pdf`. Upload.
8. **Course resolution.** OCR's `course_code` is best-effort. If it matches a known active course (`retrieval.known_courses`), use it. Otherwise default to `"UNKNOWN"` — but `UNKNOWN` is not in `courses` and `pending_papers.course_code REFERENCES courses(code)` will reject. So: if no match, mark `status='failed', failure_reason='unknown_course'`, commit, notify contributor `"Couldn't tell which course that is — Hafeedh will follow up."`. Do **not** crash the sweep.
9. Compute `is_active_risk` and `held_until=NULL` per Phase 4 rules.
10. Insert `PendingPaper(source='wa_intake', uploaded_by=batch.phone_number, ...)` + N `PendingPaperChunk` rows in one transaction. Set `batch.pending_paper_id = paper.id`, `batch.status='ocr_done'`, `batch.sealed_at=now()`. Commit.
11. Notify contributor via the same outbound path the route layer uses (queued for the route to send after the sealer returns; see §9).

The sealer is **purely synchronous** and runs inside whichever request triggered it. Worst-case latency for that request: ~2 s preprocess + ~3 s OCR + ~1 s embed + ~1 s GCS upload ≈ 7 s — comfortably within Cloud Run's 60 s timeout. Concurrent webhooks: the `SELECT ... FOR UPDATE SKIP LOCKED` pattern (see §10) guarantees only one request seals any given batch.

---

## 9. Pipeline change (`app/pipeline.py`)

Two changes. The existing 1–8 step structure is preserved.

### 9.1 At the very top of `handle_message`, before step 1 (idempotency)

```python
# Phase 5: opportunistic sealer. Run before anything else so a long-idle batch
# doesn't get further-delayed by every subsequent webhook. Wrapped in a broad
# except so a sweep failure cannot break the request path.
try:
    intake.sweep_and_seal(session, gcs_client)  # gcs_client passed via dependency
except Exception:
    log.exception("intake_sweep_failed")
```

The `gcs_client` is plumbed in via `app/deps.py`'s existing DI — add a `get_gcs_client()` provider that returns `request.app.state.gcs`. `handle_message`'s signature gains one parameter; `app/main.py`'s call site is updated.

### 9.2 New image branch in step 2 (Type guard rewrite)

```python
if msg.type == "image":
    if msg.image is None:
        log_entry.outcome = "error"
        log_entry.error = "image_payload_missing"
        session.commit()
        return TextReply(body="Send a clear photo of the paper.")
    return intake.handle_image(session, http_client, gcs_client, msg)

if msg.type != "text":
    # unchanged Phase 1 behavior — guidance text
    ...
```

`http_client` and `gcs_client` are also threaded into `handle_message`. **No new outcome strings other than `not_whitelisted`** (and reuse of `rate_limited`, `error`).

### 9.3 Sealer-originated outbound replies

The sealer cannot directly call `whatsapp.send_reply` because it's invoked outside any specific user message context (it might be sealing batch B owned by phone X while the request was for phone Y). Approach:

- The sealer **records** intended notifications by inserting into a new in-memory `list` `app.state.pending_notifications` (lifespan-scoped) keyed by `(phone, body)`. Wait — that's fragile across instances. **Replace with:** the sealer writes a row to a tiny `intake_notifications` table:

```sql
CREATE TABLE IF NOT EXISTS intake_notifications (
    id BIGSERIAL PRIMARY KEY,
    phone_number TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ NULL
);
```

Add this table to `005_phase5.sql`.

After every webhook returns, the route handler in `app/main.py` does one final synchronous step before returning 200 to Meta: select up to 5 unsent notifications (`ORDER BY created_at` LIMIT 5 FOR UPDATE SKIP LOCKED), call `whatsapp.send_text(...)` for each, mark `sent_at=now()`, commit. If sending fails, leave `sent_at=NULL` for the next request to retry. **No background worker.** Worst-case unsent notifications drain on the next webhook of any kind.

This keeps the "no queue" rule while honoring at-most-once-per-message intent: the contributor will receive their seal confirmation the next time *anyone* messages the bot, or the next time they themselves send an image.

---

## 10. Concurrency

The eager sealer is invoked from every webhook request. Two concurrent webhooks could both try to seal the same batch. To prevent double-OCR and double-insert:

- `sweep_and_seal` opens its candidate selection with `SELECT ... FOR UPDATE SKIP LOCKED`:
  ```python
  candidates = session.execute(
      select(ImageBatch)
      .where(ImageBatch.status == 'open')
      .where(ImageBatch.last_item_at < cutoff)
      .order_by(ImageBatch.id)
      .limit(10)
      .with_for_update(skip_locked=True)
  ).scalars().all()
  ```
- Each candidate is fully processed before the function returns; the row-level lock holds until commit.
- If a row was already grabbed by another request, `SKIP LOCKED` skips it cleanly.
- Cap: process at most `10` batches per sweep. If more are pending, the next webhook drains the rest.

`intake_notifications` reads use the same pattern (`FOR UPDATE SKIP LOCKED`).

---

## 11. Admin commands

### 11.1 `admin/uploaders.py`

```
python -m admin.uploaders allow <PHONE> [--name "Yusuf Adebayo"]
python -m admin.uploaders revoke <PHONE> --reason "<text>" [--yes]
python -m admin.uploaders list [--include-revoked] [--csv PATH]
```

`allow`: insert with `added_by=os.environ.get("USER","ibrahim")`. If row exists with `revoked_at IS NOT NULL`, un-revoke it (set `revoked_at=NULL`, `revoke_reason=NULL`). Otherwise insert.

`revoke`: update `revoked_at=now(), revoke_reason=:reason`. Idempotent (re-revoke → no-op + exit 0).

`list`: `tabulate` table with columns `phone_number, display_name, added_by, added_at, revoked_at, revoke_reason`. Default excludes revoked.

### 11.2 `admin/batches.py`

```
python -m admin.batches list [--phone PHONE] [--status STATUS] [--limit 50]
python -m admin.batches seal <BATCH_ID> [--yes]
python -m admin.batches clear <BATCH_ID> --reason "<text>" [--yes]
```

`list`: prints `id, phone_number, status, opened_at, last_item_at, sealed_at, items_count`.
`seal <id>`: forcibly run the sealer logic on a single batch (used to drain `deferred_ocr`). Reuses `sweep_and_seal` internals, scoped by id.
`clear <id>`: marks `status='failed'`, optionally deletes the GCS objects of every item.

---

## 12. Tests (`tests/`)

### 12.1 `tests/test_uploaders.py`
- `allow` then `is_whitelisted` → True.
- `revoke` then `is_whitelisted` → False.
- Re-`allow` un-revokes (single row).

### 12.2 `tests/test_intake_batch.py`
- Mock `whatsapp.get_media_metadata` and `whatsapp.download_media` to return canned bytes.
- Mock GCS client.
- Whitelisted phone sends image → batch is opened, item inserted, reply is `"got page 1"`.
- Same phone sends a 2nd image within the seal window → existing batch reused, `ord=2`.
- Non-whitelisted phone sends image → reply `"isn't approved"`, no batch created.
- Per-day cap: 4th batch from same phone in 24h → reply `"You've submitted enough today"`, no media downloaded (assert metadata mock NOT called).

### 12.3 `tests/test_intake_seal.py`
- Set `IMAGE_BATCH_SEAL_SECONDS=0.001` so the test doesn't sleep.
- Open a batch with 2 items. Force `last_item_at = now() - 1 minute`. Mock `app.ocr.ocr_paper` to return a canned `OcrPaperExtraction(course_code="MTH102", questions=[OcrQuestion(number=1,text="x")])`. Mock `app.embeddings.embed_many` to return `[[0.0]*768]`.
- Call `sweep_and_seal`. Assert one `pending_papers` row was created with `source='wa_intake'`, batch transitioned to `status='ocr_done'`, `sealed_at` is set, an `intake_notifications` row exists for the phone.
- OCR returning `error` path → batch becomes `status='failed', failure_reason='ocr_empty'`, contributor gets a *different* notification.

### 12.4 `tests/test_pipeline.py` extension
- `test_pipeline_image_from_non_whitelisted`: mock `whatsapp.get_media_metadata` (must NOT be called). Send `WAMessage(type="image", image=WAImage(id="m1", mime_type="image/jpeg"))` from `2348999999999`. Assert reply text contains `"isn't approved"` and outcome is `not_whitelisted`.

---

## 13. RUNBOOK / README updates

### `RUNBOOK.md`
- New §8: **Manage uploaders.** `python -m admin.uploaders allow 234813...`. "Only allow numbers you trust — they can submit photos directly to the curation queue."
- New §9: **Stuck batches.** "If a contributor's photo never lands in `pending_papers`: `python -m admin.batches list --phone 234...` to see status. Common stuck states: `deferred_ocr` (drain via `admin batches seal <id>`), `failed` with `unknown_course` (add the course via `admin courses add` then re-run `admin batches seal`)."

### `README.md`
- Add one paragraph under "Daily ops": "Photo contributions: only whitelisted numbers can submit. Add via `admin uploaders allow`. Photos arrive in the curation queue; review via `admin curate`."

---

## 14. Cost recheck

Per-image cost (when actually sealed):
- Pro vision OCR: same as Phase 2 ingestion, ~$0.012 per paper average.
- Embeddings: ~$0.00005 per paper.
- Net: ~$0.012 per submitted batch.

The `image_intake_ocr_per_day=100` cap means worst-case daily intake cost is **~$1.20**, or **~$36/month** if abused — over the $15 ceiling. Mitigation: **default the cap to 30** in production (override via env) until intake patterns are observed. The cap default in `Settings` stays at 100 for dev convenience; document the production override in `RUNBOOK.md` §8.

Steady-state cost without intake stays at ~$9.50/month per `PRD.md §5.3`.

---

## 15. Non-goals reaffirmed

The execution agent must **not** add any of the following:

- A queue, scheduler, BackgroundTasks, asyncio task, or thread for sealing.
- Cloud Tasks, Pub/Sub, Cloud Scheduler, Eventarc, Workflows.
- A `users` table or any read of inferred profile data.
- BM25 / hybrid retrieval / reranker.
- A web UI for whitelist or batches management.
- An auto-OCR-retry loop. Failed batches stay failed; admin manually triggers `admin batches seal` to retry.
- A migration tool. Migrations stay hand-applied SQL.
- Templated WhatsApp messages.
- Caching of `is_whitelisted` results — admin changes must take effect immediately.

If any become tempting, stop and amend `PHASE_5_SPEC.md` first.

---

## 16. Definition of Done (Phase 5)

A maintainer (Hafeedh or Ibrahim) on his laptop:

1. Pulls `master`, runs `pip install -r requirements.txt`. No errors.
2. Applies `migrations/005_phase5.sql`. `\d uploaders`, `\d image_batches`, `\d image_batch_items`, `\d intake_notifications` all exist with the right columns.
3. Runs `python -m admin.uploaders allow 2348131234567 --name "Yusuf"`. Then `python -m admin.uploaders list` shows the row.
4. From `2348131234567`, sends 3 images of a CSC305 paper to the bot in quick succession. Bot replies `"got page 1"`, `"got page 2"`, `"got page 3"` — within 5 s each on weak signal.
5. Waits 90 s, sends any text message. The bot acks the text and (within the same request) seals batch B. The next response back to `2348131234567` (within seconds, from the next bot interaction) is `"Got 3 pages. Submitted for review..."`.
6. `python -m admin.curate` shows the new pending paper with `source='wa_intake'`. Approve it.
7. From any other phone, send `"CSC305 harmattan 2024"` → receives the approved PDF.
8. Sends an image from a non-whitelisted phone → receives `"This number isn't approved..."` text. `python -m admin.batches list --phone 234...` shows zero batches for that phone.
9. `pytest -q` passes including every Phase 5 test in §12.
10. `make smoke` still prints `SMOKE OK`.
11. Total monthly cost remains ≤ $15 with `image_intake_ocr_per_day=30` set in production.

When all 11 are green, Phase 5 is implementation-complete and ready for the next-phase planning cycle.
