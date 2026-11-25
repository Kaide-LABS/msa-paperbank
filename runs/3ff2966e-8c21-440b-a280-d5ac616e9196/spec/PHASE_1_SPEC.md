# Phase 1 — `/download` media typing + `/tool/retrieve` OpenAPI documentation

## Goal
Make `GET /download` label files correctly (PDF media type + safe `inline` filename) and make `POST /tool/retrieve` self-describing in `/openapi.json` (operation id, summary/description, fully-described response model, documented 401) — without changing any response body, auth, retrieval logic, or any file other than `app/main.py` and the tests.

## Scope
- Edit **only** `app/main.py` and add/extend tests under `tests/`.
- Do **not** modify `spike/copilot-studio/`, `app/auth.py`, `app/retrieval.py`, `app/signing.py`, the WhatsApp webhook, or any other file.
- No new dependencies; stdlib only (`mimetypes`, string ops). No secrets, no GCP references.
- Target Python 3.12. All pre-existing tests must still pass unchanged.

---

## Part A (first agent)

### Files
- `app/main.py` (edit)
- `tests/test_download_headers.py` (new)
- `tests/test_tool_openapi.py` (new)

### Interfaces and behaviour

**1. Download helper + route (`app/main.py`)**
- Add `import mimetypes` at module top (stdlib).
- Add a private pure helper:
  ```python
  def _download_headers(key: str) -> tuple[str, str]:
      """Return (media_type, content_disposition) for an object key.
      media_type from the key's extension (.pdf -> application/pdf), else
      application/octet-stream. filename is the key's last path segment,
      sanitised so it cannot inject header characters, embedded as
      inline; filename="...".
      """
  ```
  - `filename`: take the last path segment by splitting on both `/` and `\\`; e.g. `name = key.replace("\\", "/").rsplit("/", 1)[-1]`.
  - `media_type`: `mimetypes.guess_type(name)[0] or "application/octet-stream"`.
  - Sanitise `name`: remove every `"` (double quote), `\r` (CR), `\n` (LF), `\\` (backslash), and `/`; keep other characters. Reduce any non-ASCII to a safe ASCII form (e.g. drop or replace non-ASCII bytes). If the sanitised name is empty, use `"download"`.
  - Return `(media_type, f'inline; filename="{safe_name}"')`.
- In the `download(...)` handler, keep the existing flow **exactly** (`signing.verify` → `request.app.state.store.download_bytes(key)` → `FileNotFoundError` → 404 → 403 on bad sig). Change only the final return to:
  ```python
  media_type, cd = _download_headers(key)
  return Response(content=data, media_type=media_type,
                  headers={"Content-Disposition": cd})
  ```
  Do not alter the `signing.verify` 403 branch or the `FileNotFoundError` 404 branch or the `download_bytes` call.

**2. `/tool/retrieve` response model + metadata (`app/main.py`)**
- Add Pydantic models (Pydantic v2 `Field(description=...)`):
  ```python
  class PaperModel(BaseModel):
      id: int | None = Field(None, description="Internal paper identifier.")
      course_code: str | None = Field(None, description="PAU course code, e.g. MTH102.")
      course_title: str | None = Field(None, description="Human-readable course title.")
      year: int | None = Field(None, description="Academic year of the paper.")
      semester: str | None = Field(None, description="Semester, e.g. 'harmattan' or 'rain'.")
      exam_session: str | None = Field(None, description="Exam session, e.g. CA1, CA2, exam.")

  class RetrieveResponse(BaseModel):
      found: bool | None = Field(None, description="True when a matching paper was found.")
      intent: str | None = Field(None, description="Routed intent for the request.")
      course_code: str | None = Field(None, description="Course code parsed from the query (not-found case).")
      course_known: bool | None = Field(None, description="Whether the course code is in the catalog (not-found case).")
      paper: PaperModel | None = Field(None, description="The matched paper's metadata (found case).")
      signed_url: str | None = Field(None, description="Download link to the paper PDF, valid for about 15 minutes.")
  ```
  Also add `description=...` to `ToolRetrieveRequest.query` and `.prefer_courses` via `Field`:
  - `query`: "What the student asked for, in their own words."
  - `prefer_courses`: "Optional course codes to prefer; leave empty if unspecified."
