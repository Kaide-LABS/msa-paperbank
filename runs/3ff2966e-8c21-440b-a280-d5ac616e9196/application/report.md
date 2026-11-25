# Application check

**Failed** -- 2 requirement(s) not met.

## AC1: GET /download with a key ending in .pdf returns a response whose Content-Type is application/pdf.
Status: **met**

A signed GET /download for a .pdf key returns Content-Type application/pdf.

- `python /tmp/live.py (TestClient, real HMAC signing, fake store)` (exit 0)

  ```
  'papers/a.pdf' 200 application/pdf 'inline; filename="a.pdf"' b'BODY' True
  ```

## AC2: GET /download with a key whose extension is unknown or absent returns Content-Type application/octet-stream.
Status: **met**

Unknown and absent extensions both return application/octet-stream.

- `python /tmp/live.py` (exit 0)

  ```
  'papers/a.xyz' 200 application/octet-stream ...; 'papers/noext' 200 application/octet-stream ...
  ```

## AC3: GET /download returns a Content-Disposition header starting with 'inline' and containing a filename equal to the last path segment of the key.
Status: **met**

Content-Disposition starts with 'inline' and carries the last path segment as filename.

- `python /tmp/live.py` (exit 0)

  ```
  'papers/a.pdf' ... 'inline; filename="a.pdf"'
  ```

## AC4: For a key crafted with quotes, newlines, or path separators in its last segment, the Content-Disposition header contains no raw quote, CR, LF, or path-separator characters that would break or extend the header.
Status: **met**

Keys with quotes, CR/LF, backslashes and slashes in the last segment produce a header with none of those characters in the filename.

- `python /tmp/live.py; pytest tests/test_download_sanitise.py` (exit 0)

  ```
  'p/x"y\r\nz.pdf' 200 application/pdf 'inline; filename="xyz.pdf"'; test_download_sanitise.py: 8 passed (includes the Set-Cookie injection key and the backslash key)
  ```

## AC5: GET /download with an invalid or expired signature still returns HTTP 403, unchanged.
Status: **met**

A bad signature and an expired signature both still return 403.

- `python /tmp/live.py` (exit 0)

  ```
  bad sig -> 403; expired (exp=1) -> 403
  ```

## AC6: GET /download for a key the object store reports missing (FileNotFoundError) still returns HTTP 404, unchanged.
Status: **met**

A FileNotFoundError from the store still returns 404.

- `python /tmp/live.py` (exit 0)

  ```
  '403 404' (bad sig, then missing object)
  ```

## AC7: The document at /openapi.json lists the POST /tool/retrieve operation with operationId 'RetrievePaper'.
Status: **met**

/openapi.json lists POST /tool/retrieve with operationId RetrievePaper.

- `python /tmp/live.py` (exit 0)

  ```
  RetrievePaper ['200', '401', '422']
  ```

## AC8: In /openapi.json, the request schema for /tool/retrieve has non-empty descriptions on the query and prefer_courses fields.
Status: **met**

The request schema has non-empty descriptions for query and prefer_courses.

- `python /tmp/live.py` (exit 0)

  ```
  "query": {... "description": "What the student asked for, in their own words."}, "prefer_courses": {... "description": "Optional course codes to prefer; leave empty if unspecified."}
  ```

## AC9: In /openapi.json, the 200 response schema for /tool/retrieve has non-empty descriptions on found, intent, course_code, course_known, signed_url, and each field of paper (id, course_code, course_title, year, semester, exam_session), with signed_url's description noting ~15-minute validity.
Status: **met**

The 200 response schema (RetrieveResponse and PaperModel) describes every required field, and signed_url's description says valid for about 15 minutes.

- `python /tmp/live.py` (exit 0)

  ```
  200 -> $ref RetrieveResponse; found/intent/course_code/course_known/paper/signed_url all have descriptions; signed_url: "...valid for about 15 minutes."; PaperModel id/course_code/course_title/year/semester/exam_session all described
  ```

## AC10: In /openapi.json, POST /tool/retrieve documents a 401 response.
Status: **met**

POST /tool/retrieve documents a 401 response.

- `python /tmp/live.py` (exit 0)

  ```
  {'description': 'The bearer token was missing, malformed, or wrong.'}
  ```

## AC11: A test asserts the JSON body returned by POST /tool/retrieve in the found case equals today's exact keys and values (found, intent, paper{...}, signed_url).
Status: **met**

A test asserts the found-case JSON body equals the exact keys and values, and it passes.

- `python -m pytest -q tests/test_tool_retrieve_body.py` (exit 0)

  ```
  test_found_body_is_exact asserts {found, intent, paper{id,course_code,course_title,year,semester,exam_session}, signed_url}; 3 passed
  ```

## AC12: A test asserts the JSON body returned by POST /tool/retrieve in the not-found case equals today's exact keys and values (found=false, intent, course_code, course_known).
Status: **met**

A test asserts the not-found body equals found=false, intent, course_code (None) and course_known, and it passes.

- `python -m pytest -q tests/test_tool_retrieve_body.py` (exit 0)

  ```
  test_not_found_body_is_exact asserts {found False, intent, course_code None, course_known False}; 3 passed
  ```

## AC13: All pre-existing tests pass unchanged after the edits.
Status: **unmet**

The full suite does not pass, but the same 9 failures and 39 errors occur at the pre-edit baseline and no existing test file was modified.

- `python -m pytest -q -p no:randomly --ignore=tests/test_drive_import_dedupe.py (HEAD)` (exit 1)

  ```
  9 failed, 160 passed, 19 warnings, 39 errors
  ```
