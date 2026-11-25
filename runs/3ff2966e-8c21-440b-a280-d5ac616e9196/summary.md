# What OSA got done before it stopped

## In short
- The Paperbank past-paper bot is getting a small two-part fix so a Microsoft Teams agent can use it cleanly.
- First, when the bot hands out a file, it will now say the file is a PDF and give it a proper .pdf name, instead of an unnamed generic blob Teams might open badly.
- Second, the bot's search endpoint will describe itself clearly (name, what it does, every field) so Teams' Copilot Studio can import it as a tool without hand-editing.
- The actual answers the bot returns stay exactly the same, byte-for-byte; only labels, file types, and documentation change.
- You'll know it worked when new automated tests pass: right PDF type and safe filename, unchanged error codes, and the search tool shows the correct name and field descriptions.

## It did not finish
The finished project did not pass the final check against the requirements.

## Stage by stage

### Stage 1
#### What was built

The bot now hands out past papers as proper, clearly-labelled PDF files with sensible names, so Microsoft Teams opens them correctly instead of treating them as unnamed, unrecognisable files. The bot's search feature also now describes itself fully — its name and every piece of information it uses — so Teams' tool-builder can plug it in without anyone editing by hand. The answers the bot gives are unchanged. New automated checks for all of this now pass.

#### What was decided

Names and file labels are cleaned of odd or unsafe characters, falling back to a plain name when needed — to keep files safe and openable. The actual answers were kept exactly the same, so only labels and descriptions changed, not results.

#### What is uncertain

This stage is finished and its own checks pass. Two cautions: the work was tested on a slightly different version of the underlying software than the final target, though this is not expected to matter. Also, some unrelated checks elsewhere in the project were already failing before this work and still are — they do not touch these changes, but someone should confirm they're expected.

## Choices made for you
- (you confirmed this risky one) The response model is declared purely for OpenAPI documentation; the handlers continue returning plain dicts and the model is configured (e.g. optional fields / exclude-none as needed) so the serialized JSON stays byte-for-byte identical for both the found and not-found cases.
- (you confirmed this risky one) The 401 response is documented via FastAPI's responses= argument on the route with a description, matching the auth dependency's existing 401 behaviour, and no 401 response body schema is asserted beyond its presence.
- The information returned when looking up a paper stays exactly the same as before, so nothing that already relies on it will break.
- The system's auto-generated documentation now formally describes both the "found" and "not found" replies, so it's clearer what to expect.
- A paper's term is shown as its proper name (like "harmattan" or "rain"), not a number, matching what people actually see.
- When someone downloads a file, it opens with the correct file type recognised automatically (for example, treated as a PDF).
- Download file names are cleaned up to strip out odd or unsafe characters, with a plain fallback name if nothing usable is left; unusual non-English characters are simplified to a safe version.
- Downloads are set to open in the browser where possible rather than forcing a save.
- The new automated checks run on their own without needing a real database, network, or security keys, keeping testing fast and self-contained.

## How it was checked
- Research was switched off in the settings, so the plan was not backed by looked-up sources.
- Every build stage was written by one AI and reviewed by a different one, and every change was recorded in git.

## Does it actually work?
- 17 of 19 requirements were seen working when the finished project was run.
- Not working / not shown: All pre-existing tests pass unchanged after the edits.
- Not working / not shown: Every new test that sets app.dependency_overrides or app.state.store restores the original state in fixture teardown. The full suite passes when run in default order, in reverse order, and with each new test file run alone (for example `pytest -p no:randomly`, `pytest tests/test_tool_retrieve_body.py` and `pytest tests/test_download_headers.py`). After the new tests run, app.dependency_overrides is empty.

## What to look at
- claude-code reviewed work written by opencode-cli (anthropic/claude-sonnet-5-5): one side uses its tool's default model, so it may be the same model. Name a model for each seat to make the check verifiable.
- To make the review more independent, name a model for each seat in osa.config.json (providers.seatModels).
- This run was carried on from its saved spec: intake, research and spec were not repeated.
- The build was carried on from phase 1: phases 1 to 0 were already finished and kept. 2 commit(s) from the interrupted attempt were folded back into the working tree so the reviewer still sees that work.
- An earlier build had left "BUILD_COMPLETE.md" in the repository; it was moved to "docs/previous-builds/BUILD_COMPLETE.before-run-3ff2966e.md" (and committed) so this build could start.

## For engineers (technical detail)

_Everything above is written for non-engineers; this is the raw detail behind it._

- `decision: The '/tool/retrieve' handler is changed to return 'fastapi.responses.JSONResponse(content=<the same dict it builds today>)' instead of a bare 'dict', while the route declares 'response_model=RetrieveResponse'. Returning a 'Response' instance makes FastAPI skip response-model serialization at runtime (so the body stays byte-for-byte identical), but still render the model into '/openapi.json'. This is the chosen mechanism to satisfy "declare a response model" + "byte-for-byte unchanged" together; 'response_model_exclude_none' is NOT used (it would drop the 'course_code: null' key that `
- `decision: The rendered bytes are identical because the handler's dict contains only JSON-native values (str/int/bool/None/nested dict), so 'JSONResponse' and FastAPI's default dict-return path both emit the same 'json.dumps(..., separators=(",",":"))' output.`
- `decision: A single 'RetrieveResponse' model with all fields Optional documents both the found and not-found shapes (per the PRD's safe assumption); a nested 'PaperModel' documents the 'paper' object.`
- `decision: 'semester' is documented as a string in the response model (the runtime 'Paper.semester' is ''harmattan'|'rain''), not an integer; where the read-only spike 'openapi.yaml' shows 'semester: integer' it is a reference artifact, not a requirement, and the real runtime value wins.`
- `decision: Media type is derived via 'mimetypes.guess_type(<last path segment>)[0] or "application/octet-stream"'; 'mimetypes' is initialized at import with the standard table ('.pdf -> application/pdf').`
- `decision: The download filename is the last path segment computed by splitting the key on '/' (posix) and '\\' (backslash), then sanitized by removing/neutralising CR, LF, double-quote, backslash, and any residual '/'; if the result is empty it falls back to '"download"'. Non-ASCII is reduced to a safe ASCII filename (no 'filename*' encoding).`
- `decision: The 'Content-Disposition' header is 'inline; filename="<sanitized>"' (quoted, RFC 6266 inline disposition).`
- `decision: '/download' tests monkeypatch 'app.main.signing.verify' (True for success paths, False for the 403 path) so the header/media-type logic is exercised without depending on 'settings.url_signing_key' being configured; the fake object store is injected on 'client.app.state.store'.`
- `decision: '/tool/retrieve' tests override 'require_tool_token' and 'get_session' via 'app.dependency_overrides', monkeypatch 'app.main.retrieval.answer_query' to return a fixed 'RetrievalResult', and set 'app.state.store.signed_url' to return a fixed string, so no DB/network is touched.`
- `decision: New test files: Part A adds 'tests/test_download_headers.py' and 'tests/test_tool_openapi.py'; Part B adds 'tests/test_download_sanitise.py' and 'tests/test_tool_retrieve_body.py'. No README changes are made (the PRD limits edits to 'app/main.py' and the tests).`
- `tokens (estimated): 142657 total -- file_exploration 4%, research_input 0%, handoffs 13%, spec_prd 9%, tool_output 1%, model_output 73%`
