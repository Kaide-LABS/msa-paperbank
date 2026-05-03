# PHASE 2 — Technical Spec (Execution Blueprint)

**Source of truth:** `PRD.md` (canonical, narrow V1 scope). `MASTER_PRD.md` is reference-only — its broader vision (Drive importer, user-photo ingestion, full PAU corpus, vector-only retrieval) is **not** in scope here.
**Audience:** the execution agent that will write the code. Do not deviate without amending this file first.
**Predecessor:** `PHASE_1_SPEC.md`. Phase 1 is approved and merged. Phase 2 builds on top of the existing schema and request flow without rewriting them.

---

## 0. Phase 2 mission (one sentence)

Add image-based paper ingestion (photo → OpenCV preprocess → Gemini 3.1 Pro Preview OCR → reportlab combined PDF → GCS) and a semantic-fallback retrieval layer (`gemini-embedding-001` + pgvector cosine ANN) **invoked exclusively by the admin CLI**. No change to the WhatsApp request path's authentication, signature checks, idempotency, or rate-limit logic. No Drive importer. No live user-photo ingestion. Still MTH102-only.

---

## 1. Scope (locked)

**In Phase 2:**
1. Postgres extensions: enable `vector` and `pg_trgm`. Migration file `migrations/002_phase2.sql`.
2. New table `paper_chunks` (question-level chunks with 768-dim embeddings).
3. Additive columns on `papers`: `course_title TEXT`, `exam_session TEXT` (nullable; carries `'CA1'|'CA2'|'exam'` etc. when known; `semester` already exists), `is_active_risk BOOLEAN NOT NULL DEFAULT FALSE`, `held_until DATE NULL`, `pdf_was_generated BOOLEAN NOT NULL DEFAULT FALSE`.
4. New module `app/preprocess.py` — OpenCV grayscale → denoise → deskew → adaptive threshold.
5. New module `app/ocr.py` — Gemini 3.1 Pro Preview vision OCR with structured JSON output.
6. New module `app/embeddings.py` — `gemini-embedding-001` @ 768-dim, single-input-per-call, bounded concurrency in admin CLI.
7. New module `app/pdfgen.py` — reportlab: stitch N preprocessed images into one combined PDF, upload to GCS.
8. **Admin CLI gains a second subcommand**: `python -m admin.upload images <img_path> [<img_path> ...] --year YYYY --semester {harmattan,rain} [--session CA1|CA2|exam]`. Invokes preprocess → OCR → embed → pdfgen → DB insert atomically.
9. **Retrieval layer extended in `app/retrieval.py`**: keep ILIKE as the primary path (per `PRD.md`); add a `find_paper_by_semantic_query(session, course_code, query_text, top_k=1) -> Paper | None` that's used **only** as a fallback when ILIKE returns nothing AND the router gave a confidence ≥ 0.5 with `intent="paper_request"` but year was missing or wrong.
10. Active-risk computation at upload time only: `is_active_risk = (year >= current_year - 1)`. Computed and stored, **not used** to block insertion in Phase 2 — the admin always intends to upload. The flag exists for Phase 3's optional curation surface and for a retrieval-time soft-filter described in §8.
11. New tests: `test_preprocess.py`, `test_ocr_schema.py`, `test_embeddings.py`, `test_retrieval_semantic.py`, plus an extension to `test_pipeline.py` covering the semantic-fallback branch.

**Out of Phase 2 (do not build):**
- Drive importer / `scripts/drive_import.py`. (Phase 3 candidate.)
- Live user photo ingestion via WhatsApp. The `POST /webhook` handler still rejects non-text inbound messages with the existing guidance text in `app/pipeline.py`.
- Multi-course catalog. Course is still hardcoded to `settings.hardcoded_course_code` (`MTH102`).
- A `users` table or implicit-profile updates. `MASTER_PRD §4.4` explicitly defers reads to V1.2.
- A `pending_submissions` table or a curation review CLI. Active-risk is *flagged*, not *gated*.
- A separate `message_log` table. We continue using `request_log` from Phase 1.
- Outbound reply changes. We continue sending the PDF directly via Meta media upload (Phase 1 §11.2 of PRD.md). No signed-URL list reply.
- BackgroundTasks / async / queues. All Phase 2 work runs sync inside the admin CLI process.

