# Handoff from phase 1

Outcome: completed.

## Turns
- turn 0 executor/opencode-cli: completed
- turn 1 executor/opencode-cli: completed, continuity CONTINUED
- turn 2 reviewer/claude-code: completed, continuity CONTINUED

## Work done
- executor/opencode-cli: Part A implemented. app/main.py: added mimetypes import, JSONResponse and Field imports, private _download_headers(key) helper (last path segment split on / and backslash; keeps only printable ASCII 0x20-0x7e minus double quote, backslash and slash; empty result falls back to 'download'; media type from mimetypes.guess_type on the sanitised name, default application/octet-stream; header is inline; filename="..."). download() keeps verify/download_bytes/403/404 flow and only the final Response changed. Added PaperModel and RetrieveResponse models, Field descriptions on ToolRetrieveRequest, route metadata on POST /tool/retrieve (operation_id RetrievePaper, summary, description, response_model, 401 response), handler now returns JSONResponse with the same two dicts. New tests tests/test_download_headers.py (pdf type, unknown/absent extension, inline filename, no-slash key, non-ASCII/control chars give printable ASCII header, trailing slash gives 'download', helper purity; fixture restores app.state.store) and tests/test_tool_openapi.py (operationId, summary, description, request field descriptions). The 10 new tests pass. Full suite excluding tests/test_drive_import_dedupe.py: 145 passed, 9 failed, 39 errors; failures are in test_inbound, test_ocr_schema, test_page_boundary and test_preprocess, and errors are DB-fixture setup errors in the local environment, none touching the changed code. test_drive_import_dedupe.py fails collection (no module scripts.drive_import). No baseline run before the change was made to confirm these pre-existing failures. Python 3.14 is the local interpreter.
- executor/opencode-cli: Part B. Read the spec, PRD, context and Part A output (app/main.py, tests/test_download_headers.py, tests/test_tool_openapi.py); Part A production code needed no change. Added tests/test_download_sanitise.py (6 adversarial keys with quote, CR/LF, backslash, slash, header-injection attempt: no raw quote/CR/LF/backslash/slash in the filename and no injected header; verify False gives 403; FileNotFoundError gives 404). Added tests/test_tool_retrieve_body.py (found and not-found exact JSON bodies using dependency_overrides for require_tool_token and get_session, a fake store and a monkeypatched retrieval.answer_query; each body also checked with RetrieveResponse.model_validate(strict=True) and key subset of declared model fields; fixture restores dependency_overrides and app.state.store; a test asserts overrides are empty afterwards). Extended tests/test_tool_openapi.py with response field descriptions, nested paper field descriptions, signed_url mentioning 15 minutes, and a documented 401. The 25 tests across the four phase test files pass. Full suite excluding tests/test_drive_import_dedupe.py (collection error, no module scripts.drive_import): 160 passed, 9 failed, 39 errors, identical in default order and with -p no:randomly; a run at baseline commit 353cb4d in a temporary worktree gave the same 9 failed and 39 errors (135 passed), so those failures are pre-existing and unrelated. tests/test_tool_retrieve_body.py passes when run alone. No dependency files changed; diff grep for gcp/secret/key terms in app and tests returned nothing. Committed as bdf3176. Python 3.14 is the local interpreter; Python 3.12 target not exercised locally. Reverse-order run was not performed.
- reviewer/claude-code: Reviewed Phase 1 against the spec, PRD, context and the executor diff. Read both executors' outputs: app/main.py (download helper + route media type/Content-Disposition; /tool/retrieve operation_id, summary/description, RetrieveResponse/PaperModel response_model, documented 401, JSONResponse wrapping) and all four phase test files including Part B's test_download_sanitise.py, test_tool_retrieve_body.py and the extended test_tool_openapi.py. Ran the four phase test files under pytest -p no:randomly: 25 passed. Verified each PRD acceptance criterion 1-16 and spec implications S1-S3 map to a passing test. Confirmed AC16: the only gcp/bearer tokens in the changed region of app/main.py are pre-existing lifespan/warmup comments and the new 401 description string, no secret literal and no GCP reference introduced by the diff. Confirmed the three prior artifacts_written hashes match the handoff exactly. Wrote the build completion record to BUILD_COMPLETE.md and committed it. Flags (not overruled): local interpreter is Python 3.14.4 not the 3.12 target (code is stdlib-only and version-agnostic, pyproject requires-python >=3.12 unchanged); executor commits 6281641/bdf3176 also swept in osa.config.json, the run summary.md and three spike/copilot-studio files as new additions, which the spec scopes out, but they appear to be pre-existing untracked reference/scaffolding files captured by the commit rather than edits to pass the phase, and no spike file content was altered.

## Files changed
- .osa/runs/7745146e-0ed3-425e-8018-29a4fdfff5ea/handoff/1/002-reviewer-claude-code.json
- BUILD_COMPLETE.md
- app/main.py
- osa.config.json
- runs/3ff2966e-8c21-440b-a280-d5ac616e9196/summary.md
- spike/copilot-studio/README.md
- spike/copilot-studio/openapi.yaml
- spike/copilot-studio/stub_server.py
- tests/test_download_headers.py
- tests/test_download_sanitise.py
- tests/test_tool_openapi.py
- tests/test_tool_retrieve_body.py

## Commits
- Set media type and inline filename on /download; document /tool/retrieve in OpenAPI
- chore: capture a dispatched turn's uncommitted working-tree changes
- Add download sanitising, retrieve body and OpenAPI description tests
- Add Phase 1 build completion record
- Add reviewer handoff record for phase 1

## Next steps recorded by the agents
- Part B: add tests/test_download_sanitise.py (adversarial filename, 403, 404), tests/test_tool_retrieve_body.py (found/not-found exact bodies, plus RetrieveResponse.model_validate and declared-keys check per S2), extend tests/test_tool_openapi.py (response field descriptions, signed_url ~15 minutes, 401).
- Ensure new tests restore app.dependency_overrides and app.state.store (S3).
- Confirm the failing/erroring pre-existing tests also fail at the prior commit.
- Reviewer: confirm the 9 failures and 39 errors (test_inbound, test_ocr_schema, test_page_boundary, test_preprocess, DB-fixture errors) are environmental and also occur at baseline.
- Optionally run the suite in reverse order and under Python 3.12.
- Optionally exercise the suite under Python 3.12 to confirm the stated target before cutover.
- Optionally confirm osa.config.json and the spike/copilot-studio files swept into the executor commits were intended inclusions and not scope creep.
