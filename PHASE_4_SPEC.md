# PHASE 4 — Technical Spec (Execution Blueprint)

**Source of truth:** `PRD.md` (canonical, narrow V1 scope). `MASTER_PRD.md` is reference-only; this phase finally consumes its `§8.3` (Drive importer) and `§9.2` (curation gate as a *real* gate, not a flag) deliverables.
**Audience:** the execution agent that will write the code. Do not deviate without amending this file first.
**Predecessors:** `PHASE_1_SPEC.md`, `PHASE_2_SPEC.md`, `PHASE_3_SPEC.md`. All merged. V1 is launched.

---

## 0. Phase 4 mission (one sentence)

Lift the single-course hardcode, add a Google Drive bulk importer, and turn `is_active_risk` from an *informational flag* into a *blocking curation gate* with an `admin curate` review CLI — so Hafeedh can bring the verified 782-file PAU corpus online safely without re-architecting the request path.

---

## 1. Scope (locked)

**In Phase 4:**

1. **Multi-course support.** Drop `settings.hardcoded_course_code` from the request path. Replace with a DB-backed `courses` lookup. Router prompt is rewritten to extract any course code; pipeline rejects requests for courses not in the DB with a clear text reply.
2. **Course catalog admin commands.** `python -m admin.courses {add|list|deactivate}`.
3. **Curation queue.** `is_active_risk=TRUE` papers (and any paper with `held_until > today`) are **excluded from retrieval** (already true in Phase 2/3), and now also **excluded from `paper_chunks` until approved**. New table `pending_papers` mirrors `papers` for the staging window. The Drive importer writes there; an approved row is *promoted* into `papers` + `paper_chunks` atomically.
4. **`admin curate` CLI.** Paginated interactive review of `pending_papers`. Approve / reject / defer / view-full / quit. Uses the transcript shape in `MASTER_PRD §13.4`.
5. **Drive importer.** `scripts/drive_import.py`. Auth via service account (ADC). Walks a Drive folder. Dedupes by SHA-256. For each file:
   - PDF → extract text via `pypdf` (Phase 4 path); if extraction yields < 200 chars, fall back to rendering pages via `pdf2image` and routing through the Phase 2 OCR pipeline.
   - Image (jpg/png/heic) → group by filename convention (`<COURSE>-<SESSION>-<YEAR>-q<N>.{jpg,png}`); send the group through the Phase 2 OCR pipeline.
   - Inserts to `pending_papers`; admin must `admin curate` to promote.
6. **Soft active-risk default flips.** New uploads in the current academic year (or year-1) get `held_until = (PAU calendar end-of-session + 30 days)` *only if a manual `--held-until YYYY-MM-DD` flag is provided*; otherwise `held_until=NULL` and the curation gate is the sole guard.
7. **`admin retire` extended.** Now accepts `--course <CODE>` to mass-retire all papers for a course (e.g., when a lecturer rotates the syllabus). Same confirmation flow.
8. **Pipeline reply changes for "course unknown"**: when a router intent is `paper_request` but the course is not in `courses`, reply with the closest 3 known course codes (from `pg_trgm` similarity on `courses.code`). Existing "Phase 1 only serves MTH102" text is removed.
9. **Tests** for course catalog, curation promote/reject, Drive importer dedupe, and the new pipeline branches.

**Out of Phase 4 (do not build):**

- Live user-photo ingestion via WhatsApp. The webhook still rejects non-text inbound. (V1.1.2 in MASTER_PRD; deferred again.)
- Multi-image *stitching* with timing windows and a 90s-sealed batch — that is the V1.1+ user-photo path. Drive importer uses filename conventions, no timing windows.
- A `users` table or `inferred_courses` reads. Still V1.2.
- BM25 / hybrid retrieval / reranker.
- Async / Pub/Sub / Cloud Tasks. Drive importer is a **synchronous CLI** that Hafeedh runs from his laptop. It is *not* a Cloud Run job.
- A web admin UI. `admin curate` stays in the terminal.
- CAC / Meta business verification (operational, no code).

---

## 2. Repository layout (delta from Phase 3)

Files added (✦) or modified (∆):