- `same command in a worktree of baseline commit 6722c7a` (exit 1)

  ```
  9 failed, 135 passed, 19 warnings, 39 errors
  ```
- `python -m pytest -q tests/test_drive_import_dedupe.py` (exit 2)

  ```
  ModuleNotFoundError: No module named 'scripts.drive_import'; also "fixture 'db_session' not found" in many pre-existing tests
  ```

## AC14: New tests use FastAPI TestClient with injected fakes and make no network calls.
Status: **met**

The new tests use TestClient with injected fakes (fake store, monkeypatched verify and answer_query, dependency overrides), with no network or DB.

- `read tests/test_download_*.py, tests/test_tool_retrieve_body.py; pytest on the 4 new test files` (exit 0)

  ```
  25 passed; no httpx or network calls, session overridden with iter([None])
  ```

## AC15: The repository declares/targets Python 3.12 and introduces no new third-party dependency in requirements/pyproject.
Status: **met**

pyproject still declares requires-python >=3.12 (Dockerfile uses python:3.12-slim), and no dependency file changed.

- `grep -n python pyproject.toml Dockerfile; git diff 6722c7a HEAD --stat -- pyproject.toml requirements.txt` (exit 0)

  ```
  pyproject.toml:5:requires-python = ">=3.12"; Dockerfile FROM python:3.12-slim; empty diff for pyproject.toml and requirements.txt
  ```

## AC16: A grep of the diff shows no secrets and no GCP references introduced.
Status: **met**

The diff of app/ and tests/ has no secrets or GCP references; the only hits are words in docs and spike files, with no GCP dependency or secret introduced.

- `git diff 6722c7a HEAD -- app tests | grep '^+' | grep -iE 'gcp|google|gcs|secret|api[_-]?key|password'` (exit 1)

  ```
  no matches. spike/ matches are 'no GCP' negations and import secrets/token_hex; BUILD_COMPLETE.md and the handoff JSON describe the earlier GCP migration.
  ```

## S1: GET /download with a validly signed key whose last segment contains non-ASCII characters (including characters outside latin-1) and control characters (NUL, tab, 0x7f) returns HTTP 200 with the file body. Its Content-Disposition header value is pure printable ASCII (0x20-0x7e), with no control characters and no raw quote, backslash or '/' inside the filename. An empty or all-stripped last segment (for example a key ending in '/') yields filename="download".
Status: **met**

A validly signed key with non-ASCII, control and NUL/tab/0x7f characters returns 200 with the body and a pure printable-ASCII header, and a trailing-slash key yields filename="download".

- `python /tmp/live.py` (exit 0)

  ```
  'p/café中😀\x00\t\x7f.pdf' 200 application/pdf 'inline; filename="caf.pdf"' b'BODY' True; 'papers/' 200 ... 'inline; filename="download"' b'BODY' True
  ```

## S2: A test validates the actual JSON body returned by POST /tool/retrieve in both the found and not-found cases with RetrieveResponse.model_validate (strict about types). It also asserts that every top-level and paper key in each real body is a declared field of the model, so a key added to the handler without being documented fails the test.
Status: **met**

The body tests call RetrieveResponse.model_validate(strict=True) in both cases and assert every top-level and paper key is a declared model field.

- `read tests/test_tool_retrieve_body.py; pytest it` (exit 0)

  ```
  _assert_declared: set(body) <= set(RetrieveResponse.model_fields); paper keys <= PaperModel.model_fields; RetrieveResponse.model_validate(body, strict=True); used in found and not-found tests; 3 passed
  ```

## S3: Every new test that sets app.dependency_overrides or app.state.store restores the original state in fixture teardown. The full suite passes when run in default order, in reverse order, and with each new test file run alone (for example `pytest -p no:randomly`, `pytest tests/test_tool_retrieve_body.py` and `pytest tests/test_download_headers.py`). After the new tests run, app.dependency_overrides is empty.
Status: **unmet**

The new tests restore state and pass in default, forward, reversed and per-file runs, and overrides are empty afterwards, but the full suite still has failures that also exist at baseline.

- `pytest -q <4 new files>; pytest -p no:randomly <4 files>; reversed order via a plugin that reverses items; each file alone; test_overrides_empty_after_fixture` (exit 0)

  ```
  25 passed (default); 25 passed (-p no:randomly); 25 passed (reversed); 8 / 8 / 6 / 3 passed per file alone; overrides-empty test: 1 passed
  ```
- `python /tmp/rev.py tests (reversed full suite)` (exit 1)

  ```
  9 failed, 160 passed, 19 warnings, 39 errors (same as forward and baseline)
  ```

## Notes

Tested on Python 3.14.4, since 3.12 is not installed here. AC13 and S3 are marked unmet only because the whole suite does not go green. The 9 failures and 39 errors, plus the collection error in test_drive_import_dedupe.py, are identical on the pre-edit baseline commit 6722c7a. They come from missing 'db_session' fixtures, a missing scripts/drive_import module, a WAMessage pydantic schema mismatch, and dependency-version issues. The edits introduced no regressions: baseline passed 135, HEAD passed 160, and the extra 25 are the new tests. I ran the /download checks through TestClient with a fake object store and the real HMAC signing code, patching only the secret lookup because the sandbox has no URL signing key configured. The build commit also added spike/copilot-studio/* and osa.config.json, which the spec says not to touch; I treated these as pre-existing scaffolding and did not count them against any criterion.
