# Baby PRD -- FastAPI download Content-Disposition media typing and OpenAPI tool documentation for Copilot Studio import

## TL;DR
- The Paperbank past-paper bot is getting a small two-part fix so a Microsoft Teams agent can use it cleanly.
- First, when the bot hands out a file, it will now say the file is a PDF and give it a proper .pdf name, instead of an unnamed generic blob Teams might open badly.
- Second, the bot's search endpoint will describe itself clearly (name, what it does, every field) so Teams' Copilot Studio can import it as a tool without hand-editing.
- The actual answers the bot returns stay exactly the same, byte-for-byte; only labels, file types, and documentation change.
- You'll know it worked when new automated tests pass: right PDF type and safe filename, unchanged error codes, and the search tool shows the correct name and field descriptions.

## Scope
narrow

## Baby PRD

### Problem
A Copilot Studio agent in Microsoft Teams calls the Paperbank FastAPI backend over public HTTPS, but a spike kit exposed two defects: GET /download returns every object as application/octet-stream with no filename (so Teams may mishandle it or save a file with no .pdf extension), and POST /tool/retrieve lacks the OpenAPI metadata (operation id, descriptions, response model, documented 401) needed to import it cleanly as a REST tool.

### Users / who it's for
The engineer maintaining the Paperbank backend, and indirectly the PAU students who receive past-paper download links through the Teams Copilot Studio agent.

### In scope
- In app/main.py, make GET /download set the media type from the object key's file extension (application/pdf for .pdf keys; safe fallback application/octet-stream for unknown/missing extensions).
- In app/main.py, make GET /download add a Content-Disposition: inline header with a filename taken from the last path segment of the key.
- Sanitise the Content-Disposition filename so it cannot inject header characters: strip/neutralise quotes, newlines, and path separators.
- In app/main.py, give POST /tool/retrieve an operation_id of RetrievePaper.
- Add a plain-language summary and description to POST /tool/retrieve stating what it does and when an agent should call it.
- Declare a response model for POST /tool/retrieve with a description on every field: request fields (query, prefer_courses) and response fields (found, intent, course_code, course_known, paper and each of its fields, signed_url noted as valid ~15 minutes).
- Document the 401 response for POST /tool/retrieve so it appears in /openapi.json.
- Add new tests using FastAPI TestClient with injected fakes (no network) covering: the download media type and filename, the filename sanitising, the unchanged 403 and 404 download paths, the OpenAPI operation id and field descriptions, and that both the found and not-found response bodies are byte-for-byte unchanged.

### Out of scope
- Any change to signature verification, expiry/403 handling, the 404-for-missing-object behaviour, or the object-store download call in GET /download.
- Any change to the bearer-token auth dependency in app/auth.py.
- Any change to the retrieval logic (retrieval.answer_query) or the shape/values of the /tool/retrieve JSON response for found or not-found cases.
- Any change to the WhatsApp webhook path and its handlers.
- Any modification to the spike/copilot-studio/ folder (README.md, stub_server.py, openapi.yaml are read-only references).
- Adding new runtime dependencies, secrets, or GCP references.
- The Copilot Studio agent itself, Teams push notifications, image/photo input to /tool/retrieve, and any Azure hosting work.
- Changes to files other than app/main.py and the test suite.

### Acceptance criteria
1. GET /download with a key ending in .pdf returns a response whose Content-Type is application/pdf.
2. GET /download with a key whose extension is unknown or absent returns Content-Type application/octet-stream.
3. GET /download returns a Content-Disposition header starting with 'inline' and containing a filename equal to the last path segment of the key.
4. For a key crafted with quotes, newlines, or path separators in its last segment, the Content-Disposition header contains no raw quote, CR, LF, or path-separator characters that would break or extend the header.
5. GET /download with an invalid or expired signature still returns HTTP 403, unchanged.
6. GET /download for a key the object store reports missing (FileNotFoundError) still returns HTTP 404, unchanged.
7. The document at /openapi.json lists the POST /tool/retrieve operation with operationId 'RetrievePaper'.
8. In /openapi.json, the request schema for /tool/retrieve has non-empty descriptions on the query and prefer_courses fields.
9. In /openapi.json, the 200 response schema for /tool/retrieve has non-empty descriptions on found, intent, course_code, course_known, signed_url, and each field of paper (id, course_code, course_title, year, semester, exam_session), with signed_url's description noting ~15-minute validity.
10. In /openapi.json, POST /tool/retrieve documents a 401 response.
11. A test asserts the JSON body returned by POST /tool/retrieve in the found case equals today's exact keys and values (found, intent, paper{...}, signed_url).
12. A test asserts the JSON body returned by POST /tool/retrieve in the not-found case equals today's exact keys and values (found=false, intent, course_code, course_known).
13. All pre-existing tests pass unchanged after the edits.
14. New tests use FastAPI TestClient with injected fakes and make no network calls.
15. The repository declares/targets Python 3.12 and introduces no new third-party dependency in requirements/pyproject.
16. A grep of the diff shows no secrets and no GCP references introduced.

