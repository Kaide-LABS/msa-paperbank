# PHASE 1 — Technical Spec (Execution Blueprint)

**Source of truth:** `PRD.md` in this repo.
**Audience:** the execution agent that will write the code. Do not deviate from this spec without changing this file first.
**Scope (locked):** single-course end-to-end functional bot. **Course is hardcoded to `MTH102`.** Retrieval is **Postgres `ILIKE` only** — no `pg_trgm`, no embeddings, no semantic search. Inbound WhatsApp message → Flash router parses → ILIKE lookup against the single hardcoded course's papers → send PDF (or "not found") in one message.
**Out of scope for Phase 1 (do not touch):** `pg_trgm`/fuzzy matching, pgvector embeddings, OpenCV PDF preprocessing, Google Drive importer, multi-course catalog, admin curation gate / approval flow, multi-turn clarification dialogues, monitoring alert wiring, `Makefile` deploy automation. These are Phase 2/3.

---

## 0. Definition of Done (Phase 1)

A real PAU number sends "MTH 102 harmattan 2022" to the WhatsApp business number; within 30s on weak signal, the same chat receives the matching PDF as a `document` message. If the paper is not in the DB, the same chat receives the literal string `We don't have this MTH102 paper yet — Ibrahim is uploading.` That is the only success criterion.

---

## 1. Repository layout

Exactly these files. Nothing more, nothing less.

```
msa-paperbank/
├── PRD.md
├── PHASE_1_SPEC.md
├── README.md                   # one page: how to run locally, how to deploy
├── pyproject.toml              # build metadata + tool config (ruff, pytest)
├── requirements.txt            # pinned deps (see §2)
├── Dockerfile                  # python:3.12-slim, gunicorn+uvicorn
├── .dockerignore
├── .gitignore
├── .env.example                # every env var the app reads, no secrets
├── env.yaml.example            # Cloud Run env file template
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app + lifespan + routes
│   ├── config.py               # Settings (pydantic-settings)
│   ├── deps.py                 # FastAPI dependency providers (db session, settings)
│   ├── schemas.py              # all Pydantic v2 models (request, response, LLM IO)
│   ├── db.py                   # SQLAlchemy 2.0 engine, session factory, Base, ORM models
│   ├── llm.py                  # google-genai client + router function
│   ├── whatsapp.py             # Meta Cloud API client (verify sig, upload media, send doc)
│   ├── retrieval.py            # ILIKE lookup against papers table for hardcoded course
│   ├── pipeline.py             # webhook orchestration (the one function that runs per inbound msg)
│   └── logging_setup.py        # structured JSON logging
├── admin/
│   ├── __init__.py
│   └── upload.py               # `python -m admin.upload <pdf> --year --semester` CLI (MTH102 only)
├── migrations/
│   └── 001_init.sql            # the three tables + seed for MTH102
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_signature.py
    ├── test_router_schema.py
    ├── test_retrieval.py
    └── test_pipeline.py
```

No `__pycache__`, no `.venv`, no notebooks, no `scripts/` folder. If a file is not on this list, do not create it.

---

## 2. Pinned dependencies (`requirements.txt`)

```
fastapi==0.120.2
uvicorn[standard]==0.32.1
gunicorn==23.0.0
pydantic==2.9.2
pydantic-settings==2.6.1
google-genai==1.2.0
SQLAlchemy==2.0.36
psycopg[binary]==3.2.3
cloud-sql-python-connector[psycopg3]==1.15.0
google-cloud-storage==2.19.0
httpx==0.28.1
python-multipart==0.0.20
```