```
msa-paperbank/
├── PHASE_4_SPEC.md             ✦
├── README.md                   ∆ (multi-course quick-start; new Drive importer steps)
├── RUNBOOK.md                  ∆ (curation queue troubleshooting section)
├── requirements.txt            ∆ (+google-api-python-client, +google-auth, +pypdf, +pdf2image)
├── Makefile                    ∆ (+drive-import target)
├── scripts/
│   └── drive_import.py         ✦
├── app/
│   ├── config.py               ∆ (drive folder default, course catalog cache toggle)
│   ├── db.py                   ∆ (PendingPaper, PendingPaperChunk; courses gain is_active flag)
│   ├── retrieval.py            ∆ (no change to find_paper signature; multi-course already works once hardcode is removed at call sites — see §6)
│   ├── pipeline.py             ∆ (course guard reads from DB; nearest-3 reply on unknown)
│   ├── llm.py                  ∆ (router prompt rewritten; no MTH102 anchoring)
│   └── schemas.py              ∆ (RouterOutput.course_code stays free-form str)
├── admin/
│   ├── courses.py              ✦
│   ├── curate.py               ✦
│   ├── retire.py               ∆ (--course mass-retire mode)
│   └── upload.py               ∆ (no course hardcode; --course is now required)
├── migrations/
│   └── 004_phase4.sql          ✦
└── tests/
    ├── test_courses_admin.py        ✦
    ├── test_curate_promote.py       ✦
    ├── test_drive_import_dedupe.py  ✦
    ├── test_pipeline.py             ∆ (course-not-in-catalog branch + nearest-3 reply)
    └── test_retrieval.py            ∆ (assertions updated for multi-course)
```

No other files change. Do not "tidy" Phase 1–3 modules.

---

## 3. Pinned dependency additions (`requirements.txt`)

Append, do not reformat:

```
google-api-python-client==2.149.0
google-auth==2.36.0
google-auth-httplib2==0.2.0
pypdf==5.1.0
pdf2image==1.17.0
```

`pdf2image` requires `poppler` on the host running the Drive importer; document this in `RUNBOOK.md` (`apt-get install -y poppler-utils` on Debian/Ubuntu, `brew install poppler` on macOS). The Cloud Run image does **not** install poppler — Drive importer runs locally only.

Dev-only: nothing new.

---

## 4. Schema migration (`migrations/004_phase4.sql`)

Run order: must be applied after `003_phase3.sql`.

```sql
-- Multi-course support: courses gains is_active flag.
ALTER TABLE courses
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Pending (curation-staged) papers. Mirrors papers but never directly retrievable.
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

-- Convenience: trigram index on course codes for the nearest-3 reply path.
CREATE INDEX IF NOT EXISTS courses_code_trgm ON courses USING gin (code gin_trgm_ops);
```

No backfill: existing `papers` rows stay where they are. The seed for MTH102 from `001_init.sql` keeps that course active.

---

## 5. Configuration delta (`app/config.py`)

Add the following fields. All have defaults so existing deployments don't break.

| Field | Env var | Type | Default |
|---|---|---|---|
| `drive_default_folder_id` | `DRIVE_DEFAULT_FOLDER_ID` | `str \| None` | `None` |
| `drive_service_account_json` | `DRIVE_SERVICE_ACCOUNT_JSON` | `str \| None` | `None` (path to a service-account JSON; if `None`, falls back to ADC) |
| `course_catalog_cache_seconds` | `COURSE_CATALOG_CACHE_SECONDS` | `int` | `60` (in-process cache for the request-path course-membership check) |
| `unknown_course_suggest_count` | `UNKNOWN_COURSE_SUGGEST_COUNT` | `int` | `3` |

`hardcoded_course_code` stays in `Settings` for backward compat **but is no longer referenced by `app/pipeline.py` or `app/retrieval.py`**. The admin upload CLI no longer treats it as an implicit course; `--course` becomes required.

---

## 6. Retrieval change (`app/retrieval.py`)

Both `find_paper` and `find_paper_by_semantic_query`:

- **Drop the `course_code != settings.hardcoded_course_code` guard.** The course-membership check moves to `app/pipeline.py`.
- Add `.where(Paper.course_code.ilike(course_code))` is unchanged.
- The `is_retired`, active-risk soft, and pgvector-cosine logic is untouched.

A new helper:

```python
def known_courses(session: Session) -> set[str]:
    """Returns the set of UPPERCASE active course codes."""
```
- Reads `select(Course.code).where(Course.is_active == True)`. Returns `{c.upper() for c in rows}`.
- Cached in-process for `settings.course_catalog_cache_seconds` (use a tiny `(value, expires_at)` tuple in a module-level dict; no third-party cache lib).

A new helper for the unknown-course reply:

```python
def nearest_courses(session: Session, query_code: str, limit: int) -> list[str]:
    """pg_trgm similarity over courses.code; only is_active=TRUE; returns up to `limit` codes."""
```
- SQL: `SELECT code FROM courses WHERE is_active=TRUE ORDER BY similarity(code, :q) DESC LIMIT :n`.

---

## 7. Pipeline change (`app/pipeline.py`)

Step 6 (Course guard) is rewritten:

```python
# 6. Course guard (Phase 4: DB-backed)
known = retrieval.known_courses(session)
proposed = (routed.course_code or "").upper().replace(" ", "")
if not proposed or proposed not in known:
    suggestions = retrieval.nearest_courses(session, proposed, settings.unknown_course_suggest_count)
    log_entry.outcome = "not_found"
    session.commit()
    if suggestions:
        body = "I don't have that course yet. Did you mean: " + ", ".join(suggestions) + "?"
    else:
        body = "I don't have that course in the catalog. Send something like 'MTH102 harmattan 2022'."
    return TextReply(body=body)

course_code = proposed   # used in subsequent retrieval calls
```

Steps 7 / 7b are unchanged except that `settings.hardcoded_course_code` is replaced with `course_code` from above.

The `intent="other"` reply text is also updated to drop the "MTH102 only" claim:

```
"I only handle past-paper requests. Try something like 'MTH102 harmattan 2022'."
```

No new outcomes. No new RequestLog columns.

---

## 8. Router change (`app/llm.py`)

`ROUTER_SYSTEM_PROMPT` is rewritten — replace the entire string with:

```
You are the router for a PAU past-paper WhatsApp bot.
Given the user's WhatsApp text, output JSON matching the provided schema.

- If the user is asking for a past paper, set intent='paper_request' and:
  * course_code: the requested course as a single uppercase token without spaces, e.g. 'MTH102', 'CSC305', 'GST122'. If unsure, set to your best guess; the server will check membership.
  * year: 4-digit integer if mentioned, else null.
  * semester: 'harmattan' for first/Harmattan/dry-season requests, 'rain' for second/Rain/Harmattan terms's counterpart. Null if absent.
  * exam_session: 'CA1' | 'CA2' | 'exam' if obvious, else null. (Add as schema field; see schemas.py.)
- If the user greets or thanks, set intent='greeting'.
- Otherwise intent='other'.
- confidence: your own 0..1 estimate.
Do not invent course codes when the request is plainly off-topic.
```

`RouterOutput` gains `exam_session: Literal["CA1","CA2","exam"] | None = None`. The pipeline does not use it yet (Phase 4 retrieval still keys on `(course, year, semester)`); it is recorded into `request_log.routed_*` for telemetry only — but **without** a schema migration on `request_log`, since we won't store it in V1.1. (Future phase work if needed.)

---

## 9. Admin commands

### 9.1 `admin/courses.py`

```
python -m admin.courses add <CODE> --title <TEXT> --level {100,200,300,400} --department <TEXT>
python -m admin.courses list [--include-inactive] [--csv PATH]
python -m admin.courses deactivate <CODE> [--yes]
```

- `add`: insert into `courses`. Refuses on duplicate code with exit 1. Uppercases & strips whitespace from `<CODE>`.
- `list`: prints `courses` in a `tabulate` grid; `--include-inactive` shows deactivated rows.
- `deactivate`: sets `is_active=FALSE`. Confirmation prompt unless `--yes`. Does not delete the row (papers may reference it).

### 9.2 `admin/curate.py`

Paginated terminal review. Loop:

1. Fetch the next `pending_papers` row with `review_status='awaiting_review'`, oldest first. If none, print "Queue empty" and exit 0.
2. Print: `[<position>/<total>] pending_paper_id=<id>` + the rest per `MASTER_PRD §13.4` transcript: `course`, `year`, `session`, `source`, `gcs_object`, `pending_paper_chunks count`, plus a `Preview:` section with the first 3 chunks' first 120 chars.
3. Prompt: `Action [a/r/d/v/s/q]:` (approve / reject / defer / view-full / skip / quit).
   - `a`: prompt for an optional reason; promote inside one transaction:
     - `INSERT INTO papers (...) SELECT ... FROM pending_papers WHERE id=:id RETURNING id`
     - `INSERT INTO paper_chunks (paper_id, chunk_no, chunk_kind, text, embedding, created_at) SELECT :new_id, chunk_no, chunk_kind, text, embedding, created_at FROM pending_paper_chunks WHERE pending_paper_id=:id`
     - `UPDATE pending_papers SET review_status='approved', reviewer=:user, reviewed_at=now(), review_notes=:reason WHERE id=:id`
     - **`pending_papers` rows with `review_status='approved'` are kept** as audit trail; they are filtered out of the queue by `WHERE review_status='awaiting_review'`. (Add `'approved'` to the CHECK constraint in `004_phase4.sql`.)
   - `r`: prompt for a required reason; `UPDATE pending_papers SET review_status='rejected', reviewer, reviewed_at, review_notes=:reason WHERE id=:id`. Delete the GCS blob.
   - `d`: prompt for a defer reason; `UPDATE pending_papers SET review_status='deferred', review_notes=:reason WHERE id=:id` — reappears next time admin runs `curate`.
   - `v`: dump every chunk text to stdout, then re-prompt.
   - `s`: skip without state change (treated like defer but no notes recorded).
   - `q`: print "Saved progress." and exit 0.
4. After each action, refresh the queue size and continue.

Wait, the spec said the schema CHECK is `('awaiting_review','rejected','deferred')`. I need to add `'approved'` too. Update §4.

### 9.3 `admin/retire.py` (extension)

Add a mutually-exclusive group: `--course <CODE>` (mass mode) | `<paper_id>` (single mode).
- Mass mode: list affected paper_ids, count, prompt unless `--yes`, then `UPDATE papers SET is_retired=TRUE, retired_by, retired_at, retired_reason=:reason WHERE course_code=:CODE AND is_retired=FALSE`.
- Single-mode behavior is byte-identical to Phase 3.

### 9.4 `admin/upload.py` (extension)

Both `pdf` and `images` subcommands now require `--course <CODE>`. Course must exist in `courses` and be `is_active=TRUE`; otherwise exit 1 with "course not found in catalog; run admin courses add". Replace every `course_code="MTH102"` literal with `course_code=args.course.upper()`.

The `gcs_object` path becomes `papers/<COURSE>/<year>-<semester>-<session or 'exam'>.pdf`.

The `is_active_risk` computation is unchanged. **A new `--held-until YYYY-MM-DD` optional flag** is added; if provided, `held_until` is set on insert. Otherwise `NULL` and the curation queue is the only safeguard.