### Constraints
- Edit only app/main.py and the tests; touch nothing else and do not modify spike/copilot-studio/.
- No new dependencies (standard library only for mimetype lookup and sanitising).
- No secrets and no GCP references anywhere in the changes.
- Target Python 3.12.
- Existing tests must keep passing unchanged.
- New tests must use FastAPI TestClient with injected fakes and make no network calls.
- The /tool/retrieve JSON response must stay byte-for-byte compatible (same keys, same values) for both found and not-found cases.
- Stack: FastAPI, Pydantic, Starlette, SQLAlchemy (existing).

### Research plan
- Topic: FastAPI download Content-Disposition media typing and OpenAPI tool documentation for Copilot Studio import
- Time range: last 3 years
- Items:
  1. content-disposition-inline-filename | Content-Disposition inline with a safe filename | How to set Content-Disposition: inline; filename=... safely in a FastAPI/Starlette Response, including RFC 6266 quoting and filename* for non-ASCII, and what characters must be stripped to prevent header injection. | modules: general-web, stackoverflow
  2. mimetype-from-extension | Deriving media type from a key's file extension | How Python's mimetypes.guess_type maps extensions (notably .pdf -> application/pdf) and how to fall back to application/octet-stream for unknown/missing extensions without new dependencies. | modules: general-web, stackoverflow
  3. fastapi-response-model-field-descriptions | Response model and per-field descriptions in OpenAPI | How to declare a Pydantic response_model with Field(description=...) on nested models so every field's description surfaces in /openapi.json, without changing the runtime dict the endpoint returns. | modules: general-web, stackoverflow
  4. fastapi-operation-id-and-responses | operation_id, summary/description, and documented error responses | How to set operation_id='RetrievePaper' and document a 401 response via the responses= argument on a FastAPI route, and how these render in /openapi.json. | modules: general-web
  5. return-dict-while-declaring-model | Keeping a byte-for-byte dict body while declaring a response model | Whether declaring response_model (and response_model_exclude_none behaviour) alters the serialized JSON when the handler returns a plain dict, and how to guarantee the found/not-found bodies stay identical. | modules: general-web, github-debug
  6. copilot-studio-rest-tool-openapi | Copilot Studio REST tool OpenAPI expectations | What OpenAPI fields Copilot Studio uses when importing a REST tool (operationId, summary, descriptions, x-ms-summary) and whether the backend's FastAPI-generated OpenAPI 3.x satisfies import given the spike's Swagger 2.0 reference. | modules: general-web
  7. testclient-injected-fakes | TestClient with dependency_overrides and fake app.state | How to override get_session and require_tool_token and inject a fake object store on app.state via FastAPI TestClient so tests make no network calls while exercising /download and /tool/retrieve. | modules: general-web, stackoverflow
  8. header-injection-sanitisation | HTTP header value injection defences | Which characters (CR, LF, double quotes, backslash, path separators) must be removed or encoded from a filename before placing it in a response header, and canonical sanitising approaches. | modules: general-web, stackoverflow
- Official docs to read:
  - FastAPI
  - Starlette
  - Pydantic
  - Python standard library (mimetypes)
  - Python standard library (os.path / posixpath)
  - Microsoft Copilot Studio
  - OpenAPI Specification
  - Swagger 2.0