- Change the route decorator to:
  ```python
  @app.post(
      "/tool/retrieve",
      operation_id="RetrievePaper",
      response_model=RetrieveResponse,
      summary="Find a past paper",
      description="Searches the past-paper collection for the paper that best "
                  "matches the student's request and returns its course, year and "
                  "semester plus a short-lived download link. Call it when a student "
                  "asks for a past paper or exam questions for a course. If nothing "
                  "matches, found is false.",
      responses={401: {"description": "The bearer token was missing, malformed, or wrong."}},
  )
  ```
- In the handler, build the **same two dicts as today** (do not change keys or values) and return them wrapped in `JSONResponse`:
  ```python
  from fastapi.responses import JSONResponse  # add to existing imports
  ...
  return JSONResponse(content={...})  # for both found and not-found dicts
  ```
  Keep `-> dict` off the signature if it conflicts; the handler now returns `JSONResponse`. Do **not** add `response_model_exclude_none`. Do not change the auth dependency, `get_session`, or the call to `retrieval.answer_query`.

### Tests (Part A)

`tests/test_download_headers.py` — build a `TestClient(app)`, set `client.app.state.store` to a fake with `download_bytes(key) -> b"%PDF-1.4..."`, and `monkeypatch.setattr("app.main.signing.verify", lambda *a, **k: True)`:
- `.pdf` key → response `Content-Type` is `application/pdf` (AC 1).
- key with unknown/absent extension (e.g. `papers/file.xyz`, `papers/noext`) → `Content-Type` is `application/octet-stream` (AC 2).
- `Content-Disposition` starts with `inline` and contains `filename="<last segment>"` equal to the key's last path segment (AC 3).

`tests/test_tool_openapi.py` — `client.get("/openapi.json").json()`:
- the `POST /tool/retrieve` operation has `operationId == "RetrievePaper"` (AC 7).
- request schema fields `query` and `prefer_courses` have non-empty `description` (AC 8).

### Acceptance criteria satisfied in Part A
AC 1, 2, 3, 7, 8 (and the groundwork making 4, 5, 6, 9, 10, 11, 12 verifiable in Part B).

---

## Part B (second agent)

### Files
- `tests/test_download_sanitise.py` (new)
- `tests/test_tool_retrieve_body.py` (new)
- `tests/test_tool_openapi.py` (extend — 401 + full field descriptions)

### Interfaces and behaviour
No new production code is expected; Part B proves the edge cases, error paths, body stability, and full OpenAPI surface produced by Part A. If any Part A test exposes a gap (e.g. an un-sanitised character, a missing field description, a 401 not rendered), Part B fixes it **in `app/main.py`** (helper or model/metadata only) and commits.

### Tests (Part B)

`tests/test_download_sanitise.py` (AC 4, 5, 6) — same fake store + `TestClient`:
- For keys whose last segment contains `"`, `\r`, `\n`, `\\`, and embedded `/`, assert the returned `Content-Disposition` header value contains **no** raw `"`, `\r`, `\n`, `\\`, or `/` that would break or extend the header. (Read `response.headers["content-disposition"]`.) (AC 4)
- `monkeypatch.setattr("app.main.signing.verify", lambda *a, **k: False)` → `GET /download?...` returns **403** unchanged (AC 5).
- `signing.verify` → True but fake store's `download_bytes` raises `FileNotFoundError` → **404** unchanged (AC 6).

`tests/test_tool_retrieve_body.py` (AC 11, 12, 14) — `TestClient`, with:
- `app.dependency_overrides[require_tool_token] = lambda: None`
- `app.dependency_overrides[get_session] = lambda: iter([None])` (or a generator yielding a dummy)
- `monkeypatch.setattr("app.main.retrieval.answer_query", ...)` returning a fixed `RetrievalResult`
- `client.app.state.store.signed_url = lambda key: "https://host/download?..."`
- **Found case:** monkeypatch returns a result with a `paper`; assert `response.json()` equals exactly `{"found": True, "intent": ..., "paper": {"id":..., "course_code":..., "course_title":..., "year":..., "semester":..., "exam_session":...}, "signed_url": ...}` — same keys/values the handler builds today (AC 11).
- **Not-found case:** result with `paper=None`; assert `response.json()` equals exactly `{"found": False, "intent": ..., "course_code": ..., "course_known": ...}` (including a `course_code` key even when its value is `None`) (AC 12).
- Both tests make no network/DB calls (AC 14).

