# msa-paperbank — Master PRD (V1)

**Project:** PAU MSA Past-Paper Bank over WhatsApp
**Intent:** Sadaqah jariyah. A boring, durable, single-service system that lets a PAU student request a past paper from WhatsApp and receive the PDF in one message.
**Owner / Maintainer:** Ibrahim (200-level, knows Python, does not know GCP). Solo dev, weekend chunks.
**Status:** V1 locked. Modernized 2026-05-03 against the current Vertex AI catalog and current Python stack.

---

## 1. V1 Scope (Locked — do not expand)

**In scope (V1):**
- WhatsApp inbound message → return the requested past-paper PDF (or a clear "not found" reply) in one message.
- Past-paper bank only. PDFs ingested by Ibrahim via an offline admin CLI.
- Course/level/semester resolution from natural-language requests (e.g., "Aisha's typo'd MTH 102 Harmattan 2022").
- One Cloud Run service. One Cloud SQL Postgres instance. One GCS bucket. Nothing else.

**Out of scope (V1, do not build):**
- Mentor matching, study groups, community features.
- User-uploaded PDFs / crowdsourced ingestion. (Admin CLI only.)
- Async workers, Pub/Sub, Cloud Tasks, Cloud Functions, Eventarc.
- MongoDB, Firestore, Redis, Elasticsearch, vector DBs.
- A web frontend. There is no website in V1.
- Twilio. We talk to Meta WhatsApp Cloud API directly.

---

## 2. Personas & Constraints

**Aisha (end user, PAU undergraduate, Lagos):**
- 1 bar of MTN signal in a lecture hall basement. Requests must succeed on a single round trip.
- Pays for data. PDFs must be sent as-is, not linked off-platform.
- Types fast and wrong: "mth102 hamattan 22", "give me CSC 201 last year".
- One message in, one message out. No buttons, no carousels, no flow that fails when the next webhook is dropped.

**Ibrahim (maintainer, 200-level, Python only):**
- Has never touched GCP before. Should not have to.
- Operates the system from one terminal: `make deploy`, `python admin.py upload …`, `gcloud sql connect`. Nothing else.
- Cannot be expected to debug Pub/Sub, IAM bindings, Cloud Run revisions, or async race conditions.

**Lagos infra constraints:**
- Power and network are unreliable on Ibrahim's side too. Ingestion is offline-first: PDFs go into a local folder, the CLI uploads when there's signal.
- Costs are USD-denominated and converted to NGN at a punishing rate. Hard ceiling **$15/month after GCP free credits** (see §6).

---

## 3. Architectural Taste (Boring-Reliable)

These are not preferences. They are constraints.

1. **One service.** Single Cloud Run service, single container, single deploy. No second service, no sidecar.
2. **Sync over async.** FastAPI sync endpoints unless a library forces async. WhatsApp webhook handler does the work inline and returns 200 within the Meta timeout. No background tasks, no fire-and-forget.
3. **Postgres over Mongo.** Cloud SQL for PostgreSQL 16. One database, three tables.
4. **No Pub/Sub.** No queue. If a message fails, it fails loudly, returns a clear error to the user, and is logged. We do not build delivery guarantees on top of best-effort substrates.
5. **No vector DB.** Course/title resolution is Postgres `pg_trgm` similarity + a Gemini Flash classifier, not embeddings + ANN.
6. **Two LLM calls maximum per request.** A Flash router and (only if needed) a Pro disambiguation. Cost ceiling is enforced in code, not in spreadsheets.
7. **Pinned versions.** Every external dependency, including Meta's Graph API version, is pinned. Upgrades are an explicit, dated PR.

---

## 4. System Architecture

```
                    Meta WhatsApp Cloud API
                              │
                              ▼   (HTTPS POST, X-Hub-Signature-256)
                ┌─────────────────────────────────┐
                │  Cloud Run service (1 container)│
                │   FastAPI, sync handlers        │
                │   ├─ /webhook  (Meta inbound)   │
                │   ├─ /webhook  GET (verify)     │
                │   └─ /healthz                   │
                └────────┬─────────────────┬──────┘
                         │                 │
                         ▼                 ▼
              Cloud SQL Postgres 16   GCS bucket
              (papers, courses,       (PDF blobs;
              request_log)            served via
                                      signed URL or
                                      direct media upload)
                         │
                         ▼
                  Vertex AI (Gemini 3 Flash + 3.1 Pro)
```