---

## 2. Repository layout (delta from Phase 1)

Files added (✦) or modified (∆):

```
msa-paperbank/
├── PHASE_2_SPEC.md                ✦
├── requirements.txt               ∆ (+pgvector, +opencv-python-headless, +reportlab, +numpy)
├── app/
│   ├── preprocess.py              ✦
│   ├── ocr.py                     ✦
│   ├── embeddings.py              ✦
│   ├── pdfgen.py                  ✦
│   ├── db.py                      ∆ (Paper gains new columns; new PaperChunk model)
│   ├── retrieval.py               ∆ (find_paper_by_semantic_query added)
│   ├── pipeline.py                ∆ (semantic fallback wired in; ≤ 12 added LOC)
│   ├── schemas.py                 ∆ (OcrPaperExtraction Pydantic model added)
│   └── llm.py                     ∆ (Pro vision call helper added; router untouched)
├── admin/
│   └── upload.py                  ∆ (new `images` subcommand; existing pdf path unchanged)
├── migrations/
│   └── 002_phase2.sql             ✦
└── tests/
    ├── test_preprocess.py         ✦
    ├── test_ocr_schema.py         ✦
    ├── test_embeddings.py         ✦
    ├── test_retrieval_semantic.py ✦
    └── test_pipeline.py           ∆ (one new test for semantic fallback)
```

No other files change. **Do not** rename existing files, restructure packages, or "tidy" Phase 1 modules.

---

## 3. Pinned dependency additions (`requirements.txt`)

Append, do not reformat:

```
pgvector==0.3.6
opencv-python-headless==4.10.0.84
numpy==2.0.2
reportlab==4.2.5
Pillow==11.0.0
```

`Pillow` is required by reportlab for image embedding. `numpy` is OpenCV's transitive runtime dep but pin it explicitly to avoid silent ABI mismatches.