Dev-only (in `pyproject.toml`'s optional group `dev`, not in `requirements.txt`):

```
pytest==8.3.4
pytest-asyncio==0.24.0
respx==0.21.1            # httpx mocking
ruff==0.8.2
```

Patch versions are illustrative — pin exactly to whatever resolves on first lockfile generation, then never float.

---

## 3. Configuration (`app/config.py`)

`Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)`. Fields, all required unless a default is given:

| Field (Python) | Env var | Type | Default |
|---|---|---|---|
| `gcp_project` | `GCP_PROJECT` | `str` | — |
| `gcp_location` | `GCP_LOCATION` | `str` | `"global"` |
| `cloud_sql_instance` | `CLOUD_SQL_INSTANCE` | `str` (`project:region:instance`) | — |
| `db_user` | `DB_USER` | `str` | — |
| `db_password` | `DB_PASSWORD` | `SecretStr` | — |
| `db_name` | `DB_NAME` | `str` | `"paperbank"` |
| `gcs_bucket` | `GCS_BUCKET` | `str` | — |
| `wa_phone_number_id` | `WA_PHONE_NUMBER_ID` | `str` | — |
| `wa_access_token` | `WA_ACCESS_TOKEN` | `SecretStr` | — |
| `wa_app_secret` | `WA_APP_SECRET` | `SecretStr` | — |
| `wa_verify_token` | `WA_VERIFY_TOKEN` | `SecretStr` | — |
| `wa_graph_version` | `WA_GRAPH_VERSION` | `str` | `"v23.0"` |
| `model_flash` | `MODEL_FLASH` | `str` | `"gemini-3-flash-preview"` |
| `model_pro` | `MODEL_PRO` | `str` | `"gemini-3.1-pro-preview"` |
| `hardcoded_course_code` | `HARDCODED_COURSE_CODE` | `str` | `"MTH102"` |
| `request_rate_limit_per_hour` | `REQUEST_RATE_LIMIT_PER_HOUR` | `int` | `300` |
| `log_level` | `LOG_LEVEL` | `str` | `"INFO"` |

Expose a single module-level `settings = Settings()` instance constructed at import time. `.env.example` mirrors every key with placeholder values.

---

## 4. Logging (`app/logging_setup.py`)

One function `setup_logging(level: str) -> None`. JSON-line formatter writing to stdout with fields `ts`, `level`, `logger`, `msg`, plus any `extra` kwargs. Called from `main.py` at module import (before app creation). No file handlers. No log rotation. Cloud Run captures stdout.

---

## 5. Database (`app/db.py`)

### 5.1 Connection

- Module-level `connector = Connector()` (from `google.cloud.sql.connector`).
- `getconn()` returns `connector.connect(settings.cloud_sql_instance, "psycopg", user=..., password=..., db=...)`.
- `engine = create_engine("postgresql+psycopg://", creator=getconn, pool_size=2, max_overflow=2, pool_pre_ping=True, pool_recycle=1800)`.
- `SessionLocal = sessionmaker(engine, expire_on_commit=False, autoflush=False)`.
- Disposal hook: `def dispose() -> None` calls `engine.dispose()` and `connector.close()`. Called from FastAPI lifespan shutdown.

### 5.2 ORM models (SQLAlchemy 2.0 declarative)

```python
class Base(DeclarativeBase): ...

class Course(Base):
    __tablename__ = "courses"
    code: Mapped[str] = mapped_column(primary_key=True)         # 'MTH102'
    title: Mapped[str]
    level: Mapped[int]
    department: Mapped[str]

class Paper(Base):
    __tablename__ = "papers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.code"), index=True)
    semester: Mapped[str]                                        # 'harmattan' | 'rain'
    year: Mapped[int]
    gcs_object: Mapped[str]
    sha256: Mapped[str] = mapped_column(unique=True)
    uploaded_by: Mapped[str]
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    __table_args__ = (UniqueConstraint("course_code", "semester", "year"),)

class RequestLog(Base):
    __tablename__ = "request_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wa_message_id: Mapped[str] = mapped_column(unique=True, index=True)
    wa_from: Mapped[str]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    user_text: Mapped[str]
    routed_course: Mapped[Optional[str]]
    routed_year: Mapped[Optional[int]]
    routed_semester: Mapped[Optional[str]]
    matched_paper_id: Mapped[Optional[int]] = mapped_column(ForeignKey("papers.id"), nullable=True)
    outcome: Mapped[str]                                         # 'sent'|'not_found'|'ambiguous'|'error'|'rate_limited'
    flash_input_tokens: Mapped[Optional[int]]
    flash_output_tokens: Mapped[Optional[int]]
    error: Mapped[Optional[str]]
```

### 5.3 Migration `migrations/001_init.sql`

DDL identical to PRD §7 minus `pg_trgm` (no `CREATE EXTENSION`, no GIN index on title). Plus a seed:

```sql
INSERT INTO courses(code, title, level, department) VALUES
  ('MTH102', 'General Mathematics II', 100, 'Mathematics')
ON CONFLICT (code) DO NOTHING;
```

Run via `psql -f migrations/001_init.sql` against the Cloud SQL instance. Phase 1 does not introduce Alembic.

---

## 6. Pydantic schemas (`app/schemas.py`)

All models use Pydantic v2. No `class Config:`; use `model_config = ConfigDict(...)` only where needed.

### 6.1 WhatsApp inbound (subset of Meta payload — only fields we use)

```python
class WAText(BaseModel):
    body: str

class WAMessage(BaseModel):
    id: str
    from_: str = Field(validation_alias="from")
    timestamp: str
    type: Literal["text", "image", "document", "audio", "video", "interactive", "button", "reaction", "sticker", "location", "contacts", "unknown"]
    text: WAText | None = None

class WAValue(BaseModel):
    messaging_product: Literal["whatsapp"]
    metadata: dict
    messages: list[WAMessage] | None = None
    statuses: list[dict] | None = None        # ignored in P1

class WAChange(BaseModel):
    value: WAValue
    field: str

class WAEntry(BaseModel):
    id: str
    changes: list[WAChange]

class WAWebhookPayload(BaseModel):
    object: Literal["whatsapp_business_account"]
    entry: list[WAEntry]
```

Unknown extra fields: ignored (default Pydantic behavior). The webhook handler must `model_validate` the parsed JSON and tolerate `messages is None` (status-only callback) by returning 200 immediately.

### 6.2 LLM router IO

```python
class RouterOutput(BaseModel):
    """Strict JSON output from gemini-3-flash-preview router prompt."""
    intent: Literal["paper_request", "greeting", "other"]
    course_code: str | None = None         # must equal HARDCODED_COURSE_CODE when intent=paper_request
    year: int | None = None                # 4-digit, 2000..current_year+1
    semester: Literal["harmattan", "rain"] | None = None
    confidence: float                      # 0.0 .. 1.0

    @field_validator("year")
    @classmethod
    def _year_range(cls, v):
        if v is None: return v
        if not (2000 <= v <= 2100): raise ValueError("year out of range")
        return v
```

### 6.3 Outbound reply discriminator

```python
class TextReply(BaseModel):
    kind: Literal["text"] = "text"
    body: str

class DocumentReply(BaseModel):
    kind: Literal["document"] = "document"
    paper_id: int
    caption: str

Reply = Annotated[TextReply | DocumentReply, Field(discriminator="kind")]
```

`pipeline.handle_message` returns `Reply`; `whatsapp.send_reply(to: str, reply: Reply)` dispatches on `kind`.

---

## 7. WhatsApp client (`app/whatsapp.py`)

### 7.1 Signature verification

```python
def verify_signature(raw_body: bytes, header_value: str, app_secret: str) -> bool
```
- Computes `"sha256=" + hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()`.
- Returns `hmac.compare_digest(expected, header_value or "")`.
- Raises nothing. Caller raises `HTTPException(401)` on `False`.

### 7.2 Verify-token check (GET)

```python
def verify_token_match(mode: str, token: str, expected: str) -> str | None
```
Returns the value of `hub.challenge` (passed in by caller) iff `mode == "subscribe"` and `token == expected`. Caller (route) takes the returned challenge and responds with `PlainTextResponse(challenge, status_code=200)`. Otherwise route returns 403.

### 7.3 Outbound HTTP

One module-level `httpx.Client` constructed in lifespan startup, closed in shutdown. Timeouts `httpx.Timeout(connect=5, read=30, write=30, pool=5)`. Base URL `https://graph.facebook.com/{wa_graph_version}`.

```python
def upload_media(pdf_bytes: bytes, filename: str) -> str
```
- POST `/{phone_number_id}/media` with `multipart/form-data`: `messaging_product="whatsapp"`, `type="application/pdf"`, `file=(filename, pdf_bytes, "application/pdf")`.
- `Authorization: Bearer {wa_access_token}`.
- Returns `response.json()["id"]` (the `media_id`).
- On non-2xx: log status+body, raise `WhatsAppError`.

```python
def send_text(to: str, body: str) -> None
def send_document(to: str, media_id: str, caption: str, filename: str) -> None
```
- POST `/{phone_number_id}/messages`, JSON body per Meta spec:
  - text: `{messaging_product, recipient_type:"individual", to, type:"text", text:{body, preview_url:false}}`
  - document: `{messaging_product, recipient_type:"individual", to, type:"document", document:{id: media_id, caption, filename}}`
- Same auth header. Same error handling.

```python
def send_reply(to: str, reply: Reply, paper_loader: Callable[[int], tuple[bytes, str]]) -> None
```
Top-level dispatcher. For `DocumentReply`: `pdf_bytes, filename = paper_loader(reply.paper_id)`; `media_id = upload_media(pdf_bytes, filename)`; `send_document(to, media_id, reply.caption, filename)`. For `TextReply`: `send_text(to, reply.body)`.

### 7.4 No retries on 4xx. One retry on `httpx.ConnectError` only. Never on 5xx (let Meta resend the inbound).

---

## 8. LLM router (`app/llm.py`)

Single module-level client:
```python
client = genai.Client(vertexai=True, project=settings.gcp_project, location=settings.gcp_location)
```

Constants:
```python
ROUTER_SYSTEM_PROMPT = """You are the router for a PAU past-paper WhatsApp bot.
The bot only serves the course MTH102 (General Mathematics II) in Phase 1.
Given the user's WhatsApp text, output JSON matching the provided schema.
- If the user is asking for an MTH102 past paper, set intent='paper_request',
  course_code='MTH102', and extract year (4 digits) and semester
  ('harmattan' for Harmattan/first semester, 'rain' for Rain/second semester).
- If the user greets or thanks, set intent='greeting'.
- Otherwise intent='other'.
- confidence is your own 0..1 estimate.
Never invent a course code other than MTH102.
"""
```

Function:
```python
def route(user_text: str) -> tuple[RouterOutput, int, int]:
    """Returns (parsed_output, input_tokens, output_tokens)."""
```

Implementation contract:
- `client.models.generate_content(model=settings.model_flash, contents=user_text, config=types.GenerateContentConfig(system_instruction=ROUTER_SYSTEM_PROMPT, response_mime_type="application/json", response_schema=RouterOutput, temperature=0.0, max_output_tokens=256))`.
- Parse via `RouterOutput.model_validate_json(resp.text)`.
- Token counts: `resp.usage_metadata.prompt_token_count`, `resp.usage_metadata.candidates_token_count` (fall back to 0 if missing).
- On any exception: re-raise as `RouterError` with original chained.

**No Pro model is called in Phase 1's request path.** `model_pro` is only referenced by the admin CLI.

---

## 9. Retrieval (`app/retrieval.py`)

Phase 1 uses **`ILIKE` only** against the `papers` table for the hardcoded course.

```python
def find_paper(session: Session, course_code: str, year: int | None, semester: str | None) -> Paper | None
```
Logic:
1. If `course_code != settings.hardcoded_course_code`: return `None`.
2. Build query: `select(Paper).where(Paper.course_code.ilike(course_code))`.
3. If `year is not None`: add `.where(Paper.year == year)`.
4. If `semester is not None`: add `.where(Paper.semester.ilike(semester))`.
5. `.order_by(Paper.year.desc()).limit(1)`.
6. Return `session.execute(query).scalar_one_or_none()`.

```python
def load_pdf_bytes(paper: Paper, gcs_client: storage.Client, bucket_name: str) -> tuple[bytes, str]
```
Downloads `gs://{bucket_name}/{paper.gcs_object}` into memory; returns `(bytes, f"{paper.course_code}_{paper.semester}_{paper.year}.pdf")`.

No fuzzy matching, no `pg_trgm`, no similarity ranking. If year is missing from the router output, retrieval just returns the most recent paper for the hardcoded course/semester.

---

## 10. Pipeline (`app/pipeline.py`)

Single orchestration entry point per inbound user message.

```python
def handle_message(session: Session, msg: WAMessage) -> Reply
```

Sequence (sync, no `asyncio`):

1. **Idempotency.** Insert a `RequestLog` row with `wa_message_id=msg.id`, `wa_from=msg.from_`, `user_text=(msg.text.body if msg.text else "")`, `outcome="received"`. If `IntegrityError` on the unique index → this is a Meta retry. Roll back, log info, raise `DuplicateMessage` (caller catches and returns the previously-computed reply OR a no-op text — Phase 1 returns a no-op `TextReply(body="")` and the route layer skips `send_reply` when body is empty).
2. **Type guard.** If `msg.type != "text"`: update `outcome="error"`, `error="non_text_message"`, return `TextReply(body="Send the course code, year, and semester as a text message, e.g. 'MTH102 harmattan 2022'.")`.
3. **Rate limit.** Count `RequestLog` rows in the last hour where `outcome != 'rate_limited'`. If `>= settings.request_rate_limit_per_hour`: update `outcome="rate_limited"`, return `TextReply(body="The bot is busy right now. Try again in a minute, in shaa Allah.")`.
4. **Route.** `routed, in_tok, out_tok = llm.route(msg.text.body)`. Update `RequestLog.flash_input_tokens / flash_output_tokens`. On `RouterError`: `outcome="error"`, return generic apology text reply.
5. **Branch on intent.**
   - `greeting` → `outcome="sent"`, return `TextReply(body="Wa alaykum salaam. Send a request like 'MTH102 harmattan 2022' to get the past paper.")`.
   - `other` → `outcome="not_found"`, return `TextReply(body="I only handle MTH102 past-paper requests for now. Try 'MTH102 rain 2023'.")`.
   - `paper_request` → continue.
6. **Course guard.** If `routed.course_code` is not the hardcoded course (case-insensitive): `outcome="not_found"`, return `TextReply(body=f"Phase 1 only serves {settings.hardcoded_course_code}. Other courses are coming soon.")`.
7. **Lookup.** `paper = retrieval.find_paper(session, settings.hardcoded_course_code, routed.year, routed.semester)`.
8. **Result.**
   - Found → update `RequestLog.routed_*`, `matched_paper_id=paper.id`, `outcome="sent"`. Return `DocumentReply(paper_id=paper.id, caption=f"{paper.course_code} {paper.semester.title()} {paper.year}")`.
   - Not found → `outcome="not_found"`. Return `TextReply(body=f"We don't have this {settings.hardcoded_course_code} paper yet — Ibrahim is uploading.")`.
9. Commit the session once at the end of the function. The route layer is responsible for catching exceptions and rolling back.

`handle_message` does **not** call `whatsapp.send_reply`. The route layer does, after `handle_message` returns.

---

## 11. FastAPI app (`app/main.py`)

### 11.1 Lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    app.state.http = httpx.Client(timeout=httpx.Timeout(connect=5, read=30, write=30, pool=5))
    app.state.gcs = storage.Client(project=settings.gcp_project)
    yield
    app.state.http.close()
    db.dispose()
```

### 11.2 Routes (signatures are exact)

```python
app = FastAPI(lifespan=lifespan, title="msa-paperbank", version="0.1.0")

@app.get("/healthz")
def healthz() -> dict: ...
# returns {"ok": True}

@app.get("/webhook")
def webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    challenge = whatsapp.verify_token_match(hub_mode, hub_verify_token, settings.wa_verify_token.get_secret_value())
    if challenge is None:
        raise HTTPException(status_code=403, detail="verify_token mismatch")
    return PlainTextResponse(hub_challenge, status_code=200)

@app.post("/webhook")
async def webhook_inbound(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    session: Session = Depends(get_session),
) -> Response:
    raw = await request.body()
    if not whatsapp.verify_signature(raw, x_hub_signature_256, settings.wa_app_secret.get_secret_value()):
        raise HTTPException(status_code=401, detail="bad signature")
    try:
        payload = WAWebhookPayload.model_validate_json(raw)
    except ValidationError as e:
        log.warning("invalid_payload", extra={"err": str(e)})
        return Response(status_code=200)   # always 200 to Meta on parseable-but-unexpected
    for entry in payload.entry:
        for change in entry.changes:
            for msg in (change.value.messages or []):
                try:
                    reply = pipeline.handle_message(session, msg)
                    if not (isinstance(reply, TextReply) and reply.body == ""):
                        whatsapp.send_reply(
                            to=msg.from_,
                            reply=reply,
                            paper_loader=lambda pid: retrieval.load_pdf_bytes(
                                session.get(Paper, pid), request.app.state.gcs, settings.gcs_bucket
                            ),
                        )
                except DuplicateMessage:
                    continue
                except Exception:
                    log.exception("handle_message_failed", extra={"wa_message_id": msg.id})
                    session.rollback()
    return Response(status_code=200)
```

The route is `async def` because `request.body()` is awaitable, but every downstream call (`pipeline.handle_message`, `whatsapp.send_reply`) is sync. **Do not** add `BackgroundTasks` or `asyncio.create_task`. The route runs the work inline and returns 200 only after replies are sent (or attempted).

### 11.3 Dependencies (`app/deps.py`)

```python
def get_session() -> Iterator[Session]:
    s = SessionLocal()
    try: yield s
    finally: s.close()
```

That is the only dependency in Phase 1.

---

## 12. Admin CLI (`admin/upload.py`) — Phase 1 minimum

`python -m admin.upload <pdf_path> --year YYYY --semester {harmattan,rain}` (no Pro model, no Drive importer, no OCR — those are Phase 2/3).

Steps:
1. `argparse` parses `pdf_path`, `--year`, `--semester`. Both flags required in Phase 1 (no auto-detect).
2. Read file bytes; compute `sha256 = hashlib.sha256(bytes).hexdigest()`.
3. Open `SessionLocal()`. Check `select(Paper).where(Paper.sha256 == sha256)`. If exists, print row and exit 0.
4. Compute `gcs_object = f"papers/MTH102/{year}-{semester}.pdf"`. Upload via `storage.Client().bucket(settings.gcs_bucket).blob(gcs_object).upload_from_string(bytes, content_type="application/pdf")`.
5. Insert `Paper(course_code="MTH102", semester=semester, year=year, gcs_object=gcs_object, sha256=sha256, uploaded_by=os.environ.get("USER", "ibrahim"))`. Commit.
6. Print the new paper ID.

No interactive confirmation prompt in Phase 1. No multi-course support.

---

## 13. Tests (`tests/`)

Use `pytest` + `respx` (for httpx mocks). Database tests use a local Postgres via `DATABASE_URL_TEST` env var; if unset, those tests are skipped. No Cloud SQL connector in tests.

| File | Cases |
|---|---|
| `test_signature.py` | (a) valid signature returns True; (b) tampered body returns False; (c) missing header returns False. |
| `test_router_schema.py` | (a) `RouterOutput.model_validate_json('{"intent":"paper_request","course_code":"MTH102","year":2022,"semester":"harmattan","confidence":0.95}')` succeeds; (b) year=1999 fails validation; (c) semester="fall" fails. |
| `test_retrieval.py` | (a) exact `(course, year, semester)` returns the paper; (b) missing year returns most recent; (c) wrong course returns None. |
| `test_pipeline.py` | (a) duplicate `wa_message_id` triggers `DuplicateMessage`; (b) non-text type returns guidance text; (c) `intent=greeting` returns greeting text; (d) found paper returns `DocumentReply` with correct caption; (e) not-found returns the literal "We don't have this MTH102 paper yet" string. LLM is monkey-patched to return a canned `RouterOutput`. |

No end-to-end test against real Meta or real Vertex in Phase 1.

---

## 14. Dockerfile

```
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY admin ./admin
EXPOSE 8080
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "60"]
```

One worker, eight threads. Concurrency is bounded by Cloud Run (`--concurrency 40`). Do not raise workers — Cloud Run scales by instance.

---

## 15. Error taxonomy

Define in `app/errors.py` (one file, four classes — add it to the layout above if missing):

```python
class AppError(Exception): ...
class WhatsAppError(AppError): ...
class RouterError(AppError): ...
class DuplicateMessage(AppError): ...
```

The route layer translates uncaught `AppError` to a structured log entry and returns 200 to Meta regardless. Never leak a stack trace to Meta's response body.

---

## 16. Non-goals reaffirmed

The execution agent must **not** add any of the following while implementing Phase 1, even if it seems harmless:

- `pg_trgm`, GIN indexes, fuzzy matching, Levenshtein, embeddings, pgvector.
- OpenCV, pdfminer, pypdf, PIL — Phase 1 does not parse or render PDFs; it just streams bytes from GCS to Meta.
- Google Drive client / importer.
- Curation, approval queue, admin web UI.
- Background tasks, Celery, Cloud Tasks, Pub/Sub, Cloud Functions.
- Multiple courses, dynamic course catalog, course aliases.
- Multi-turn clarification, button replies, list messages, interactive templates.
- Caching layer (Redis, in-memory).
- Webhook reply queue / retry worker.
- Alembic, dbmate, or any migration runner. SQL file is run by hand.

If any of these appear desirable mid-implementation, stop and amend `PHASE_1_SPEC.md` first.

---

## 17. Handoff checklist for the execution agent

- [ ] All files in §1 present, none extra.
- [ ] `requirements.txt` matches §2 exactly (patch versions may shift on first lock).
- [ ] `Settings` exposes every key in §3, no more.
- [ ] Three ORM models match §5.2 byte-for-byte.
- [ ] Pydantic schemas in §6 use `Field(validation_alias=...)` for `from_`, no `class Config`.
- [ ] Routes in §11.2 match the exact function signatures and decorators given.
- [ ] `pipeline.handle_message` follows §10 step ordering and outcome strings.
- [ ] No symbol from §16's non-goals list appears anywhere in the codebase.
- [ ] All four tests in §13 pass against a local Postgres.

When all 9 boxes are checked, Phase 1 is implementation-complete and ready for Cloud Run deploy.