`tests/test_tool_openapi.py` (extend) (AC 9, 10):
- 200 response schema for `/tool/retrieve` has non-empty `description` on `found`, `intent`, `course_code`, `course_known`, `signed_url`, and on each `paper` field (`id`, `course_code`, `course_title`, `year`, `semester`, `exam_session`); `signed_url`'s description mentions ~15-minute validity (AC 9).
- the operation documents a `401` response in `/openapi.json` (AC 10).

### Project-wide checks (run/verify, not new code)
- Full suite green: pre-existing tests unchanged + all new tests pass (AC 13).
- `pyproject.toml`/requirements unchanged re: dependencies; still targets Python 3.12 (AC 15).
- A grep of the diff shows no secrets and no GCP references introduced (AC 16).

### Acceptance criteria satisfied in Part B
AC 4, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16.

---

## Acceptance-criteria mapping (all → Phase 1)
| AC | Where | Concrete check |
|----|-------|----------------|
| 1 | A | `.pdf` key → `Content-Type: application/pdf` test |
| 2 | A | unknown/absent ext → `application/octet-stream` test |
| 3 | A | `Content-Disposition` starts `inline`, filename = last segment |
| 4 | B | adversarial filename → no raw `"`,CR,LF,`\`,`/` in header |
| 5 | B | `verify`→False → 403 unchanged |
| 6 | B | `download_bytes` raises `FileNotFoundError` → 404 unchanged |
| 7 | A | `/openapi.json` operationId == `RetrievePaper` |
| 8 | A | request `query`/`prefer_courses` descriptions non-empty |
| 9 | B | all response + nested paper field descriptions non-empty; `signed_url` ~15 min |
| 10 | B | `401` present in operation responses |
| 11 | B | found body equals exact keys/values |
| 12 | B | not-found body equals exact keys/values (incl. `course_code` key) |
| 13 | B | full pytest suite passes |
| 14 | A,B | tests use TestClient + fakes, no network |
| 15 | B | no new dependency; Python 3.12 target intact |
| 16 | B | diff grep: no secrets, no GCP references |

## Documentation sources
- none (research was disabled for this run; no documentation URLs were provided, so none are cited).

## Out of scope for this phase
- Any change to signature verification, expiry/403 handling, the 404-for-missing-object behaviour, or the object-store `download_bytes` call in `GET /download`.
- Any change to `app/auth.py` (`require_tool_token`), `app/retrieval.py` (`answer_query`), or the shape/values of the `/tool/retrieve` response for found/not-found.
- Any change to the WhatsApp webhook path and its handlers.
- Any modification to `spike/copilot-studio/` (read-only reference).
- New runtime dependencies, secrets, or GCP references.
- The Copilot Studio agent, Teams push notifications, image/photo input to `/tool/retrieve`, and Azure hosting.
- Changes to files other than `app/main.py` and the test suite.

## Spec assumptions

Gaps found while writing this spec were resolved as follows (nobody was asked):

- The `/tool/retrieve` handler is changed to return `fastapi.responses.JSONResponse(content=<the same dict it builds today>)` instead of a bare `dict`, while the route declares `response_model=RetrieveResponse`. Returning a `Response` instance makes FastAPI skip response-model serialization at runtime (so the body stays byte-for-byte identical), but still render the model into `/openapi.json`. This is the chosen mechanism to satisfy "declare a response model" + "byte-for-byte unchanged" together; `response_model_exclude_none` is NOT used (it would drop the `course_code: null` key that today's not-found body contains).
- The rendered bytes are identical because the handler's dict contains only JSON-native values (str/int/bool/None/nested dict), so `JSONResponse` and FastAPI's default dict-return path both emit the same `json.dumps(..., separators=(",",":"))` output.
- A single `RetrieveResponse` model with all fields Optional documents both the found and not-found shapes (per the PRD's safe assumption); a nested `PaperModel` documents the `paper` object.
- `semester` is documented as a string in the response model (the runtime `Paper.semester` is `'harmattan'|'rain'`), not an integer; where the read-only spike `openapi.yaml` shows `semester: integer` it is a reference artifact, not a requirement, and the real runtime value wins.
- Media type is derived via `mimetypes.guess_type(<last path segment>)[0] or "application/octet-stream"`; `mimetypes` is initialized at import with the standard table (`.pdf -> application/pdf`).
- The download filename is the last path segment computed by splitting the key on `/` (posix) and `\\` (backslash), then sanitized by removing/neutralising CR, LF, double-quote, backslash, and any residual `/`; if the result is empty it falls back to `"download"`. Non-ASCII is reduced to a safe ASCII filename (no `filename*` encoding).
- The `Content-Disposition` header is `inline; filename="<sanitized>"` (quoted, RFC 6266 inline disposition).
- `/download` tests monkeypatch `app.main.signing.verify` (True for success paths, False for the 403 path) so the header/media-type logic is exercised without depending on `settings.url_signing_key` being configured; the fake object store is injected on `client.app.state.store`.
- `/tool/retrieve` tests override `require_tool_token` and `get_session` via `app.dependency_overrides`, monkeypatch `app.main.retrieval.answer_query` to return a fixed `RetrievalResult`, and set `app.state.store.signed_url` to return a fixed string, so no DB/network is touched.
- New test files: Part A adds `tests/test_download_headers.py` and `tests/test_tool_openapi.py`; Part B adds `tests/test_download_sanitise.py` and `tests/test_tool_retrieve_body.py`. No README changes are made (the PRD limits edits to `app/main.py` and the tests).

## Implications

Second-order consequences found by an independent review of this spec. This section only adds to the spec; the locked PRD is unchanged.

### Additional acceptance criteria

S1. GET /download with a validly signed key whose last segment contains non-ASCII characters (including characters outside latin-1) and control characters (NUL, tab, 0x7f) returns HTTP 200 with the file body. Its Content-Disposition header value is pure printable ASCII (0x20-0x7e), with no control characters and no raw quote, backslash or '/' inside the filename. An empty or all-stripped last segment (for example a key ending in '/') yields filename="download". _(user-impact: The spec only strips CR, LF, quotes, backslash and '/'. Other control characters (NUL, tab, 0x7f) can still reach the header. Non-ASCII is only 'dropped or replaced', which is vague. Starlette encodes header values as latin-1, so a key with characters outside latin-1 (for example an emoji or a curly-quoted course title) could raise an encoding error and return a 500 instead of the file.)_
S2. A test validates the actual JSON body returned by POST /tool/retrieve in both the found and not-found cases with RetrieveResponse.model_validate (strict about types). It also asserts that every top-level and paper key in each real body is a declared field of the model, so a key added to the handler without being documented fails the test. _(maintenance: Returning JSONResponse bypasses FastAPI's response-model validation. The documented RetrieveResponse/PaperModel can drift from the real body: types such as id, year and semester, or renamed keys. Copilot Studio would then import a schema that lies. Nothing in the spec checks that the documented model matches what the handler emits.)_
S3. Every new test that sets app.dependency_overrides or app.state.store restores the original state in fixture teardown. The full suite passes when run in default order, in reverse order, and with each new test file run alone (for example `pytest -p no:randomly`, `pytest tests/test_tool_retrieve_body.py` and `pytest tests/test_download_headers.py`). After the new tests run, app.dependency_overrides is empty. _(maintenance: The new tests set app.dependency_overrides, app.state.store and monkeypatch signing/retrieval on the one shared global `app`. If the tests don't restore them, they leak into the pre-existing tests. That causes order-dependent failures or hides real auth and DB behaviour.)_

### Explicitly out of scope

- Out of scope: restricting the guessed media type to an allowlist, adding X-Content-Type-Options, or forcing attachment for non-PDF types. Object keys are assumed to be trusted, admin-ingested paper PDFs. Non-PDF extensions are served inline with whatever mimetypes.guess_type returns. _(security)_
- Out of scope: verifying that the generated /openapi.json imports into Copilot Studio without edits. This covers the OpenAPI 3.1 version, anyOf/null schemas, x-ms-summary, and conversion to Swagger 2.0. Acceptance is limited to the /openapi.json assertions in the acceptance criteria, and manual import testing is left to a later step. _(user-impact)_

### Noted, no action

- The '~15 minutes' wording in signed_url's description is static documentation. It is not derived from the configured TTL, and this change does not check that the two match. _(user-impact)_
- Compute the media type from the sanitised filename so the Content-Type and the filename extension always agree. The test for '.pdf -> application/pdf' guards against host-specific mimetypes tables. _(maintenance)_
- No additional error responses (422, 5xx) are documented beyond the 200 and 401. Their FastAPI defaults are left unchanged. _(user-impact)_