**Phase 4 ingestion target swap:** `admin upload images` now writes to `pending_papers` + `pending_paper_chunks`, **not** `papers` + `paper_chunks`. Promotion is via `admin curate`. (Phase 4 standardizes on the curation gate; Phase 2's direct-insert path is removed.) `admin upload pdf` continues to write directly to `papers` because PDFs uploaded via the admin CLI are pre-trusted; document this asymmetry in `RUNBOOK.md`.

---

## 10. Drive importer (`scripts/drive_import.py`)

Synchronous Python CLI. Run from Hafeedh's laptop. Auth via service-account JSON at `settings.drive_service_account_json` if set, else ADC. Scopes: `["https://www.googleapis.com/auth/drive.readonly"]`.

```
python scripts/drive_import.py --folder <DRIVE_FOLDER_ID> [--max N] [--dry-run] [--course <CODE>]
```

`--folder` defaults to `settings.drive_default_folder_id`.

Steps for each file in the folder (recursively, depth-first):

1. **Fetch metadata** (`drive.files.get`). Skip if `mimeType` is `application/vnd.google-apps.folder` (recurse into it).
2. **Filename grouping**: parse against the regex `^(?P<course>[A-Z]{2,4}[0-9]{2,3})-(?P<session>CA1|CA2|EXAM)-(?P<year>[0-9]{4})(?:-q(?P<page>[0-9]+))?\.(?P<ext>pdf|jpg|jpeg|png|heic)$`. If no match: log `unparsed_filename` and skip the file (do not abort the whole run).
3. **Course resolution**: if `--course` was passed, override the parsed course. Verify the course exists in `courses` and is active; if not, log `unknown_course` and skip.
4. **Group images**: collect all sibling files with the same `(course, session, year)` tuple and ext in {jpg, jpeg, png, heic}. Sort by `page`. Treat the group as one logical paper. For PDFs, the file is its own group of 1.
5. **SHA-256 dedupe**: compute the combined SHA-256 (concat in sorted order). Check `papers.sha256` AND `pending_papers.sha256`. If found in either: skip with `dedupe_hit`.
6. **Download** each file's bytes via `drive.files.get_media`. Cap each file at `settings.ocr_max_image_bytes`. PDFs may exceed this for V1.1; cap PDFs at 50 MB (Vertex inline limit).
7. **Render path**:
   - **PDF group**: extract text via `pypdf.PdfReader`. Concatenate per-page text. If total length ≥ 200 chars: split into chunks at the page-boundary level (one chunk per page; up to the first 25 pages); skip OCR. Combined PDF = the original bytes.
   - **PDF group with < 200 chars extracted**: render pages to PNG via `pdf2image.convert_from_bytes(dpi=200)`, run each rendered PNG through `app.preprocess.preprocess_paper_image`, then `app.ocr.ocr_paper(preprocessed_pngs)`.
   - **Image group**: preprocess each image, then `app.ocr.ocr_paper(preprocessed)`. Combined PDF = `app.pdfgen.stitch_images_to_pdf(preprocessed)`.
8. **Embed**: `app.embeddings.embed_many(chunk_texts)`.
9. **Active-risk**: same rule as Phase 2 (`year >= current_year - 1`). `held_until` not set unless a per-paper hold is hardcoded for the run (not exposed in V1.1).
10. **GCS upload**: `papers/<COURSE>/<year>-<session>-pending-<sha256[:8]>.pdf`.
11. **DB insert**: insert `pending_papers` row + N `pending_paper_chunks` rows in one transaction. Print `pending_id=<id>, chunks=<n>`.
12. **`--dry-run`**: stop after step 4 for each file; print what would be ingested without GCS/DB writes.
13. **Progress**: every 10 files, print `[<idx>/<total>] processed=<n_ok> dedupe=<n_skip> errors=<n_err>`.
14. **Final summary** on exit: counts and a path to a `drive_import_<run_id>.log` file written under the current directory.

Failure modes:
- Network blip mid-download: caught per-file, logged, continue.
- OCR error: caught per-group, logged, continue.
- DB integrity error (duplicate sha256): caught, logged as dedupe.

The importer is **idempotent** by SHA-256.

`Makefile` adds:

```
drive-import:
	python scripts/drive_import.py --folder $${DRIVE_FOLDER_ID:?set DRIVE_FOLDER_ID}
```

---

## 11. Tests (`tests/`)

All Phase 4 tests must pass alongside Phases 1–3.

### 11.1 `tests/test_courses_admin.py`
- `add` inserts a row; second `add` of the same code → exit 1.
- `list` returns the seeded MTH102 plus any added courses.
- `deactivate --yes` flips the flag; `list` (default) hides it; `list --include-inactive` shows it.

### 11.2 `tests/test_curate_promote.py`
- Insert a `pending_papers` row + 2 `pending_paper_chunks`.
- Run `admin.curate` with stdin scripted to `a\nreason\nq\n` (approve + reason + quit).
- Assert one new row in `papers` matching the pending fields, two rows in `paper_chunks`, and `pending_papers.review_status='approved'`.
- Reject case: stdin `r\nreason\nq\n`. Assert `review_status='rejected'` and the GCS blob delete was attempted (mock GCS client).

### 11.3 `tests/test_drive_import_dedupe.py`
- Mock the Drive client to return two files with the same SHA-256.
- Run the importer. Assert one `pending_papers` row, one log line `dedupe_hit`.
- Mock a third file with an unparseable filename. Assert `unparsed_filename` log; no row inserted.

### 11.4 `tests/test_pipeline.py` extensions
- `test_pipeline_unknown_course_returns_suggestions`: mock `llm.route` to return `intent="paper_request", course_code="MTH999"`. Insert MTH102, MTH101, MTH202 in `courses`. Assert reply is a `TextReply` whose body contains `MTH102` and `MTH202` (or any 3 nearest by trigram). Outcome is `"not_found"`.
- `test_pipeline_known_course_passes_to_retrieval`: mock `llm.route` for `CSC305`. Seed CSC305 in `courses`, a CSC305 paper in `papers`. Assert `DocumentReply` returned.

### 11.5 `tests/test_retrieval.py` extension
- Re-run existing assertions but now also assert that `find_paper` for CSC305 (when CSC305 papers exist) returns the right row, with no implicit MTH102 guard.

---

## 12. RUNBOOK / README updates

### `RUNBOOK.md`
- New §6: **Curation queue.** "After every Drive import, run `python -m admin.curate` to walk the queue. The bot does not retrieve a paper until you approve it."
- New §7: **Mass-retire a course.** `python -m admin.retire --course CSC305 --reason "syllabus rotated"`.
- §1 (token rotation) unchanged.
- §4 (silent bot triage) gains a step: "Check `python -m admin.courses list` — if the course the user asked about is missing or `is_active=FALSE`, that's the cause."

### `README.md`
Section "Adding a paper" now has three sub-steps:
1. Make sure the course exists: `python -m admin.courses add <CODE> --title ... --level ... --department ...`.
2. Either: bulk-import from Drive (`make drive-import` with `DRIVE_FOLDER_ID` set), or upload images directly (`python -m admin.upload images ...`).
3. Approve via `python -m admin.curate`.

---

## 13. Cost recheck

Phase 4 introduces no new request-path LLM calls. The Drive importer is a one-time bulk operation; per `MASTER_PRD §11.3`, the 782-file corpus is estimated at ~$10–13 in Pro vision OCR plus negligible embedding cost. That is a **one-time** spend on Hafeedh's laptop; it does not recur monthly.

Steady-state monthly cost remains ~$9.50 per `PRD.md §5.3`.

---

## 14. Non-goals reaffirmed

The execution agent must **not** add any of the following:

- Live user-photo ingestion via the WhatsApp webhook.
- Multi-image stitching with a 90s sealing window or an `image_batches` table.
- A `users` table or any read of inferred profile data.
- Async / Pub/Sub / Cloud Tasks / Cloud Scheduler. Drive importer stays a sync CLI.
- A web admin UI of any kind.
- BM25 / hybrid retrieval / reranker.
- A migration tool. Migrations stay hand-applied SQL.
- Templated WhatsApp messages.
- An automated PAU-calendar lookup for `held_until`. The flag stays manual in V1.1.
- A `submitted` table for student-side photo submissions. (V1.1.2; deferred.)
- Cloud Run cold-start work: no `--min-instances=1`, no warm-up cron.

If any become tempting, stop and amend `PHASE_4_SPEC.md` first.

---

## 15. Definition of Done (Phase 4)

A maintainer (Hafeedh or Ibrahim) on his laptop:

1. Pulls `master`, runs `pip install -r requirements.txt`. No errors.
2. Applies `migrations/004_phase4.sql`. `\d courses` shows `is_active`. `\d pending_papers` and `\d pending_paper_chunks` exist.
3. Runs `python -m admin.courses add CSC305 --title "Algorithms" --level 300 --department "Computer Science"`. Then `python -m admin.courses list` shows MTH102 + CSC305.
4. Sets `DRIVE_FOLDER_ID=<id>` and runs `make drive-import`. Importer walks the folder, inserts to `pending_papers`, prints summary counts.
5. Runs `python -m admin.curate`. Reviews 5–10 papers. Approves a known-safe one. `python -m admin.list --course CSC305` now includes it.
6. Sends a WhatsApp message "CSC305 harmattan 2022" → receives the approved CSC305 PDF.
7. Sends "MTH999 something" → receives a "Did you mean: MTH102, MTH101, ..." text reply.
8. Runs `python -m admin.retire --course CSC305 --reason "test mass retire" --yes`. `admin.list --course CSC305` now empty; `--include-retired` shows the rows.
9. `pytest -q` passes, including every Phase 4 test in §11.
10. `make smoke` still prints `SMOKE OK`.
11. Total monthly cost (post the one-time Drive import) remains within the $15 ceiling per `PRD.md §5.3`.

When all 11 are green, Phase 4 is implementation-complete and ready for the next-phase planning cycle.
