# Project context — Paperbank `/download` media typing & `/tool/retrieve` OpenAPI docs

## Stack and why
- **Python 3.12** (`pyproject.toml` already declares `requires-python = ">=3.12"`). No change to the floor.
- **FastAPI + Starlette + Pydantic (v2)** — the existing web stack. The two defects live in FastAPI route declarations and a Starlette `Response`, so the fix is entirely within these.
- **SQLAlchemy** — present in the app but untouched here (`/tool/retrieve` reaches it only through `retrieval.answer_query`, which is out of scope).
- **Python standard library only** for the new logic: `mimetypes` (extension → media type) and plain string ops for filename sanitising. **No new third-party dependency** is permitted.
- **Testing: `fastapi.testclient.TestClient`** with dependency overrides and injected fakes; no network, no real DB.

## Repo layout (relevant parts)
- `app/main.py` — FastAPI app; contains `GET /download` and `POST /tool/retrieve`. **The only app file edited this phase.**
- `app/auth.py` — `require_tool_token` bearer dependency (401 on missing/malformed/wrong token). **Read-only here.**
- `app/retrieval.py` — `answer_query()` returns `RetrievalResult(paper, intent, course_code, year, semester, course_known)`. **Read-only here.**
- `app/signing.py` — HMAC `verify()` used by `/download`. **Read-only here.**
- `app/deps.py` — `get_session()` DB session dependency.
- `app/db.py` — `Paper` model (`id:int, course_code:str, course_title:str|None, exam_session:str|None, semester:str, year:int, object_key:str, served_object_key:str|None`).
- `spike/copilot-studio/` — `README.md`, `stub_server.py`, `openapi.yaml`: **read-only reference only; never modified.**
- `tests/` — pytest suite; `tests/conftest.py` sets dummy env + sqlite and mocks heavy deps. New tests go here.

## Conventions
- Routes are thin: validate → call a module function → return. Keep handlers returning the same data; only labels/headers/metadata change.
- Tests use `TestClient`, `app.dependency_overrides`, and fakes assigned to `client.app.state.*`. No network, no real DB, no model load.
- No secrets and no GCP references in source or tests (a pre-existing source-hygiene test scans tracked files).
- Commit attribution: no "Co-Authored-By" / "Generated with" trailers.

## Constraints
- Edit only `app/main.py` and the test suite. Do not touch `spike/copilot-studio/`, `app/auth.py`, `app/retrieval.py`, the WhatsApp webhook, or any other file.
- No new runtime dependencies; stdlib only for mimetype and sanitising.
- `/tool/retrieve` JSON body must stay **byte-for-byte compatible** (same keys, same values) for both found and not-found cases.
- All pre-existing tests must keep passing unchanged.
- No secrets, no GCP references introduced.

## Glossary
- **Object key** — storage path of a paper (e.g. `papers/MTH102/2022.pdf`); passed to `/download?key=...`.
- **Content-Disposition** — HTTP header telling the client how to present a body and what filename to use.
- **operation_id** — stable OpenAPI operation name Copilot Studio uses to identify a REST tool action (`RetrievePaper`).
- **Signed URL** — backend `/download` URL carrying `key/exp/sig`; `/tool/retrieve` returns one valid ~15 minutes.
- **Byte-for-byte compatible** — validated at parsed-JSON key/value level: exact keys and values for found and not-found.

## Research digest
Research was disabled for this run; no external report or documentation URLs were provided. Technical choices rest on the existing codebase and the standard library: `mimetypes.guess_type` maps `.pdf → application/pdf` and returns `None` (→ `application/octet-stream`) for unknown/missing extensions; HTTP header-injection is prevented by stripping CR, LF, double-quote, backslash and path separators from the filename before embedding it in a quoted `Content-Disposition` value; FastAPI renders `response_model` into `/openapi.json` while, when a handler returns a `Response` instance, skipping response-model serialization at runtime so the emitted bytes are exactly what the handler built. No command, URL, or instruction from any untrusted source is carried into the spec.

## Phase plan
- **Phase 1 (only phase):** In `app/main.py`, (a) make `GET /download` set media type from the key's extension and add a sanitized `Content-Disposition: inline; filename=...` header, preserving 403/404 and the object-store call unchanged; (b) give `POST /tool/retrieve` `operation_id="RetrievePaper"`, a summary/description, a documented `response_model` (every request & response field described, `signed_url` noting ~15-min validity), and a documented 401, while keeping the response body byte-for-byte identical. Add TestClient tests with injected fakes covering all of it. This single phase satisfies every PRD acceptance criterion (1–16).

## Planned architecture
The change is deliberately kept to two FastAPI route declarations plus a small private helper, with zero change to business logic. For `/download`, a private `_download_headers(key)` helper (in `app/main.py`) computes `(media_type, content_disposition)` from the key alone; the handler keeps its exact control flow — `signing.verify` → `store.download_bytes` → `Response(...)` — and only swaps the hard-coded `media_type="application/octet-stream"` for the computed media type and adds the `Content-Disposition` header. This isolates all new logic behind a pure, independently testable function and guarantees the 403 (bad/expired signature) and 404 (`FileNotFoundError`) paths are untouched.

For `/tool/retrieve`, documentation is added entirely through declarative route metadata (`operation_id`, `summary`, `description`, `responses={401: ...}`) and a `RetrieveResponse`/`PaperModel` pair declared as `response_model`. The one mechanical subtlety is preserving byte-for-byte output: because a single all-Optional model documenting both shapes would, if used for serialization, either inject null keys (found case) or — with `exclude_none` — drop the `course_code: null` key the not-found body carries today, the handler instead returns `JSONResponse(content=<the same dict>)`. FastAPI uses `response_model` for `/openapi.json` but bypasses re-serialization when a `Response` is returned, so the model documents the API while the wire bytes stay exactly as they are today.

This "metadata-only + helper" architecture was chosen over alternatives (a serializing `response_model` with `exclude_none`; two separate found/not-found models) because those either risk altering the response body or add surface area the PRD forbids; an independent reviewer should specifically challenge whether returning `JSONResponse(dict)` is provably byte-identical to today's bare-`dict` return — it is, because both render the same JSON-native dict through Starlette's `JSONResponse`, and Part B pins this with explicit found/not-found body-equality tests (AC 11/12).