Dev-only (in `pyproject.toml`'s `dev` extras): `pytest-mock==3.14.0`.

---

## 4. Schema migration (`migrations/002_phase2.sql`)

Run order: must be applied after `001_init.sql` and before any Phase 2 code path executes.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS course_title TEXT,
    ADD COLUMN IF NOT EXISTS exam_session TEXT,                 -- 'CA1' | 'CA2' | 'exam' | NULL
    ADD COLUMN IF NOT EXISTS is_active_risk BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS held_until DATE NULL,
    ADD COLUMN IF NOT EXISTS pdf_was_generated BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS paper_chunks (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    chunk_no INT NOT NULL,                       -- 1-based ordinal within the paper
    chunk_kind TEXT NOT NULL DEFAULT 'question', -- 'question' | 'header' | 'page' (Phase 2: always 'question')
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
```

No backfill of `papers` rows from Phase 1: those rows had no images and no embeddings; they remain ILIKE-only. The semantic-fallback path simply finds nothing for them, which is correct.

`paper_chunks.embedding NOT NULL` is intentional — every row created by the Phase 2 pipeline has an embedding. If embedding fails, the whole upload aborts and the row is never inserted.

---

## 5. Configuration delta (`app/config.py`)

Add the following fields to `Settings`. All have defaults so Phase 1 deployments keep working without env updates.

| Field | Env var | Type | Default |
|---|---|---|---|
| `model_embedding` | `MODEL_EMBEDDING` | `str` | `"gemini-embedding-001"` |
| `embedding_dim` | `EMBEDDING_DIM` | `int` | `768` |
| `ocr_max_image_bytes` | `OCR_MAX_IMAGE_BYTES` | `int` | `7_000_000` (Meta's 7 MB cap; same as Vertex inline limit) |
| `ocr_max_images_per_paper` | `OCR_MAX_IMAGES_PER_PAPER` | `int` | `12` |
| `embedding_concurrency` | `EMBEDDING_CONCURRENCY` | `int` | `8` |
| `semantic_fallback_top_k` | `SEMANTIC_FALLBACK_TOP_K` | `int` | `3` |
| `semantic_fallback_min_router_confidence` | `SEMANTIC_FALLBACK_MIN_ROUTER_CONFIDENCE` | `float` | `0.5` |

---

## 6. OpenCV preprocessing (`app/preprocess.py`)

Single sync function, no global state.

```python
def preprocess_paper_image(image_bytes: bytes) -> bytes
```

Contract:
1. Decode with `cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)`. If `None`, raise `PreprocessError("undecodable image")`.
2. Reject if either dimension is `< 200 px` (`PreprocessError("image too small")`).
3. Convert to grayscale via `cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)`.
4. Denoise with `cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)`.
5. Deskew:
   - Compute edges: `edges = cv2.Canny(denoised, 50, 150, apertureSize=3)`.
   - `lines = cv2.HoughLinesP(edges, 1, np.pi/180, 200, minLineLength=denoised.shape[1]//4, maxLineGap=20)`.
   - If at least one line: take the median angle (radians) of all line angles bounded to `[-pi/4, pi/4]`; rotate the image by `-degrees` using `cv2.getRotationMatrix2D` + `cv2.warpAffine` with `cv2.BORDER_REPLICATE`.
   - If no lines or angle within `±0.5°`: skip rotation.
6. Threshold: `cv2.adaptiveThreshold(rotated, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, blockSize=31, C=10)`.
7. Re-encode as PNG: `ok, buf = cv2.imencode(".png", thresh); if not ok: raise PreprocessError("encode failed")`.
8. Return `bytes(buf.tobytes())`.

`PreprocessError(AppError)` is added to `app/errors.py`.

The function is pure (no I/O, no globals). Callers handle file/GCS reads.

---

## 7. OCR (`app/ocr.py`)

Reuses the module-level `client = genai.Client(...)` from `app/llm.py` (do not create a second client). Add to `app/llm.py` a thin helper for Pro vision calls; OCR's prompt and schema live in `app/ocr.py`.

### 7.1 Pydantic schema (`app/schemas.py` addition)

```python
class OcrQuestion(BaseModel):
    number: int                                 # 1-based; OCR best-effort
    text: str

class OcrPaperExtraction(BaseModel):
    course_code: str | None = None              # raw extraction; admin always overrides via CLI flags
    course_title: str | None = None
    exam_year: int | None = None
    exam_session: Literal["CA1", "CA2", "exam", "first", "second"] | None = None
    questions: list[OcrQuestion]
    error: str | None = None                    # set when the model couldn't extract; questions=[] in that case

    @field_validator("exam_year")
    @classmethod
    def _year_range(cls, v):
        if v is None: return v
        if not (2000 <= v <= 2100): raise ValueError("year out of range")
        return v
```

### 7.2 OCR helper

```python
OCR_SYSTEM_PROMPT = """You are extracting structured data from a PAU exam paper image.
Return JSON ONLY matching the provided schema.
- questions[]: each entry must contain the verbatim question text. Preserve mathematical notation as plain text.
- If multiple images are part of one paper, treat them as a single logical document; the user will pass them in reading order.
- If the image is unreadable, set error to a short reason and questions=[].
"""

def ocr_paper(image_bytes_list: list[bytes]) -> OcrPaperExtraction
```

Implementation contract:
- Build `parts = [types.Part.from_bytes(b, mime_type="image/png") for b in image_bytes_list]` (PNG because preprocess outputs PNG).
- Single call: `client.models.generate_content(model=settings.model_pro, contents=parts, config=types.GenerateContentConfig(system_instruction=OCR_SYSTEM_PROMPT, response_mime_type="application/json", response_schema=OcrPaperExtraction, temperature=0.0, max_output_tokens=4096))`.
- Parse `OcrPaperExtraction.model_validate_json(resp.text)`.
- On any exception: re-raise as `OcrError` (new `AppError` subclass).
- The function does **not** persist anything. The caller (admin CLI) uses the result.

The OCR call is the only Pro invocation in the system. It is never on the request path — `app/pipeline.py` does not import `app.ocr`.

---

## 8. Embeddings (`app/embeddings.py`)

`gemini-embedding-001` accepts one input per request (per `MASTER_PRD` Appendix B note). Phase 2 batches via thread pool, not asyncio (the admin CLI is sync — keep it boring).

```python
def embed_one(text: str) -> list[float]
def embed_many(texts: list[str], concurrency: int | None = None) -> list[list[float]]
```

`embed_one` contract:
- `resp = client.models.embed_content(model=settings.model_embedding, contents=text, config=types.EmbedContentConfig(output_dimensionality=settings.embedding_dim, task_type="RETRIEVAL_DOCUMENT"))`.
- Returns `resp.embeddings[0].values` cast to `list[float]`. Length must equal `settings.embedding_dim`; if not, raise `EmbeddingError`.
- For the *query* path (semantic fallback in retrieval), a sibling `embed_query(text: str) -> list[float]` calls the same model with `task_type="RETRIEVAL_QUERY"` and returns the same shape. Two functions, same client.

`embed_many` contract:
- `concurrency = concurrency or settings.embedding_concurrency`. Cap at 16.
- Use `concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)`. Submit `embed_one` per text. Collect in input order. Re-raise the first exception encountered as `EmbeddingError("batch failed: <n> ok, <m> failed")`; do not return partial results.
- No retries. Admin reruns the upload command.

`EmbeddingError(AppError)` is added to `app/errors.py`.

---

## 9. PDF generation (`app/pdfgen.py`)

```python
def stitch_images_to_pdf(image_bytes_list: list[bytes]) -> bytes
def upload_pdf(gcs_client: storage.Client, bucket_name: str, gcs_object: str, pdf_bytes: bytes) -> None
```

`stitch_images_to_pdf`:
- Use `reportlab.pdfgen.canvas.Canvas` writing to a `BytesIO`.
- For each image: open via `PIL.Image.open(BytesIO(b))`. Convert to `"RGB"` if mode != `"RGB"`. Compute page size to preserve aspect: `page = (image.width, image.height)` capped at `reportlab.lib.pagesizes.A4`'s diagonal × 2 (sanity). Use `c.setPageSize((w, h))`, then `c.drawImage(ImageReader(image), 0, 0, width=w, height=h)`, then `c.showPage()`.
- `c.save()`. Return `BytesIO.getvalue()`.

`upload_pdf` is a 4-line wrapper around `bucket.blob(gcs_object).upload_from_string(pdf_bytes, content_type="application/pdf")`. No retries; GCS client retries idempotent ops itself.

---

## 10. Updated retrieval (`app/retrieval.py`)

Keep `find_paper(...)` (ILIKE) **unchanged**. Add:

```python
def find_paper_by_semantic_query(
    session: Session,
    course_code: str,
    query_text: str,
    top_k: int | None = None,
) -> Paper | None
```

Logic:
1. Course guard: same as `find_paper` — must equal `settings.hardcoded_course_code` (case-insensitive); else return None.
2. Compute `qvec = embeddings.embed_query(query_text)`.
3. Run:
   ```python
   stmt = (
       select(Paper)
       .join(PaperChunk, PaperChunk.paper_id == Paper.id)
       .where(Paper.course_code.ilike(course_code))
       .order_by(PaperChunk.embedding.cosine_distance(qvec))
       .limit(top_k or settings.semantic_fallback_top_k)
   )
   ```
   (Requires `from pgvector.sqlalchemy import Vector` and a `Mapped[list[float]] = mapped_column(Vector(768))` on `PaperChunk.embedding`. Cosine distance operator is provided by pgvector's SQLAlchemy integration.)
4. Return the *first distinct* Paper from the result (multiple chunks may belong to the same paper; we want the closest paper). If no rows, return `None`.

**Soft active-risk filter (Phase 2 retrieval-time behavior):**
Both `find_paper` and `find_paper_by_semantic_query` add the predicate:
```python
.where(or_(Paper.is_active_risk == False, Paper.held_until == None, Paper.held_until <= func.current_date()))
```
This makes active-risk papers retrievable as soon as `held_until` has passed. With Phase 2's default `held_until = NULL` for everything, behavior is unchanged from Phase 1 (everything is retrievable); the column is wired in so Phase 3's curation review can populate `held_until` without touching retrieval code.

`load_pdf_bytes` is unchanged.

---

## 11. Pipeline change (`app/pipeline.py`)

Exactly one inserted block, between current step 7 (Lookup) and step 8 (Result). The rest of the function is byte-identical to Phase 1.

```python
# 7. Lookup
paper = retrieval.find_paper(session, settings.hardcoded_course_code, routed.year, routed.semester)

# 7b. Phase 2 semantic fallback (added)
if paper is None and routed.confidence >= settings.semantic_fallback_min_router_confidence:
    try:
        paper = retrieval.find_paper_by_semantic_query(
            session, settings.hardcoded_course_code, msg.text.body
        )
    except EmbeddingError:
        # Soft fallback: stay with paper=None and let step 8 reply "not found".
        log.warning("semantic_fallback_embedding_failed", extra={"wa_message_id": msg.id})

# 8. Result (unchanged)
```

**No outcome string change. No new RequestLog column.** Telemetry for the fallback is the existing log line plus the (already-recorded) `routed_*` fields and the `matched_paper_id` field. If the fallback succeeds, `outcome="sent"` as before; if not, `outcome="not_found"`.

`from app.errors import EmbeddingError` is added at the top of `pipeline.py`.

---

## 12. `app/llm.py` addition (vision helper)

A single helper used only by `app/ocr.py`. Keeps the `client = genai.Client(...)` instance singular.

```python
def call_pro_vision(parts: list[types.Part], system_instruction: str, response_schema: type[BaseModel]) -> str:
    """Returns the raw resp.text. Caller does Pydantic validation."""
    resp = client.models.generate_content(
        model=settings.model_pro,
        contents=parts,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.0,
            max_output_tokens=4096,
        ),
    )
    return resp.text
```

Router (`route(...)`) is **untouched**.

---

## 13. Admin CLI extension (`admin/upload.py`)

The existing `python -m admin.upload <pdf_path> --year ... --semester ...` flow stays exactly as Phase 1. Add subcommand structure: refactor the file to use `argparse` subparsers `pdf` (Phase 1 behavior; default for backward compat) and `images` (Phase 2 new flow). Both subcommands share `--year`, `--semester`, optional `--session`.

### 13.1 CLI surface

```
python -m admin.upload pdf <pdf_path> --year YYYY --semester {harmattan,rain} [--session {CA1,CA2,exam}]
python -m admin.upload images <img1> [<img2> ...] --year YYYY --semester {harmattan,rain} [--session {CA1,CA2,exam}] [--no-ocr]
```

`--no-ocr` (images only, dev escape hatch): skips OCR + embedding; produces a chunk-less paper with the combined PDF only. Use for testing the pipeline plumbing without burning Pro tokens.

### 13.2 `images` subcommand sequence (sync, top-to-bottom)

1. **Argparse validation.** `1 <= len(image_paths) <= settings.ocr_max_images_per_paper`. Each file must exist and be ≤ `settings.ocr_max_image_bytes`.
2. **Read raw bytes** for every image. Compute `sha256_combined = hashlib.sha256(b"".join(raw_bytes_list)).hexdigest()`. **This is the dedupe key.** Check `select(Paper).where(Paper.sha256 == sha256_combined)`; if found, print and exit 0.
3. **Preprocess**: `preprocessed = [preprocess_paper_image(b) for b in raw_bytes_list]`. Surfaces `PreprocessError` to the user with a clear `print(...)` and `sys.exit(2)`.
4. **OCR (skip when `--no-ocr`)**: `ocr_result = ocr_paper(preprocessed)`. If `ocr_result.error is not None or not ocr_result.questions`: print the error and exit 3 unless `--force` is also set (`--force` is **not** in Phase 2; reserved). For Phase 2: hard-fail on empty.
5. **Compute active-risk**: `is_active_risk = (args.year >= datetime.now(timezone.utc).year - 1)`. Set `held_until = None` for Phase 2 (Phase 3 will populate this from curation).
6. **Stitch PDF**: `pdf_bytes = stitch_images_to_pdf(preprocessed)`.
7. **Compute GCS object**: `gcs_object = f"papers/MTH102/{args.year}-{args.semester}-{args.session or 'exam'}.pdf"`. If a blob already exists at that path, append `-{sha256_combined[:8]}` before `.pdf` and use that.
8. **Upload PDF**: `upload_pdf(gcs_client, settings.gcs_bucket, gcs_object, pdf_bytes)`.
9. **Embed all questions** (skip when `--no-ocr`): `vectors = embed_many([q.text for q in ocr_result.questions])`. On `EmbeddingError`: do **not** insert the paper row. Delete the GCS blob (`bucket.blob(gcs_object).delete()`), print, exit 4. The system must not have a paper without embeddings.
10. **Insert in one transaction:**
    ```python
    with SessionLocal.begin() as session:
        paper = Paper(
            course_code="MTH102",
            course_title=ocr_result.course_title,        # may be None
            semester=args.semester,
            exam_session=args.session,
            year=args.year,
            gcs_object=gcs_object,
            sha256=sha256_combined,
            uploaded_by=os.environ.get("USER", "ibrahim"),
            is_active_risk=is_active_risk,
            held_until=None,
            pdf_was_generated=True,
        )
        session.add(paper)
        session.flush()  # populate paper.id
        if not args.no_ocr:
            session.add_all([
                PaperChunk(paper_id=paper.id, chunk_no=i+1, text=q.text, embedding=vec)
                for i, (q, vec) in enumerate(zip(ocr_result.questions, vectors))
            ])
    print(f"Uploaded paper id={paper.id}, chunks={len(ocr_result.questions) if not args.no_ocr else 0}")
    if is_active_risk:
        print("Note: marked is_active_risk=TRUE (year within current academic window).")
    ```
11. **Idempotency on partial failure**: if step 10 raises after step 8 succeeded, log and **delete the GCS blob** in a `finally` to avoid orphans. Same on `EmbeddingError` at step 9.

### 13.3 `pdf` subcommand

Identical to Phase 1's existing flow (read bytes → sha → optional dedupe → upload → insert). It does **not** OCR or embed — Phase 1 PDFs remain ILIKE-retrievable only. This is intentional and documented inline in the CLI's help text.

---

## 14. Tests (`tests/`)

All Phase 2 tests must pass alongside Phase 1's. Use `pytest-mock` for mocking the LLM client. Embedding values in tests are deterministic small lists, not real model output.

### 14.1 `tests/test_preprocess.py`
- `test_preprocess_decodes_png_jpg`: feed a 400×400 synthetic JPEG; assert output is bytes and `cv2.imdecode` reads it back.
- `test_preprocess_rejects_tiny_image`: 50×50 image → `PreprocessError`.
- `test_preprocess_rejects_garbage`: `b"\x00\x01\x02"` → `PreprocessError("undecodable image")`.

### 14.2 `tests/test_ocr_schema.py`
- `OcrPaperExtraction.model_validate_json('{"questions":[{"number":1,"text":"Solve dy/dx=2x"}]}')` succeeds with `error=None`.
- `exam_year=1990` raises `ValidationError`.
- `exam_session="fall"` raises `ValidationError`.
- `error="image blank", questions=[]` validates (used to signal failure).

### 14.3 `tests/test_embeddings.py`
- `embed_one` mocks `client.models.embed_content` to return a fixture with `embeddings[0].values = [0.1] * 768`; asserts return shape and dtype.
- `embed_one` with mock returning length 512 → `EmbeddingError`.
- `embed_many(["a","b","c"])` mocks per-call; asserts return is a list of 3 lists, in input order.
- `embed_many(["a","b","c"])` where the 2nd call raises → `EmbeddingError`; no partial results returned.

### 14.4 `tests/test_retrieval_semantic.py`
- Skipped unless `DATABASE_URL_TEST` is a Postgres URL with `vector` extension installed locally (xfail otherwise; do not silently pass).
- Insert one Paper with two PaperChunks whose embeddings are unit vectors pointing at known directions; query an embedding closer to the second chunk; assert returned paper id matches.
- Wrong course → `None`.
- Active-risk paper with `held_until > today` → excluded.

### 14.5 `tests/test_pipeline.py` extension (one new test)
- `test_pipeline_semantic_fallback_when_ilike_misses`: mock `llm.route` to return `intent="paper_request", course_code="MTH102", year=None, confidence=0.8`. Insert a Paper + chunks. Mock `retrieval.find_paper` to return None. Mock `retrieval.find_paper_by_semantic_query` to return the inserted Paper. Assert pipeline returns `DocumentReply` with that paper's id.

---

## 15. Cost model update

Per-message LLM cost on the WhatsApp request path: **unchanged**. The semantic fallback only fires when ILIKE misses AND router confidence ≥ 0.5; in that case it adds one `gemini-embedding-001` query call ≈ 30 input tokens at $0.000045/1k = **~$0.0000014/call**. Negligible.

Per-paper ingestion cost (admin-side, not user-facing):
- Pro vision OCR: ~1290 image tokens × N images + ~300 prompt tokens in, ~500 out. Assume 2 images/paper average. Vertex `gemini-3.1-pro-preview` global pricing (2026-05-03): $2/1M input, $12/1M output → `(2*1290 + 300)*$2 + 500*$12 / 1M ≈ $0.0117/paper`.
- Embeddings: 6 questions × 200 tokens × $0.000045/1k ≈ $0.00005/paper.
- **~$0.012 per paper. ~$1.20 for a 100-paper batch.** Well within `PRD.md` §5.3's $15/mo ceiling.

No change to `PRD.md` §5.3's monthly steady-state estimate (still ~$9.50). The Pro budget there already accounted for 50 PDFs/mo at ~$0.072/each; image-mode papers at ~$0.012 are cheaper, so the budget still holds.

---

## 16. Non-goals reaffirmed

The execution agent must **not** add any of the following while implementing Phase 2, even if they appear elsewhere in `MASTER_PRD.md`:

- A Drive importer (`scripts/drive_import.py`) — Phase 3 candidate, not Phase 2.
- A `users` table, implicit-profile updates, or any read of `inferred_courses`.
- A `pending_submissions` table or a curation review CLI.
- A `message_log` table or any rename of `request_log`.
- Outbound reply changes (signed URLs in text bodies). Stay on Meta media-upload from Phase 1.
- Live ingestion of user-sent images via the WhatsApp webhook. The pipeline's non-text guard remains the single source of truth.
- Multi-course retrieval, course aliases, or removal of the hardcoded-course guard.
- BackgroundTasks, asyncio, threads on the request path. The thread pool in `embeddings.embed_many` runs only inside the admin CLI process.
- BM25 / hybrid retrieval, reranking, RRF.
- Cohere, OpenAI, or any non-Google model.
- Cloud Tasks, Cloud Scheduler, Pub/Sub, Eventarc, Workflows.
- A web UI of any kind.

If any of these become tempting mid-implementation, stop and amend `PHASE_2_SPEC.md` first.

---

## 17. Definition of Done (Phase 2)

A maintainer (Ibrahim) on his laptop:

1. Pulls `master`, runs `pip install -r requirements.txt`. No build errors.
2. Connects to Cloud SQL, runs `psql -f migrations/002_phase2.sql`. `\dx` lists `vector` and `pg_trgm`. `\d papers` shows the new columns. `\d paper_chunks` exists with an HNSW index.
3. Runs `python -m admin.upload images ./samples/mth102-har-2022-p1.jpg ./samples/mth102-har-2022-p2.jpg --year 2022 --semester harmattan --session exam`. Output: paper id printed, chunk count printed. GCS object exists. `select count(*) from paper_chunks where paper_id=...` ≥ 1.
4. Sends "MTH 102 harmattan 2022" via real WhatsApp → receives the combined PDF (Phase 1 path; ILIKE hit).
5. Sends "give me the diff eq paper from second sem 2022" with no year/semester certainty → ILIKE misses → semantic fallback hits the same paper → student receives the PDF.
6. `pytest -q` passes, including every Phase 2 test in §14.
7. `gcloud run deploy` succeeds; `/healthz` returns `{"ok": true}`; `/webhook` GET still returns the verify challenge; `/webhook` POST still rejects bad signatures with 401.
8. Total monthly Vertex spend trajectory unchanged within the $15 ceiling.

When all 8 are green, Phase 2 is implementation-complete and ready to hand to the execution agent for Phase 3 planning.