**Cloud Run config:**
- Region: `africa-south1` (Johannesburg) — closest GA region to Lagos with Cloud SQL + Vertex.
- CPU: 1, Memory: 512 MiB, min instances: 0, max: 2, concurrency: 40, request timeout: 60s.
- Service account: one custom SA with `roles/cloudsql.client`, `roles/storage.objectUser` (single bucket), `roles/aiplatform.user`.
- Ingress: all (Meta IPs are not stable enough to whitelist on a student's budget). Webhook auth = HMAC signature, not network.

**Cloud SQL:**
- Postgres 16, `db-f1-micro` (shared core, 0.6 GB) — covered by the always-free shared-core tier in supported regions; in `africa-south1` it is the cheapest paid tier and still fits the budget.
- Private IP off (saves a VPC connector). Cloud SQL Auth Proxy via the **Cloud SQL Python Connector** for connections from Cloud Run. No public IP exposed to the internet directly.
- Single database `paperbank`. Backups: automated daily, 7-day retention.

**GCS:**
- One bucket `msa-paperbank-pdfs-<project-id>`, Standard storage, region-locked to `africa-south1`. Uniform bucket-level access. Lifecycle: none in V1 (PDFs are forever).

---

## 5. LLM Stack (Vertex AI — Modernized)

### 5.1 Locked models

| Role | Model ID (Vertex AI) | Why |
|---|---|---|
| Heavy reasoning + OCR for ingestion | `gemini-3.1-pro-preview` | OCR of scanned papers, course/title/year extraction, cross-referencing handwritten metadata. Used **offline** by the admin CLI only. |
| Cheap routing + replies | `gemini-3-flash-preview` | Parses Aisha's typo'd request, produces the structured `(course_code, semester, year)` query, and writes the human reply. Used on every webhook. |

Both are public preview as of December 2025 / early 2026. Pin the exact ID strings; do not use floating aliases.

### 5.2 Vertex AI pricing (per 1M tokens, `us` / global, paid tier — Vertex pricing page, accessed 2026-05-03)

| Model | Input (text/image/video) | Cache read | Output (incl. reasoning) |
|---|---|---|---|
| `gemini-3.1-pro-preview` | $2.00 | $0.20 | $12.00 |
| `gemini-3-flash-preview` | $0.50 | $0.05 | $3.00 |

Note: Vertex prices for some regions (e.g., the higher-tier pricing band) are 1.8× these. Use the global endpoint for V1; budget assumes global pricing.

### 5.3 Cost model (V1 budget — must fit under $15/month post-credits)

Assumptions:
- 200 student requests/day × 30 days = 6,000 requests/month (generous; real V1 is closer to 50/day).
- Per request: ~400 input tokens + ~200 output tokens to Flash. Pro is **not** called on the request path in V1.
- Admin ingestion: 50 PDFs/month, ~30k input tokens (PDF pages) + 1k output to Pro per PDF.

Monthly LLM cost:
- Flash request path: 6,000 × (400 × $0.50 + 200 × $3.00) / 1,000,000 = 6,000 × ($0.0002 + $0.0006) = **$4.80**
- Pro ingestion: 50 × (30,000 × $2.00 + 1,000 × $12.00) / 1,000,000 = 50 × ($0.060 + $0.012) = **$3.60**
- **LLM total: ~$8.40/month**

Other GCP:
- Cloud Run: well under free tier at this volume → **~$0**
- Cloud SQL `db-f1-micro` in `africa-south1`: ~$9/month list, **fully covered by the $300 GCP free trial credit** for the first ~33 months. Post-credit, downgrade to a smaller scheduled-stop pattern or migrate to Supabase free tier. **Tracked as a V2 risk, not a V1 blocker.**
- GCS: ~$0.02/GB/month × <5 GB = **<$0.10**
- Egress (PDF media to Meta): WhatsApp media uploads go to Meta's CDN; egress is to Meta only, ~$0.12/GB. 6,000 × 1 MB = 6 GB → **~$0.72**.

**Total in-budget steady state: ~$9.50/month** (post free credit, excluding Cloud SQL which is on credit). Comfortably under $15.

A hard cost guard is enforced in code: if `request_log` shows >300 LLM calls in the last hour, the service short-circuits new requests with a "too busy, try again" reply.

### 5.4 SDK

- Library: `google-genai` (the unified SDK). The legacy `google-generativeai` package is deprecated; do not install it.
- Pinned: `google-genai==1.x` (latest stable on PyPI at deploy time; pin exact patch in `requirements.txt`).
- Auth: ADC via the Cloud Run service account. No API keys.

```python
# llm.py
from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project=settings.gcp_project,
    location="global",
)

FLASH = "gemini-3-flash-preview"
PRO = "gemini-3.1-pro-preview"

def route_request(user_text: str) -> dict:
    resp = client.models.generate_content(
        model=FLASH,
        contents=user_text,
        config=types.GenerateContentConfig(
            system_instruction=ROUTER_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RouterOutput,  # pydantic v2 model
            temperature=0.0,
            max_output_tokens=256,
        ),
    )
    return RouterOutput.model_validate_json(resp.text).model_dump()
```

---

## 6. Python Stack (Syntax & Deprecation Audit — 2026-05-03)

All versions pinned. Upgrades are explicit PRs.

### 6.1 FastAPI

- Pinned: `fastapi==0.12x` (latest stable). Use the **`lifespan` async context manager** for startup/shutdown, not `@app.on_event(...)`. `on_event` still works (re-implemented in `fastapi#14851`, Feb 2026) but is on the path to deprecation when Starlette ships its replacement; do not use it in new code.
- Use `Annotated[..., Depends(...)]` for dependencies — the old `param: X = Depends(...)` form still works but Annotated is the documented pattern.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await build_pool()
    yield
    await app.state.db.close()

app = FastAPI(lifespan=lifespan)
```

### 6.2 Pydantic v2 + pydantic-settings

- Pinned: `pydantic==2.x`, `pydantic-settings==2.x`.
- **No `class Config:`.** Use `model_config = ConfigDict(...)`.
- **No `.dict()`, no `.json()`, no `.parse_obj()`.** Use `model_dump()`, `model_dump_json()`, `model_validate()`, `model_validate_json()`.
- `BaseSettings` lives in `pydantic_settings`, not `pydantic`.
- Field aliases via `Field(..., validation_alias="ENV_NAME")`.

```python
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    gcp_project: str
    cloud_sql_instance: str           # project:region:instance
    db_user: str
    db_password: str = Field(validation_alias="DB_PASSWORD")
    db_name: str = "paperbank"
    wa_phone_number_id: str
    wa_access_token: str
    wa_app_secret: str
    wa_verify_token: str
    gcs_bucket: str
    graph_api_version: str = "v23.0"
```

### 6.3 Database — psycopg 3 + SQLAlchemy 2.0 + Cloud SQL Python Connector

- Pinned: `psycopg[binary]==3.x` (psycopg2 is legacy; do not use). `SQLAlchemy==2.0.x`. `cloud-sql-python-connector[pg8000]` **or** `[psycopg3]` — we use `psycopg3` to keep one driver in the image.
- Use SQLAlchemy 2.0 declarative style: `DeclarativeBase`, `Mapped[...]`, `mapped_column(...)`. Do not use `declarative_base()` from 1.x.
- **Sync** `Engine` + `Session`. No async SQLAlchemy in V1.

```python
from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

connector = Connector()

def getconn():
    return connector.connect(
        settings.cloud_sql_instance,
        "psycopg",
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
    )

engine = create_engine("postgresql+psycopg://", creator=getconn, pool_size=2, max_overflow=2, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): ...

class Paper(Base):
    __tablename__ = "papers"
    id: Mapped[int] = mapped_column(primary_key=True)
    course_code: Mapped[str] = mapped_column(index=True)
    course_title: Mapped[str]
    level: Mapped[int]
    semester: Mapped[str]      # 'harmattan' | 'rain'
    year: Mapped[int]
    gcs_object: Mapped[str]
    sha256: Mapped[str] = mapped_column(unique=True)
```

### 6.4 Meta WhatsApp Cloud API (direct, no Twilio)

- Graph API version pinned in env: `WA_GRAPH_VERSION=v23.0` (current stable as of 2026-05-03; bump explicitly).
- Inbound: Meta POSTs to `/webhook`. Verify the **`X-Hub-Signature-256`** header against the app secret before doing anything. Reject with 401 on mismatch. Do not log the raw body before verification.
- GET `/webhook` for verification: compare `hub.verify_token` to `WA_VERIFY_TOKEN`, echo `hub.challenge` as plain text.
- Outbound: POST `https://graph.facebook.com/{WA_GRAPH_VERSION}/{phone_number_id}/messages` with bearer token. For PDFs, two-step: upload media to `/media` (multipart), then send a `document` message referencing the returned `media_id`. Do not send signed GCS URLs — Aisha pays for that data and Meta caches `media_id` documents on its CDN.
- Idempotency: Meta retries webhooks. Dedupe on `messages[].id` using a unique index in `request_log`.

```python
import hmac, hashlib
from fastapi import Header, HTTPException, Request

def verify_meta_signature(raw: bytes, sig: str, app_secret: str) -> None:
    expected = "sha256=" + hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig or ""):
        raise HTTPException(status_code=401, detail="bad signature")

@app.post("/webhook")
def webhook(request: Request, x_hub_signature_256: str = Header(default="")):
    raw = request._body  # captured by middleware; or use request.body() in async wrapper
    verify_meta_signature(raw, x_hub_signature_256, settings.wa_app_secret)
    ...
```

### 6.5 HTTP client

- Pinned: `httpx==0.2x` for outbound calls to Graph API. Sync client. Timeouts: `httpx.Timeout(connect=5, read=30, write=30, pool=5)`. Retries: 1 retry on connect errors only; never retry on 4xx.

### 6.6 Pinned `requirements.txt` (illustrative; pin exact patch versions at deploy)

```
fastapi==0.120.*
uvicorn[standard]==0.3*.*
pydantic==2.*
pydantic-settings==2.*
google-genai==1.*
SQLAlchemy==2.0.*
psycopg[binary]==3.*
cloud-sql-python-connector[psycopg3]==1.*
httpx==0.2*.*
google-cloud-storage==2.*
python-multipart==0.0.*
```

---

## 7. Data Model

Three tables. That is the entire schema.

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE courses (
    code TEXT PRIMARY KEY,         -- 'MTH102'
    title TEXT NOT NULL,
    level INT NOT NULL,
    department TEXT NOT NULL
);
CREATE INDEX courses_title_trgm ON courses USING gin (title gin_trgm_ops);

CREATE TABLE papers (
    id BIGSERIAL PRIMARY KEY,
    course_code TEXT NOT NULL REFERENCES courses(code),
    semester TEXT NOT NULL CHECK (semester IN ('harmattan','rain')),
    year INT NOT NULL,
    gcs_object TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    uploaded_by TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (course_code, semester, year)
);
CREATE INDEX papers_lookup ON papers (course_code, year DESC, semester);

CREATE TABLE request_log (
    id BIGSERIAL PRIMARY KEY,
    wa_message_id TEXT UNIQUE NOT NULL,    -- dedupe Meta retries
    wa_from TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_text TEXT NOT NULL,
    routed_course TEXT,
    routed_year INT,
    routed_semester TEXT,
    matched_paper_id BIGINT REFERENCES papers(id),
    outcome TEXT NOT NULL,                  -- 'sent' | 'not_found' | 'ambiguous' | 'error'
    flash_input_tokens INT,
    flash_output_tokens INT,
    error TEXT
);
CREATE INDEX request_log_recent ON request_log (received_at DESC);
```

---

## 8. Request Flow (single round trip)

1. Meta POSTs webhook with the message. Service captures raw body → verifies signature → parses JSON.
2. Insert into `request_log` (`outcome='received'`) keyed by `wa_message_id`. If the insert violates the unique index, this is a Meta retry — return 200 and stop.
3. Call Flash router with the user text; receive `(course_code, year, semester, confidence)`.
4. If `confidence < 0.7`, run a `pg_trgm` similarity search against `courses.title || code` and pick the top hit; if still ambiguous, reply with a one-line clarification ("Did you mean MTH 102?") and update `outcome='ambiguous'`. **No multi-turn flow** — Aisha can resend.
5. Look up `papers` by `(course_code, year, semester)`. If absent, fall back to nearest year for that course and tell the user. If still nothing: reply with "We don't have this one yet — Ibrahim is uploading."
6. Stream the PDF from GCS, upload to Meta `/media`, then send a `document` message with the returned `media_id` and a one-line caption. Update `outcome='sent'`.
7. Return 200 to Meta. Total budget: <8s p50, <30s p99. If Vertex is slow, we still return 200 to Meta and reply asynchronously **never** — we make the user retry. (Boring beats half-built async.)

---

## 9. Admin CLI (V1 ingestion path)

`python admin.py upload <pdf_path> [--course MTH102 --year 2022 --semester harmattan]`

- Reads the PDF locally.
- If metadata flags are absent, sends pages 1–2 to **`gemini-3.1-pro-preview`** with a strict JSON schema (`course_code`, `course_title`, `year`, `semester`) and asks Ibrahim to confirm in the terminal (`y/N`).
- Computes SHA-256. Uploads to GCS (`papers/{course_code}/{year}-{semester}.pdf`). Inserts the `papers` row. Idempotent: if the SHA already exists, skips upload and prints the existing row.
- Runs locally on Ibrahim's laptop, authenticated via `gcloud auth application-default login`. **No web upload UI.**

`python admin.py backfill-courses courses.csv` — one-time bulk load of the PAU course catalog.

---

## 10. Deploy & Ops

**Deploy:** `make deploy` runs:
```
gcloud run deploy msa-paperbank \
  --source . --region africa-south1 \
  --service-account msa-paperbank-sa@$PROJECT.iam.gserviceaccount.com \
  --add-cloudsql-instances $PROJECT:africa-south1:paperbank \
  --set-env-vars-from-file env.yaml \
  --memory 512Mi --cpu 1 --concurrency 40 --max-instances 2 --min-instances 0 \
  --no-allow-unauthenticated=false
```
Secrets (`WA_ACCESS_TOKEN`, `WA_APP_SECRET`, `DB_PASSWORD`) are stored in Secret Manager and mounted as env vars.

**Observability:** Cloud Run request logs + structured JSON logs from the app. One Log-based Metric: `outcome="error"` count. One Cloud Monitoring alert: error rate > 5/hour for 10 minutes → email Ibrahim. That is the entire monitoring stack.

**Rollback:** `gcloud run services update-traffic msa-paperbank --to-revisions=PREVIOUS=100`. Documented in `RUNBOOK.md` (one page).

---

## 11. Risks & Explicit Non-Decisions

- **Vertex preview models can be deprecated.** Mitigation: model IDs live in env vars (`MODEL_FLASH`, `MODEL_PRO`); a Pro/Flash GA bump is a one-line config change. Pin Graph API version the same way.
- **Cloud SQL cost after free trial.** Tracked. If credits expire and donations don't cover it, V2 migrates to a managed Postgres with a real free tier. Not a V1 blocker.
- **Meta token rotation.** Long-lived system user token; rotation is a manual quarterly task in the runbook.
- **WhatsApp Business policy.** Replies inside the 24-hour customer service window are free-form; outside it, only template messages. V1 only replies to inbound messages, so we are always inside the window.
- **No mentor / community features.** Permanently out of scope for V1. Re-litigate in a separate doc after V1 has been live for one full semester.

---

## 12. Definition of Done (V1)

- [ ] Aisha sends "MTH 102 harmattan 2022" from a real PAU number; receives the correct PDF in under 30 seconds on 1-bar MTN.
- [ ] Ibrahim runs `python admin.py upload` from his laptop and the paper is queryable within 60 seconds.
- [ ] All secrets in Secret Manager. No secrets in the repo. No secrets in env files committed to git.
- [ ] `RUNBOOK.md` exists and Ibrahim can rotate the Meta token by following it without asking anyone.
- [ ] One full month of operation: total GCP bill ≤ $15 post-credits, error rate < 1% of requests.

---

*Last modernized: 2026-05-03. Verified against Vertex AI catalog, Meta Graph API v23.0, FastAPI 0.12x, Pydantic 2.x, google-genai 1.x, SQLAlchemy 2.0, psycopg 3.x.*
