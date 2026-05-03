# PRD: PAU MSA Past Paper Bank (WhatsApp + AI)

**Codename:** `msa-paperbank`
**Author:** Hafeedh (Deputy Amir, PAU MSA; Founder, Kaide Labs)
**Status:** v1.1 — pre-edited for scope discipline; pending Step 1C dependency modernization
**Audience:** AI coding agents executing Phases 1–3, future MSA tech-lead successors
**Last revised:** May 4, 2026

**Pre-edit changelog (v1.0 → v1.1):**
- §3.1, §3.2, §5.1, §5.2, §5.3, §8.2: cut Pub/Sub + Service B architecture; single-service preserved through V1
- §3.1 F4, §3.2: multi-image stitching deferred to V1.1; V1 admin imports use filename conventions
- §9.2: tightened active-risk heuristic from `year >= 2023` to `exam_year >= current_year - 1`
- §9.1, §8.3, §11.3: Drive corpus count corrected from "~1,300" to verified 782
- §7.4, §3.1, Appendix B, §11.2, §11.3: model versions updated to locked stack (Gemini 3.1 Pro Preview + Gemini 3 Flash); pricing flagged as placeholder pending Step 1C verification

---

## 1. Project Overview & Mission

### 1.1 Mission
Sadaqah jariyah project. Build a WhatsApp-accessible past-paper retrieval system for PAU students (entry vector: the Muslim Students' Association). Optimise for **durability without the original author**, not for feature breadth.

### 1.2 Hard constraints
| Constraint | Value |
|---|---|
| Solo dev | Hafeedh (20 y/o, weekend chunks only) |
| Effort budget | Phase 1: 12h · Phase 2: 12h · Phase 3: 8h. Total ≤ 36h |
| Cloud budget | $1,000 GCP free credits, must run free-tier-shaped after credits expire |
| Locale | Lagos, Nigeria. Power outages, NG mobile networks, no card-payment friction tolerated for end users |
| Engineering taste | Salafi-Muslim engineering: boring-reliable > cutting-edge. Postgres > Mongo. Sync > async until forced. Cron > queues until forced |
| Failure mode tolerance | Webhook timeout on a 4 MB image during beta = acceptable. Distributed-systems debugging on weekend 1 = unacceptable |

### 1.3 What this is NOT
- Not a chatbot platform.
- Not a study-mentor.
- Not a community tool.
- Not a Twilio-wrapped product (Twilio is replaced by direct Meta Cloud API).

---

## 2. User Personas

### 2.1 Aisha — The Cramming Student (primary, ~95% of traffic)
- 200-level Computer Science. Exam in 6 days.
- Owns a phone with 2 GB RAM, 30% battery, 1 bar of MTN signal.
- Will not install an app. Will not sign up. Will not pay.
- Saves the MSA number, sends `"DSA past papers"`, expects a reply with PDF or list within 30 s.
- Friction tolerance: **one** failed message before abandonment.

### 2.2 Yusuf — The Paper Contributor (V1.1+, not V1)
- 300-level Engineering. Has 12 photos of a CA from his last semester.
- Sends them in a WhatsApp burst. Expects acknowledgement.
- In **V1**: contributions go to a Drive folder Hafeedh imports manually. **No live ingestion path.**
- In **V1.1+**: photos hit a `pending_submissions` queue → reviewed by Tech Lead via CLI → approved or rejected.

### 2.3 Ibrahim — The MSA Tech-Lead Successor (durability persona)
- Hafeedh's hand-picked successor. 200-level. Knows Python, has never touched GCP.
- Reads `README.md`. Runs `python admin.py`. Done.
- **Pass criterion:** can add a paper, retire a paper, run the curation gate without opening the GCP console.
- **Fail criterion:** any operation requires Cloud Console clicks → architecture has failed durability test.

---

## 3. V1 Scope

### 3.1 IN
| # | Feature |
|---|---|
| F1 | Inbound WhatsApp message → Meta Cloud API webhook → Cloud Run Service A |
| F2 | Gemini 3 Flash intent routing (search vs help vs unknown) — exact model ID + pricing verified in Step 1C |
| F3 | Photo ingestion → Cloud Storage → Gemini 3.1 Pro Preview OCR → structured `paper_questions` rows — exact model ID + pricing verified in Step 1C |
| F4 | (DEFERRED to V1.1) Multi-image stitching — `image_batches` schema present in V1 for future use, no stitching logic in V1. Drive imports use filename-based grouping conventions (`CSC201-CA1-q1.jpg`, `CSC201-CA1-q2.jpg`) for multi-image papers |
| F5 | OpenCV preprocessing (grayscale → deskew → adaptive threshold) before OCR |
| F6 | Vertex AI `gemini-embedding-001` @ 768-dim embedding |
| F7 | pgvector cosine retrieval on `paper_questions.embedding` |
| F8 | Reply with paper list + Cloud Storage signed URL to PDF |
| F9 | Bulk Drive importer (`scripts/drive_import.py`) with mandatory curation gate |
| F10 | Admin CLI (`admin.py`) — add/retire/list/curate/audit |
| F11 | `message_log` for audit |

### 3.2 OUT (deferred — see §14)
- AI summarisation
- Practice mode / quizzing / state machines
- Career or study mentor
- Community coordination
- Hybrid BM25 + pgvector RRF (pg_bm25 unavailable on Cloud SQL)
- User-facing photo contribution (V1.1)
- Multi-image stitching with timing windows (V1.1, paired with user-facing photo contribution)
- Personalisation in responses (V1.2)
- Pub/Sub queue (V2 only, if real scale demands it)
- Webhook signature mTLS pinning (Meta CA migration handled at Phase 1 end — see §12)

---

## 4. User Flows (ASCII)

### 4.1 Onboarding
```
[Hafeedh announces at Jumu'ah] -> [student saves number] -> [sends "hi"]
                                                                |
                                       Service A receives webhook
                                                                |
                                  Gemini Flash-Lite routes -> intent=GREET
                                                                |
                  Reply: "Salam. Send a course code (e.g. CSC 201) or a question."
                                                                |
                                              insert into users(phone_number)
```
No signup. No OTP. The act of messaging IS registration.

### 4.2 Retrieval (95% path)
```
student: "DSA past papers 2024"
      |
      v
+----------------------+         +-------------------+
| Service A (webhook)  | <-----> |  Gemini Flash-Lite|  intent=SEARCH, course?=DSA, year?=2024
|  - parse webhook     |         +-------------------+
|  - ack 200 in <2s    |
+----------------------+
      |
      v
+----------------------+         +-------------------+
| embed(query)         | -----> | Vertex Embedding  | 768-dim vector
+----------------------+         +-------------------+
      |
      v
+----------------------+
| pgvector ANN search  |   ORDER BY embedding <=> $1 LIMIT 5
| + course_code filter |
+----------------------+
      |
      v
+----------------------+
| build reply text +   |  signed URL valid 7 days
| GCS signed URL list  |
+----------------------+
      |
      v
[POST /messages to Meta Cloud API] -> student receives reply
```

### 4.3 Ingestion (admin-triggered V1; user-triggered V1.1+)
```
[Hafeedh runs: python admin.py import-drive --folder <id>]
      |
      v
[list Drive files]
      |
      v
[FOR EACH file or image-batch]
      |
      +--> [download to /tmp]
      |
      +--> [stitch heuristic: filenames CA1-q1.jpg, CA1-q2.jpg -> one batch]
      |
      +--> [OpenCV preprocess: grayscale, deskew, adaptive threshold]
      |
      +--> [Gemini 2.5 Pro vision OCR, JSON schema output]
      |       returns: {course_code, year, session, questions: [text...]}
      |
      +--> [is_active_risk = (year >= 2023) AND (course_code unique in DB)]
      |
      +--> [if is_active_risk: write to staging, BLOCK on curation gate]
      |    [else: insert into past_papers + paper_questions]
      |
      +--> [embed each question -> paper_questions.embedding]
      |
      +--> [upload original/PDF to gs://msa-papers/raw/{paper_id}.pdf]
```

### 4.4 Implicit profile update
Background, write-only side-effect of every retrieval:
```
on each SEARCH intent:
    UPDATE users
       SET interaction_count = interaction_count + 1,
           inferred_courses  = jsonb_set(inferred_courses, course_code,
                               COALESCE(...,0)+1)
     WHERE phone_number = $1;
```
**V1 reads `inferred_courses` for nothing**. It's collected for V1.2 personalisation. Documented here so the schema isn't churned later.

---

## 5. Technical Architecture

### 5.1 Stack diagram
```
+------------------+    HTTPS POST   +-----------------------------+
| WhatsApp users   |  ------------>  |  Meta Cloud API             |
+------------------+                 |  graph.facebook.com/v23.0   |
                                     +--------------+--------------+
                                                    | webhook (HTTPS)
                                                    v
+--------------------------------------------------------------+
|  CLOUD RUN — Service A  (sync webhook + inline OCR)          |
|  Python 3.12 / FastAPI / uvicorn / 1 vCPU / 512 MiB          |
|  scale-to-zero, max 5 instances, concurrency 20              |
|  -- verifies X-Hub-Signature-256                             |
|  -- ACKS 200 within 2s (Meta retries up to ~36h on non-200)  |
|  -- routes via Gemini 3 Flash                                |
|  -- OCR runs inline via FastAPI background task pattern      |
|  -- single service throughout V1; no Pub/Sub, no Service B   |
+----+--------------------+--------------------+----------------+
     |                    |                    |
     | SQL                | Embeddings         | Vision/OCR
     v                    v                    v
+-----------+   +-------------------+   +-------------------+
| Cloud SQL |   | Vertex AI          |   | Gemini 2.5 Pro    |
| Postgres  |   | gemini-embedding-  |   | (vision)          |
| 16        |   | 001 @ 768 dims    |   | structured-output |
| db-f1-    |   +-------------------+   +-------------------+
| micro,    |
| pgvector, |   +-------------------+
| HNSW      |   | Cloud Storage     |
+-----------+   | gs://msa-papers/  |   raw/<paper>.pdf
                +-------------------+   media/<media_id>.jpg

```

**Single-service architecture preserved through V1.** No Pub/Sub. No Service B. OCR runs inline within Service A with the webhook ack happening in <2s via a background task pattern. At projected MSA scale (≤8 msgs/hour peak), splitting into two services and a queue is over-engineering that adds dead-letter handling, idempotency keys, ordering edge cases, and a separate deploy unit — none of which solve real problems at this volume and all of which raise the durability burden on Ibrahim.

### 5.2 Service boundaries
| Service | Trigger | Latency budget | Failure mode |
|---|---|---|---|
| A (`paperbank-web`) | Meta webhook POST | ≤ 2 s ack, OCR continues in background task | OCR timeouts on >2 MB images logged to `pending_submissions` for retry; webhook always acks 200 |
| Admin CLI | manual | n/a | Hafeedh's terminal |

### 5.3 Why no queue, period (V1)
A queue introduces: dead-letter handling, idempotency keys, ordering edge cases, separate deploy unit. **None of those bugs are fixable within the V1 effort budget.** At projected MSA scale (6,000 inbound msgs/month, ≤8 msgs/hour peak, OCR happens during admin-triggered Drive imports not at user-message time), a single service handling webhook + retrieval inline is correct sizing. `message_log.wamid` UNIQUE handles Meta retry idempotency. Pub/Sub revisits in V2 only if real scale demands it. **For Ibrahim: one service is one thing to debug; two services + a queue is four.**

---

## 6. Database Schema (finalised)

```sql
-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fuzzy course code match

-- Users (zero-friction; row created on first message)
CREATE TABLE users (
  phone_number       VARCHAR(20)  PRIMARY KEY,         -- E.164, no '+'
  academic_level     INT,                              -- 100/200/300/400, nullable
  major              VARCHAR(100),
  inferred_courses   JSONB        DEFAULT '{}'::jsonb, -- {"CSC201": 7, "MTH202": 2}
  user_summaries     TEXT,                             -- V1.2 use only
  interaction_count  INT          DEFAULT 0,
  created_at         TIMESTAMPTZ  DEFAULT NOW(),
  last_seen_at       TIMESTAMPTZ  DEFAULT NOW()
);

-- Papers
CREATE TABLE past_papers (
  paper_id        SERIAL       PRIMARY KEY,
  course_code     VARCHAR(20)  NOT NULL,               -- normalised: 'CSC201'
  course_title    TEXT,
  exam_year       INT,
  exam_session    VARCHAR(20),                         -- 'first'|'second'|'CA1'|'CA2'|'exam'
  is_active_risk  BOOLEAN      DEFAULT FALSE,          -- year>=2023 AND singleton course
  is_retired      BOOLEAN      DEFAULT FALSE,          -- soft-delete (admin retire_paper)
  raw_file_url    TEXT,                                -- gs:// URL
  pdf_url         TEXT,                                -- generated combined PDF
  source          VARCHAR(20)  DEFAULT 'drive_import', -- 'drive_import'|'user_submission'|'manual'
  curated_by      VARCHAR(64),                         -- e.g. 'hafeedh' / 'amir-2027'
  curated_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX idx_papers_course   ON past_papers(course_code);
CREATE INDEX idx_papers_active   ON past_papers(course_code) WHERE is_retired=FALSE;
CREATE INDEX idx_papers_course_trgm ON past_papers USING gin (course_code gin_trgm_ops);

-- Questions (chunk = retrievable unit)
CREATE TABLE paper_questions (
  question_id   SERIAL       PRIMARY KEY,
  paper_id      INT          REFERENCES past_papers(paper_id) ON DELETE CASCADE,
  question_no   INT,
  question_text TEXT         NOT NULL,
  embedding     VECTOR(768),                           -- gemini-embedding-001 truncated via MRL
  created_at    TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX idx_qn_paper     ON paper_questions(paper_id);
CREATE INDEX idx_qn_embedding ON paper_questions
  USING hnsw (embedding vector_cosine_ops)
  WITH (m=16, ef_construction=64);

-- Image batches (multi-image stitching; one logical paper from N photos)
CREATE TABLE image_batches (
  batch_id        SERIAL       PRIMARY KEY,
  phone_number    VARCHAR(20),                         -- nullable for admin imports
  paper_id        INT          REFERENCES past_papers(paper_id) ON DELETE SET NULL,
  status          VARCHAR(20)  DEFAULT 'open',         -- 'open'|'sealed'|'processed'|'failed'
  opened_at       TIMESTAMPTZ  DEFAULT NOW(),
  sealed_at       TIMESTAMPTZ,                         -- 90 s after last add
  failure_reason  TEXT
);
CREATE TABLE image_batch_items (
  item_id     SERIAL PRIMARY KEY,
  batch_id    INT REFERENCES image_batches(batch_id) ON DELETE CASCADE,
  gcs_path    TEXT NOT NULL,                           -- gs://msa-papers/media/<wamid>.jpg
  wa_media_id TEXT,
  ord         INT,
  added_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_batch_phone_open ON image_batches(phone_number) WHERE status='open';

-- Pending submissions (V1.1+; table created in V1, never written-to in V1)
CREATE TABLE pending_submissions (
  submission_id SERIAL       PRIMARY KEY,
  phone_number  VARCHAR(20),
  batch_id      INT          REFERENCES image_batches(batch_id),
  ocr_payload   JSONB,                                 -- Gemini Pro extraction output
  status        VARCHAR(20)  DEFAULT 'awaiting_review',
  reviewer      VARCHAR(64),
  reviewed_at   TIMESTAMPTZ,
  decision      VARCHAR(20),                           -- 'approved'|'rejected'|'duplicate'
  notes         TEXT,
  created_at    TIMESTAMPTZ  DEFAULT NOW()
);

-- Audit log (idempotency + debugging + future personalisation)
CREATE TABLE message_log (
  log_id        BIGSERIAL    PRIMARY KEY,
  wamid         TEXT         UNIQUE,                   -- Meta's wa.id - dedupes retries
  phone_number  VARCHAR(20),
  direction     VARCHAR(10)  CHECK (direction IN ('in','out')),
  msg_type      VARCHAR(20),                           -- 'text'|'image'|'sticker'|'unknown'
  message_body  TEXT,
  intent        VARCHAR(30),                           -- 'SEARCH'|'GREET'|'HELP'|'UNKNOWN'
  created_at    TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX idx_log_phone_time ON message_log(phone_number, created_at DESC);
```

### 6.1 Schema rationale (changes vs spec baseline)
| Field added | Reason |
|---|---|
| `users.inferred_courses` JSONB | Original spec was TEXT; JSONB lets us increment course-code counters atomically without parsing |
| `past_papers.is_retired` | Mandatory for admin `retire_paper` (per spec). Soft-delete preserves history |
| `past_papers.curated_by/at`, `source` | Audit trail required for academic-integrity review |
| `paper_questions.question_no` | Enables stable ordering when stitching back into PDF |
| `image_batches` + `image_batch_items` | Multi-image stitching is REQUIRED per spec; this is the canonical model |
| `pending_submissions` | Table exists in V1 but unused; prevents schema migration in V1.1 |
| `message_log.wamid UNIQUE` | Idempotency: Meta retries deliver duplicate webhooks; this prevents double-processing |

---

## 7. API Contract

### 7.1 Inbound: Meta Cloud API → Service A

**Verification (one-time, on webhook configuration):**
```
GET /webhook?hub.mode=subscribe&hub.verify_token=<APP_TOKEN>&hub.challenge=<N>
-> 200 with body: <N>   (echo the challenge back as plain text)
```

**Inbound text message:**
```json
POST /webhook   (Headers: X-Hub-Signature-256: sha256=...)
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "<WABA_ID>",
    "changes": [{
      "field": "messages",
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number":"234XXXX","phone_number_id":"<PNID>"},
        "contacts": [{"profile":{"name":"Aisha"},"wa_id":"234813XXXXXXX"}],
        "messages": [{
          "from": "234813XXXXXXX",
          "id": "wamid.HBg...",
          "timestamp": "1746360000",
          "type": "text",
          "text": {"body":"DSA past papers 2024"}
        }]
      }
    }]
  }]
}
```

**Inbound image:**
```json
"messages":[{
  "from":"234813XXXXXXX","id":"wamid....","timestamp":"...",
  "type":"image",
  "image":{"mime_type":"image/jpeg","sha256":"...","id":"<MEDIA_ID>"}
}]
```

**HARD RULES**
1. **Always return HTTP 200 within 2 s.** Meta retries non-200 with exponential backoff up to ~36 h. A retry storm is catastrophic.
2. **Always validate `X-Hub-Signature-256`** with `hmac.compare_digest(...)`. App secret stored in Secret Manager.
3. **Always dedupe by `messages[i].id` (wamid)** via `INSERT ... ON CONFLICT (wamid) DO NOTHING`.
4. **`entry[]`, `changes[]`, `messages[]` are arrays.** Never index `[0]` blindly — iterate.
5. **Webhook payloads can be ≤ 3 MB.**

### 7.2 Media download (2-hop, time-critical)

```
Step 1: GET https://graph.facebook.com/v23.0/<MEDIA_ID>
  Authorization: Bearer <PERMANENT_TOKEN>
  -> { "url":"https://lookaside.fbsbx.com/...", "mime_type":"image/jpeg", "file_size":..., "sha256":"...", "id":"..." }
  ⚠ The "url" expires in ~5 minutes.

Step 2: GET <url>
  Authorization: Bearer <PERMANENT_TOKEN>     # token required even on lookaside URL
  Accept: */*
  -> binary body
  ⇒ stream-write to gs://msa-papers/media/<wamid>.jpg
```

### 7.3 Outbound: Service A → Meta Cloud API
```
POST https://graph.facebook.com/v23.0/<PHONE_NUMBER_ID>/messages
Authorization: Bearer <PERMANENT_TOKEN>
Content-Type: application/json

{
  "messaging_product":"whatsapp",
  "recipient_type":"individual",
  "to":"234813XXXXXXX",
  "type":"text",
  "text":{"preview_url":true,
          "body":"Found 3 DSA papers (CSC305):\n2024 Exam — https://...\n2024 CA2  — https://...\n2023 Exam — https://..."}
}
```
- **Inside the 24 h Customer Service Window** (CSW): free-form text/media replies are FREE under Meta's PMP model (effective 2025-07-01). The MSA bot only ever replies inside CSW → **template messages are not used**.
- Template approval and the marketing/utility/auth pricing categories are therefore irrelevant to V1.
- Failure semantics: HTTP 200 with `messages[0].id` = success. 4xx = our bug. 5xx = retry once with 2 s backoff.

### 7.4 Gemini calls

**Routing (Flash, sync):**
```python
# Stack-locked: Gemini 3 Flash for routing/intent classification.
# Step 1C will verify exact API model string + pricing via live Nia lookup.
model = "gemini-3-flash"  # placeholder; verify exact model ID via Vertex AI catalog in Step 1C
prompt = f"""Classify the message. Output JSON only.
schema: {{intent: "SEARCH"|"GREET"|"HELP"|"UNKNOWN",
          course_code: string|null, year: int|null}}
Message: "{user_text}"
"""
# Pricing: TO BE VERIFIED in Step 1C against current Vertex AI / Gemini API pricing.
# Original spec assumed ~$0.000024 per call at gemini-2.5-flash-lite rates;
# Gemini 3 Flash pricing must be confirmed before §11 cost model is final.
```

**OCR (Pro, inline within Service A or sync within admin Drive importer):**
```python
# Stack-locked: Gemini 3.1 Pro Preview for OCR / vision / structured extraction.
# Step 1C will verify exact API model string + pricing + Vertex AI region availability.
model = "gemini-3.1-pro-preview"  # placeholder; verify exact model ID in Step 1C
# Pricing: TO BE VERIFIED in Step 1C against current Vertex AI pricing.
# Original spec assumed ~$0.005 - $0.02 per paper at gemini-2.5-pro rates;
# Gemini 3.1 Pro Preview pricing must be confirmed before §11 cost model is final.
prompt = """Extract from this exam paper image.
Return JSON only matching schema:
{course_code: str, course_title: str|null, exam_year: int|null,
 exam_session: "first"|"second"|"CA1"|"CA2"|"exam"|null,
 questions: [{number: int, text: str}]}
If unreadable, return {"error": "<reason>"}.
"""
```

**Embeddings (Vertex):**
```python
# text-embedding-004 was DEPRECATED 2026-01-14. Spec is updated:
model = "gemini-embedding-001"
# 3072-dim native; truncate via MRL to 768 to keep schema VECTOR(768).
# Pricing: $0.15 /M tokens.
# IMPORTANT: gemini-embedding-001 accepts ONE input per request — batch via concurrent calls (asyncio.gather, sem=8).
```

---

## 8. Build Plan

### 8.1 Phase 1 — Weekend 1 (~12 h)

| Hour | Deliverable |
|---|---|
| 0–1 | GCP project bootstrap: enable Cloud Run, Cloud SQL, Vertex AI, Secret Manager, Cloud Storage. Create `db-f1-micro` Postgres 16 instance (~$10.60/mo). Install pgvector + pg_trgm. Apply schema (§6) |
| 1–2 | Meta App: create Business app → add WhatsApp product → get test number → set verify token in Secret Manager. **Trigger Hafeedh's parallel verification track (§8.4) NOW** |
| 2–5 | Service A skeleton: FastAPI, `GET /webhook` verify, `POST /webhook` sig-check + 200-ack-fast, log to `message_log`. Deploy to Cloud Run. Configure Meta webhook URL |
| 5–7 | Gemini 3 Flash intent router (model ID to be verified in Step 1C). Hardcoded retrieval: `SELECT * FROM past_papers WHERE course_code ILIKE $1 LIMIT 5`. No vectors yet. Insert ~10 manually-OCRed test papers via psql |
| 7–10 | Outbound message sender. End-to-end smoke: Hafeedh's phone → bot replies with paper list. Test from 3 NG carrier numbers (MTN, Glo, Airtel) |
| 10–12 | Logging cleanup, README first draft, commit secrets to Secret Manager not git, deploy with `--min-instances=0 --max-instances=5` |

**Phase 1 highest risk:** WABA verification stalls and the test number's 24 h CSW expires before testing. Mitigation: keep replying to your own test message every <24 h; verification track runs IN PARALLEL.

### 8.2 Phase 2 — Weekend 2 (~12 h)

| Hour | Deliverable |
|---|---|
| 0–2 | OpenCV preprocessing pipeline: `cv2.imread` → grayscale → `cv2.fastNlMeansDenoising` → deskew via Hough lines → `cv2.adaptiveThreshold(GAUSSIAN, BLOCK=31, C=10)`. Save preprocessed copies to GCS. Standalone module callable from admin path |
| 2–3 | Drive importer skeleton: `scripts/drive_import.py` — auth via service account, walk folder tree, dedupe by SHA256. Plugs into the OCR pipeline below |
| 3–6 | Gemini 3.1 Pro Preview vision OCR with JSON schema response. Insert paper + questions. Generate combined PDF (`reportlab`) → upload to GCS. Inline within the webhook handler via FastAPI background tasks for user-side OCR; synchronous within `drive_import.py` for admin bulk imports |
| 6–8 | Vertex AI `gemini-embedding-001` integration (truncated to 768-dim via MRL). Embed each ingested question. Replace Phase 1 hardcoded ILIKE retrieval with `ORDER BY embedding <=> query_emb LIMIT 5` joined to `past_papers` |
| 8–10 | Curation gate logic: Drive imports with `is_active_risk=TRUE` route to `pending_submissions` rather than `past_papers`. Manual review path scaffolded (admin CLI command in Phase 3) |
| 10–11 | Backfill embeddings for Phase-1 test papers; smoke test the full ingestion-to-retrieval loop |
| 11–12 | Logging cleanup, error path coverage, deploy verified |

**Phase 2 highest risk:** OCR quality on the actual Drive corpus is unknown until Phase 2 hours 3-6. Gemini 3.1 Pro Preview hasn't been benchmarked extensively on Nigerian academic papers with handwritten content. Mitigation: OCR pipeline is a standalone module — if quality is poor, swap to a different model or add stronger preprocessing without affecting the rest of the architecture.

### 8.3 Phase 3 — Weekend 3 (~8 h)

| Hour | Deliverable |
|---|---|
| 0–3 | `scripts/drive_import.py` — auth via service account, walk Drive folder tree, dedupe by SHA256, push each through Phase-2 pipeline. Curation gate: any `is_active_risk=TRUE` paper goes to `pending_submissions` — NOT inserted live until reviewer approves |
| 3–6 | `admin.py` CLI (§13). All commands documented in README plain English |
| 6–7 | Implicit profile inference: piggyback on retrieval flow — write-only updates to `users.inferred_courses` |
| 7–8 | Soft launch to 10 MSA execs. Collect bug reports. Publish `OPERATIONS.md` |

**Phase 3 highest risk:** the Drive corpus has 782 verified files, ~50-60% are likely 2025-2026 (active-risk under the new heuristic) → ~400 papers needing manual review. **Mitigation:** Hafeedh + one MSA exec do a single 90-120 min batch review session before public launch using the paginated `admin.py curate` UI. Active-risk papers from the *current academic session* (2025-2026) get a `held_until` flag set manually based on PAU calendar; the curate command surfaces only papers past their hold date.

### 8.4 Parallel verification track (Week 1)
Runs CONCURRENTLY with Phase 1. Not blocking on the build.

| Day | Action |
|---|---|
| Mon | Create Meta Business Portfolio. Enable 2FA. Enter MSA name + PAU address |
| Mon | Add WhatsApp product → submit display name `PAU MSA Papers` (avoid generic "Bot"/"Official"; approval ~2-4 h, sometimes 24 h) |
| Tue | Submit business verification with whatever documentation is achievable: PAU MSA constitution, signed letter from Amir on PAU letterhead, Hafeedh's NIN. **If MSA is not CAC-registered**: business verification may be denied → fall back to unverified mode |
| Wed–Fri | Monitor status. **Unverified path is acceptable for V1** because: (a) we never send templates, (b) all replies are inside the 24 h CSW (FREE), (c) the 250 msgs/day cap on unverified WABAs applies to *business-initiated* messages — irrelevant to us |
| Anytime | If verification denied, register a CAC "Incorporated Trustees" entity for "PAU MSA" (~₦40k, ~2 weeks) — but this is V1.1 work, NOT a Phase-1 blocker |

**Decision:** Ship V1 on unverified WABA. CSW-only replies have no rate-limit pain.

---

## 9. Content Sourcing & Curation

### 9.1 Sources, in priority order
1. **Drive corpus (bootstrap, V1):** 782 items inventoried (verified) — SMC/ISMS, MEE/EEE/GET, CSC, PHY, CHM, GST. Verdict: STRONG bootstrap.
2. **MSA exec uploads (V1):** Hafeedh ingests via `admin.py add-paper` after manual receipt.
3. **User photo submissions (V1.1):** disabled in V1. Table exists; webhook handler ignores image messages from non-admin numbers in V1.

### 9.2 Curation gate (mandatory; cannot be bypassed)
```
RULE: A paper enters `past_papers` (live, retrievable) ONLY IF
      (NOT is_active_risk) OR (curated_by IS NOT NULL).

is_active_risk ::= (exam_year >= EXTRACT(YEAR FROM NOW()) - 1)
                   AND (course_code count in past_papers <= 1)
                   AND (source != 'manual_admin_override')
```
- The `current_year - 1` bound flags papers from the current academic year and the immediately prior year — the actual reuse risk surface. Older papers (e.g., 2023 papers in 2026) are no longer at meaningful reuse risk and skip the gate.
- Any paper from the *current academic session* (regardless of year math): held until 30 days after the session ends. This is enforced by a `held_until` column populated at ingest based on the `exam_session` and current PAU calendar (manual flag in V1; automated calendar lookup is V1.1 work).
- Curation is performed via `admin.py curate` (§13.4) — paginated review.
- No backdoor: even Hafeedh's bulk Drive import respects the gate.

### 9.3 Submission (V1.1 path, designed but disabled in V1)
```
user image -> stitch -> OCR -> staging payload -> pending_submissions(status='awaiting_review')
                                                     |
                                       admin.py review-pending
                                                     |
                                          approve | reject | mark-duplicate
                                                     |
                                  approve -> insert past_papers (curated_by=reviewer)
```

---

## 10. Academic Integrity Policy

| # | Rule |
|---|---|
| AI-1 | No paper is indexed without a curation gate pass. |
| AI-2 | No mechanism exists for students to publish papers to the live DB. Submissions land in `pending_submissions`. |
| AI-3 | The system surfaces past papers for **revision**. It does not generate new exam-style content in V1. (V2 summarisation is explicitly behind this line.) |
| AI-4 | Active-use risk: any paper from a *currently-running* semester is quarantined. The system never serves a paper that may be re-used unaltered. |
| AI-5 | Lecturer-flagged retraction: `admin.py retire-paper <paper_id>` is the documented removal path. Sets `is_retired=TRUE`; retrieval filters exclude it within the next request (no caching layer to invalidate). |
| AI-6 | All retrievals are logged in `message_log` (phone_number, intent, papers returned). MSA exec board can audit. |
| AI-7 | The bot does not reveal lecturer marking schemes, model answers, or solutions. V1 returns paper PDFs/question text only. |

---

## 11. Cost Model

### 11.1 Adoption scenario (realistic)
- **200 active users** in exam season (≈ 1/3 of MSA + word-of-mouth).
- **30 messages/user/month** average → **6,000 inbound msgs/month**.
- 80% text retrieval, 20% photo (V1.1; ignore for V1 cost — all photos are admin-side bulk imports).
- 1.5 outbound messages per inbound → **9,000 outbound msgs/month**.
- All replies inside 24 h CSW → **WhatsApp $0**.

### 11.2 Per-message LLM cost (V1 steady state) — TO BE RE-VERIFIED IN STEP 1C
| Per inbound text msg | Model | Tokens (in/out) | Cost (placeholder, must verify) |
|---|---|---|---|
| Intent route | gemini-3-flash | 80 / 40 | $0.000024* |
| Embed query | gemini-embedding-001 | 30 | $0.0000045 |
| (Reply construction is templated — no LLM call) | — | — | — |
| **Total** | | | **≈ $0.00003 per msg* (placeholder)** |

\*Original cost figures were calculated against Gemini 2.5 Flash-Lite pricing. Step 1C must re-verify all per-token rates against Gemini 3 Flash and Gemini 3.1 Pro Preview before this table can be considered accurate.

**Monthly LLM cost @ 6,000 msgs (placeholder):** ~$0.18. Re-verify after Step 1C.

### 11.3 OCR cost (one-time bulk import + occasional admin adds) — TO BE RE-VERIFIED IN STEP 1C
- 782 papers (verified Drive count) × avg 2 photos/paper = ~1,564 image OCRs.
- Per-image Gemini 3.1 Pro Preview: pricing TBD — Step 1C verifies. *Original spec assumed ~1290 image tokens + ~300 text tokens in, ~500 tokens out → ~$0.008/image at gemini-2.5-pro rates.*
- **Bulk import one-time cost (placeholder): ~$12-13 at original assumptions.** Re-verify after Step 1C confirms Gemini 3.1 Pro Preview pricing.

### 11.4 Infrastructure
| Line | Spec | Monthly |
|---|---|---|
| Cloud SQL Postgres | db-f1-micro, 10 GB SSD, no HA | $10.60 |
| Cloud Run Service A | scale-to-zero, ~150k req/mo, well within free tier | $0.00 |
| Cloud Storage | ~3 GB papers + thumbs + media | $0.07 |
| Vertex AI / Gemini API | per §11.2 (placeholder pending Step 1C verification) | $0.18 |
| Secret Manager | 6 secrets, 10k accesses | $0.06 |
| Egress (NG) | ~2 GB/mo | $0.24 |
| **WhatsApp Cloud API** | service-window-only | **$0.00** |
| **Total recurring** | | **≈ $11.15 / month** |

### 11.5 GCP credit runway
$1,000 credits / $11.15 per month ≈ **89.7 months ≈ 7.5 years**. Credits typically expire at 90 days or 1 year — **assume 90 days, then steady-state $11/mo from MSA budget or Hafeedh's pocket.** Annual burn ~₦210k at ₦1,600/$.

### 11.6 Sensitivity
- 1,000 active users instead of 200: ~$1/mo more (LLM dominates and is small).
- WhatsApp cost only emerges if we send templates (re-engagement past 24 h). **Don't.**

---

## 12. Maintenance & Operations

### 12.1 Failure catalogue
| Symptom | Cause | Fix | Time |
|---|---|---|---|
| Bot stops replying | Permanent token rotated; webhook signature changed | `gcloud secrets versions add WHATSAPP_TOKEN ...`; redeploy Service A | 5 min |
| All webhooks failing TLS | Meta CA migration (was 2026-03-31) | Update trust store: pull `meta-outbound-api-ca-2025-12.pem`, mount as secret | 15 min |
| 250 msg/day errors | Tier 0 cap on unverified WABA | Only matters if we start sending templates. We don't. Ignore unless alerting | n/a |
| OCR returns garbage | Photo too dark / rotated 90° / Gemini API regional outage | Retry once, then log to `pending_submissions` with reason | 0 (auto) |
| `db_f1_micro` OOM | Concurrent embeddings on a small box | Run embeddings via batch admin job, not webhook path | 1 h |
| Cold-start latency 8 s+ | Cloud Run scaled to zero | Set `--min-instances=1` during exam week (~$5/mo extra) | 2 min |
| Drive import script halts | Quota / token expiry | Resumable import: keyed on `sha256` in `past_papers.raw_file_url`; rerun script | 5 min |
| Display name change request | New MSA branding | Re-submit via WhatsApp Manager; certificate re-download required within 14 days | 4 h |
| Successor onboarding | Hafeedh leaves PAU | Hand over: Meta Business Manager admin role, GCP IAM Owner, Secret Manager access, README. Documented in `HANDOVER.md` | 1 day |

### 12.2 Monitoring (minimum viable)
- Cloud Logging-based alert: `severity>=ERROR AND service=paperbank-web` → email Hafeedh.
- Weekly cron Cloud Scheduler: `SELECT count(*) FROM message_log WHERE created_at > now()-interval '7 days';` → email digest.
- No SRE pager. The system's failure mode is "Aisha sends again later." Acceptable.

---

## 13. Admin CLI Specification

`admin.py` is a single-file Python CLI (Click). Installed via `pip install -e .` in a long-lived VM or laptop. Credentials via Application Default Credentials (`gcloud auth application-default login`).

### 13.1 Command surface
```
python admin.py --help

Commands:
  add-paper         Add a single paper file (PDF or images) to the bank.
  retire-paper      Soft-delete a paper (sets is_retired=TRUE).
  list-papers       List papers, filter by course/year/active-risk.
  curate            Interactive curation gate: review is_active_risk=TRUE papers.
  review-pending    (V1.1) Walk pending_submissions queue.
  set-course-active Mark course as active/inactive (suppresses retrieval).
  import-drive      Bulk import from a Drive folder. Respects curation gate.
  reembed           Re-run embeddings (e.g. after model upgrade).
  audit             Pull message_log slice for a phone_number or date range.
  stats             Counts: papers, questions, active users, retrievals/day.
  whoami            Sanity check: prints DB host, GCS bucket, model versions.
```

### 13.2 Argument signatures
```
add-paper      --course CODE --year YYYY --session [first|second|CA1|CA2|exam]
               --file PATH... [--title TEXT] [--force]
retire-paper   <paper_id> [--reason TEXT]
list-papers    [--course CODE] [--year YYYY] [--active-risk] [--retired] [--limit N]
curate         [--course CODE] [--limit N]            # interactive
review-pending [--limit N]                            # interactive
set-course-active <CODE> [--inactive]
import-drive   --folder <DRIVE_FOLDER_ID> [--dry-run] [--max N]
reembed        [--paper-id ID | --all] [--batch-size 32]
audit          (--phone E164 | --since DATE) [--limit N] [--csv PATH]
stats          [--days N]
```

### 13.3 Behavioural rules (LLM-readable)
- Every command prints a one-line summary then exits 0/1.
- Destructive operations (`retire-paper`, `reembed --all`) prompt `Type 'yes' to confirm:`.
- All commands read the same `~/.msa-paperbank.yaml` config (DB conn, GCS bucket, model IDs).
- `--dry-run` available on every write command.
- `import-drive` is **idempotent** — keys on file SHA256.

### 13.4 Transcript: curation gate (the trickiest command)
```
$ python admin.py curate
Loading active-risk papers awaiting curation...

Found 47 papers flagged is_active_risk=TRUE.

[1/47] paper_id=812
  course:   CSC305  (course exists in DB? NO — first appearance)
  year:     2025
  session:  exam
  source:   drive_import
  raw:      gs://msa-papers/raw/812.pdf
  questions: 6 extracted

  Preview:
    Q1. Define a binary search tree. State two invariants...
    Q2. Implement Dijkstra's algorithm. State its time complexity...
    Q3. ...

Action [a]pprove / [r]eject / [d]efer / [v]iew-full / [s]kip / [q]uit: a
  Reason / note (enter for none): course is genuinely new this year, lecturer rotated
  ✓ paper_id=812 approved by 'hafeedh' at 2026-05-04T13:22:01+01:00
  → 6 questions embedded, 6 rows inserted

[2/47] paper_id=813
  course:   GST122  (course exists in DB? NO)
  year:     2025
  session:  CA2

Action [a/r/d/v/s/q]: r
  Reason: lecturer published it on slack; identical reuse risk if exam not yet sat
  ✗ paper_id=813 rejected, will not be indexed. Held for 30 days then re-prompted.

[3/47] paper_id=814
  ...
Action [a/r/d/v/s/q]: q
Saved progress. Resume with: python admin.py curate
```

### 13.5 Transcript: retire_paper
```
$ python admin.py retire-paper 812 --reason "lecturer republished verbatim 2026 CA1"
Found paper:
  paper_id=812  course=CSC305  year=2025  session=exam
  questions=6   currently_indexed=YES   retrieval_hits_30d=14
This will:
  - set is_retired=TRUE (paper hidden from retrieval immediately)
  - keep the row, raw file, and embeddings for audit
  - log retirement in message_log as direction='admin'

Type 'yes' to confirm: yes
✓ Retired paper_id=812 by 'hafeedh' at 2026-05-04T13:30:11+01:00
  Reason: lecturer republished verbatim 2026 CA1
  Retrieval will exclude this paper from the next request onwards.
```

---

## 14. Deferred Feature Backlog

### V1.1 (post-public-launch, no commitment date)
| # | Feature | Rationale for deferral |
|---|---|---|
| 1.1.1 | Hybrid BM25 + pgvector RRF retrieval | `pg_bm25` extension not available on Cloud SQL Postgres. Requires AlloyDB or self-hosted PG → blows the durability budget. Add only if pure-vector recall measurably underperforms |
| 1.1.2 | User-facing photo upload pipeline | Requires moderation UX, abuse-throttling, Tier 0 → Tier 1 WABA tracking. Schema is ready (`pending_submissions`); flip a feature flag |
| 1.1.3 | Implicit profile read-side | We collect `inferred_courses` in V1; reading it for re-ranking is V1.1 (needs A/B framework even informal) |
| 1.1.4 | CAC "Incorporated Trustees" + Meta business verification | Unblocks blue-tick, raises tier limit. Only matters if templates are sent — they aren't. Defer unless need arises |

### V1.2
| # | Feature | Rationale |
|---|---|---|
| 1.2.1 | Soft personalisation: "Prioritising your courses" reply prefix | Requires user-summary inference + opt-out flow + privacy notice. Marginal value vs effort |

### V2 (next academic year +)
| # | Feature | Rationale |
|---|---|---|
| 2.1 | AI summarisation (RAG over question chunks via Gemini Pro) | Triggers academic-integrity reviews. Out of scope for "paper bank". Build only after lecturer feedback approves |
| 2.2 | Practice mode / quizzing (stateful) | Requires a session state machine (Redis or DB), which violates the "no idle cost" durability rule |
| 2.3 | Study mentor | Open-ended chat; quality unbounded; cost unbounded |
| 2.4 | Career mentor | Same |
| 2.5 | Community coordination (events, prayer reminders, halaqah pings) | Requires WhatsApp template approvals + outbound at scale → cost model breaks |

---

## 15. Sadaqah Jariyah Durability Checklist

**Public launch is BLOCKED until every box passes.**

| ✓ | Criterion | Verification method |
|---|---|---|
| ☐ D1 | Cloud Run scales to zero. Idle cost = $0 (apart from Cloud SQL $10/mo) | `gcloud run services describe ... | grep minScale → 0` |
| ☐ D2 | No feature requires Hafeedh personally. Successor with the README can run all admin operations | Dry-run by Ibrahim (named successor) before launch |
| ☐ D3 | Admin CLI works without GCP Console interaction for: add, retire, list, curate, audit | Manual run-through, signed off in `HANDOVER.md` |
| ☐ D4 | All secrets in Secret Manager with named IAM grant `roles/secretmanager.secretAccessor` to a successor's email | `gcloud secrets get-iam-policy` |
| ☐ D5 | Database has automated daily backups; retention 7 days minimum | Cloud SQL backup config |
| ☐ D6 | README in plain English, no jargon. Includes: "If the bot stops replying, run X. If you want to add a paper, run Y." | Read aloud test by a non-technical MSA exec |
| ☐ D7 | Total monthly cost ≤ $15 at projected scale. No hidden meters (per-token caps, alert thresholds) | GCP budget alert configured at $25, $50 |
| ☐ D8 | No third-party paid SaaS dependencies (no Twilio, no BSP, no managed vector DB) | Dependency audit |
| ☐ D9 | Source code in a public or MSA-owned GitHub repo. Branch protection: deploys from `main` via Cloud Build trigger | Repo metadata |
| ☐ D10 | Successor handover documented in `HANDOVER.md` and named MSA exec has access to: Meta Business Manager (admin), GCP IAM (Owner), GitHub (admin), Secret Manager | Manual transfer + screenshot |
| ☐ D11 | Curation gate cannot be bypassed by code path. Reviewed by reading `import-drive` source | Code review |
| ☐ D12 | No cron, no always-on worker. Everything is event-driven or manual | `gcloud scheduler jobs list` should be empty or only contain weekly digest |

---

## 16. Launch Checklist

### 16.1 Soft launch (10 MSA execs)
- [ ] Phase 1, 2, 3 deliverables met
- [ ] Curation gate ran end-to-end on the Drive corpus
- [ ] At least 30 papers across ≥ 5 courses live in DB
- [ ] Each exec sends ≥ 5 test messages from their own number
- [ ] 7-day soak: zero unhandled exceptions in Cloud Logging
- [ ] Embedding sanity check: `SELECT count(*) FROM paper_questions WHERE embedding IS NULL` = 0

### 16.2 Public launch (post-feedback)
- [ ] All §15 durability boxes ticked
- [ ] OPERATIONS.md merged
- [ ] HANDOVER.md merged
- [ ] Named successor confirmed (Ibrahim or substitute) with all access grants
- [ ] Hafeedh announces at Jumu'ah; copy posted in:
  - PAU MSA general WhatsApp group
  - PAU MSA exam-prep group
  - PAU MSA brothers' / sisters' groups
- [ ] Launch timing: 4–6 weeks before semester finals (target: rabi'al-thani / late-October pre-exam window each year)
- [ ] Day-1 monitoring: Hafeedh watches Cloud Logging live for first 2 h
- [ ] Day-7 review: stats run, fix top-3 issues, document in CHANGELOG

### 16.3 Post-launch (week 2+)
- [ ] Stats digest emailed weekly to Hafeedh + Amir
- [ ] Backlog (§14) groomed monthly; nothing built without explicit MSA exec request
- [ ] Annual handover review with the successor: rotate keys, confirm billing card, run a fire-drill `retire_paper`

---

### Appendix A — Locked dependency versions (Step 1C must verify against latest stable releases)
```
python==3.12
fastapi==0.115.*
uvicorn==0.32.*
google-cloud-aiplatform==1.71.*
google-cloud-storage==2.18.*
google-cloud-secret-manager==2.20.*
psycopg[binary,pool]==3.2.*
pgvector==0.3.*
opencv-python-headless==4.10.*
reportlab==4.2.*
click==8.1.*
httpx==0.27.*
pydantic==2.9.*
```
*Note: `google-cloud-pubsub` removed in v1.1 pre-edit — Pub/Sub no longer used in V1. Step 1C verifies remaining dependencies are current and not deprecated.*

### Appendix B — Model versions (Step 1C must verify before any code is written)
| Role | Model (locked stack) | Status (May 2026) | Verification needed |
|---|---|---|---|
| Routing/intent | `gemini-3-flash` | placeholder model ID — verify exact API string in Step 1C | Confirm Vertex AI availability in target region; pull current pricing |
| OCR / vision / extraction | `gemini-3.1-pro-preview` | placeholder model ID — verify exact API string in Step 1C | Confirm Vertex AI availability in target region; pull current pricing; confirm preview-tier rate limits don't break MSA scale |
| Embeddings | `gemini-embedding-001` @ 768-dim (MRL) | GA. **Replaces `text-embedding-004` — deprecated 2026-01-14** | Confirm pricing has not changed since spec was written |

### Appendix C — Open questions parked (NOT for V1)
- Whether to add a re-ranker (Cohere Rerank, Vertex Ranking API) for V1.1 hybrid path.
- Whether `pgvectorscale` (TimescaleDB) is a worthwhile move for >100k vectors. Current corpus < 10k vectors → no.
- WhatsApp Username/BSUID rollout (June 2026): when usernames go live, store BSUID alongside `phone_number` in `users`. Schema-additive, no V1 work.