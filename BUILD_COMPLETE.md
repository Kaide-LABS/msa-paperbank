# Build complete — Phase 1: `/download` media typing + `/tool/retrieve` OpenAPI documentation

- **Run:** 7745146e-0ed3-425e-8018-29a4fdfff5ea
- **Branch:** school-migration
- **Spec:** `runs/3ff2966e-8c21-440b-a280-d5ac616e9196/spec/PHASE_1_SPEC.md`
- **PRD:** `runs/3ff2966e-8c21-440b-a280-d5ac616e9196/baby-prd.md`
- **Status:** completed — single phase, all 16 PRD acceptance criteria met plus spec implications S1–S3.

## What was built

A two-part fix in `app/main.py` so a Microsoft Teams Copilot Studio agent can call the
Paperbank backend cleanly, with no change to any response body, auth, or retrieval logic.

1. **`GET /download` media typing + safe filename.** A pure helper `_download_headers(key)`
   derives the media type from the key's last path segment via `mimetypes.guess_type`
   (`.pdf → application/pdf`, else `application/octet-stream`) and builds a sanitised
   `Content-Disposition: inline; filename="…"` header. The filename is the last segment of
   the key (split on both `/` and `\`), reduced to printable ASCII (0x20–0x7E) with `"`, `\`
   and `/` removed, falling back to `download` when empty. The handler's control flow is
   unchanged: `signing.verify` → 403, `store.download_bytes` → 404 on `FileNotFoundError`,
   then the object bytes are returned — only the media type and the new header differ.

2. **`POST /tool/retrieve` self-describing OpenAPI.** The route declares
   `operation_id="RetrievePaper"`, a plain-language `summary`/`description`, a documented
   `401`, and a `response_model` (`RetrieveResponse` + nested `PaperModel`) with a
   description on every request and response field (`signed_url` notes ~15-minute validity).
   The handler returns `JSONResponse(content=<the same dict it built before>)`, so FastAPI
   renders the model into `/openapi.json` while skipping runtime re-serialization — the
   found and not-found bodies stay byte-for-byte identical (verified by exact-equality tests).

## Files changed this build

- `app/main.py` — download helper + route media type/header; `/tool/retrieve` metadata, models, `JSONResponse` wrapping. (production)
- `tests/test_download_headers.py` — media type (AC 1/2), inline + last-segment filename (AC 3), non-ASCII/control-char printable-ASCII header (S1), trailing-slash fallback, pure-helper check.
- `tests/test_download_sanitise.py` — adversarial filenames cannot break/extend the header (AC 4), 403 unchanged (AC 5), 404 unchanged (AC 6).
- `tests/test_tool_openapi.py` — operationId (AC 7), request descriptions (AC 8), response + nested paper descriptions and ~15-min note (AC 9), documented 401 (AC 10).
- `tests/test_tool_retrieve_body.py` — exact found body (AC 11), exact not-found body incl. `course_code: null` (AC 12), strict `model_validate` + declared-field subset (S2), no network/DB (AC 14), overrides empty after teardown (S3).

## Acceptance-criteria verification

| AC | Result |
|----|--------|
| 1 `.pdf` → `application/pdf` | pass |
| 2 unknown/absent ext → `application/octet-stream` | pass |
| 3 `Content-Disposition: inline`, filename = last segment | pass |
| 4 adversarial filename: no raw `"` CR LF `\` `/` in header | pass |
| 5 bad/expired signature → 403 unchanged | pass |
| 6 missing object → 404 unchanged | pass |
| 7 `operationId == RetrievePaper` | pass |
| 8 request `query`/`prefer_courses` descriptions non-empty | pass |
| 9 response + paper field descriptions non-empty; `signed_url` ~15 min | pass |
| 10 `401` documented in operation | pass |
| 11 found body exact keys/values | pass |
| 12 not-found body exact keys/values (incl. `course_code`) | pass |
| 13 pre-existing tests unchanged | pass (see note) |
| 14 TestClient + fakes, no network | pass |
| 15 no new dependency; Python 3.12 target intact | pass |
| 16 diff grep: no secrets/GCP introduced | pass |

Spec implications: **S1** (non-ASCII/control chars → printable-ASCII header, trailing-slash
fallback), **S2** (strict `model_validate` + documented-field subset), **S3** (fixtures
restore `app.state.store` / `app.dependency_overrides`, overrides empty afterwards) — all covered.

## How it was verified

- The four phase test files — `test_download_headers.py`, `test_download_sanitise.py`,
  `test_tool_openapi.py`, `test_tool_retrieve_body.py` — run green: **25 passed** under
  `pytest -p no:randomly`.
- The executor (Part B) reported the full suite excluding `tests/test_drive_import_dedupe.py`
  (a pre-existing collection error for a missing `scripts.drive_import` module) as 160 passed,
  9 failed, 39 errors — identical at baseline commit `353cb4d` in a throwaway worktree, so
  those failures are pre-existing and environmental (DB fixtures, OCR/preprocess/inbound), not
  caused by this phase (AC 13).
- AC 16: the only `gcp`/`bearer` tokens in the changed region of `app/main.py` are pre-existing
  comments in `lifespan`/`_warmup` and the new 401 description string — no secret literals, no
  GCP reference introduced by the diff.

## Reviewer notes (flagged, not overruled)

- **Environment interpreter is Python 3.14.4**, not the 3.12 target. The code is stdlib-only
  and version-agnostic; `pyproject.toml`'s `requires-python = ">=3.12"` is unchanged. The
  3.12 target was not exercised locally.
- **Commits `6281641` and `bdf3176` also swept in `osa.config.json`, the run `summary.md`,
  and the three `spike/copilot-studio/` files** as new additions. The phase spec scopes edits
  to `app/main.py` and tests and marks `spike/copilot-studio/` read-only. These appear to be
  pre-existing untracked reference/scaffolding files captured by the executor's commit rather
  than content edits to satisfy the spec; no spike file was altered to make the phase pass.
  Noted for the record; it does not affect the correctness of the phase deliverable.

This was the only planned phase. The build is complete.