- Academic searches:
  - (none)
- Prior-art searches:
  - FastAPI download endpoint Content-Disposition inline filename sanitize
  - FastAPI response_model nested field description openapi operation_id
  - FastAPI TestClient dependency_overrides fake object store no network

## Assumptions
- [risky] The response model is declared purely for OpenAPI documentation; the handlers continue returning plain dicts and the model is configured (e.g. optional fields / exclude-none as needed) so the serialized JSON stays byte-for-byte identical for both the found and not-found cases.
- [risky] The 401 response is documented via FastAPI's responses= argument on the route with a description, matching the auth dependency's existing 401 behaviour, and no 401 response body schema is asserted beyond its presence.
- [safe] Media type is derived from the key's file extension using the Python standard library mimetypes module (no new dependency), with application/octet-stream as the fallback for unknown or missing extensions.
- [safe] The filename is extracted from the key's last path segment using posix-style splitting on '/', and sanitising strips or replaces CR, LF, double quotes, backslashes, and any residual path separators before embedding it in the Content-Disposition header.
- [safe] A single response model with all fields optional is used to document both the found and not-found shapes, rather than two separate models or a union.
- [safe] Content-Disposition uses the 'inline' disposition with a quoted filename parameter (RFC 6266 style); if non-ASCII handling is needed it is reduced to a safe ASCII filename rather than adding filename* encoding, since keys are expected to be ASCII.
- [safe] New tests inject a fake object store on app.state and override the get_session and require_tool_token dependencies via FastAPI's dependency_overrides to avoid any DB or network access.
- [safe] The links in the prompt and README (https://<tunnel-host>, https://<host>, etc.) are placeholders, not real URLs, and cannot be opened or verified.
- [safe] 'Byte-for-byte compatible' is validated at the parsed-JSON key/value level (exact keys and values for found and not-found) rather than literal byte comparison of whitespace, since FastAPI controls serialization and the dict contents are what the spec pins.
- [safe] The existing /download object-store call (request.app.state.store.download_bytes) and its return as a Response body are preserved; only the media_type and headers of the returned Response change.

## Recommended questions
- (none)

## Original request (authoritative)

The person's own words, unedited. Where anything above differs from this, this request wins.

> Small follow-up to the finished GCP-to-self-hosted migration of the Paperbank past-paper bot (FastAPI, branch school-migration). A Copilot Studio agent in Microsoft Teams will call our backend over public HTTPS, and a spike kit in spike/copilot-studio/ (read its README.md, stub_server.py and openapi.yaml; do not modify that folder) exposed two problems in the real app. Fix both in app/main.py and tests, and nothing else.
>
> 1. GET /download currently returns every object as application/octet-stream with no filename, so Teams may open it badly or save a file with no .pdf extension. Make it return the right media type for the object (application/pdf for .pdf keys, using the key's file extension, with a safe fallback of application/octet-stream) and a Content-Disposition: inline header with a filename taken from the last path segment of the key. The filename must be sanitised so it cannot inject header characters (quotes, newlines, path separators). Signature verification, expiry handling (403), the 404 for a missing object, and the object-store call stay exactly as they are.
>
> 2. POST /tool/retrieve must produce a clean OpenAPI document at /openapi.json so it can be imported into Copilot Studio as a REST tool. Give the route an operation_id of RetrievePaper, a plain-language summary and description (what it does, when an agent should call it), and a declared response model with a description on every field of the request (query, prefer_courses) and the response (found, intent, course_code, course_known, paper and its fields, signed_url, which is valid for about 15 minutes). Document the 401 response. The JSON the endpoint returns must stay byte-for-byte compatible with today's shape: same keys, same values, for both the found and not-found cases. Do not change auth (the bearer-token dependency in app/auth.py), retrieval logic, or the WhatsApp webhook path.
>
> Constraints: no new dependencies; no secrets or GCP references anywhere; project target is Python 3.12 and the existing tests must keep passing unchanged; new tests must use FastAPI TestClient with injected fakes and make no network calls, and must cover the media type and filename, the sanitising, the unchanged 403 and 404 paths, the OpenAPI operation id and field descriptions, and that the found and not-found response bodies are unchanged.
