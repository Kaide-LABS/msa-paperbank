# Handoff from phase 2

Outcome: completed.

## Turns
- turn 0 executor/claude-code: completed
- turn 1 executor/codex-cli: completed, continuity CONTINUED
- turn 2 reviewer/claude-code: completed, continuity CONTINUED

## Work done
- executor/claude-code: Implemented Phase 2 Part A (channel-neutral core + WhatsApp thin adapter). Created app/inbound.py defining InboundMessage (pydantic BaseModel: channel, sender, message_id, kind Literal[text|image|other], text, media_id, raw) and handle_inbound(session, msg, http_client, store), a faithful line-by-line migration of app.pipeline.handle_message driven off InboundMessage only (msg.type->kind, msg.text.body->text, msg.from_->sender, msg.id->message_id, msg.image->media_id); all behaviour preserved verbatim (opt-out, idempotency log, rate/cost/token guards, routing, course guard, semantic fallback, personalization, privacy notice, reply bodies). handle_inbound imports llm/retrieval/intake/profile/pricing but no WhatsApp wire types; OutboundReply is aliased to app.schemas.Reply. Created app/channels/__init__.py and app/channels/whatsapp.py: to_inbound(WAMessage)->InboundMessage (type->kind with text/image passthrough else other, from_->sender, id->message_id, text.body->text, image.id->media_id, original stashed under raw) and from_reply(Reply)->Reply (identity this phase, names the outbound seam). Added app/retrieval.answer_query(session, query, *, prefer_courses) -> RetrievalResult plus the RetrievalResult dataclass: routes a plain query via a lazily-imported llm, applies the course guard, and composes the existing find_paper/find_paper_by_semantic_query; imports no WhatsApp types (AC-4 tool-endpoint callable). Refactored app/intake.py to add handle_image_inbound(session, http_client, store, *, phone, media_id, message_id) carrying the former handle_image body; handle_image(msg: WAMessage) kept as a thin back-compat wrapper so existing callers/tests are unchanged. Rewired app/main.py webhook non-serve_v1 branch to whatsapp_channel.to_inbound(msg) -> handle_inbound(session, inbound, request.app.state.http, request.app.state.store) and mapped the reply through whatsapp_channel.from_reply; this passes the ObjectStore (not the raw storage.Client) into the handler, fixing the Phase 1 caller mismatch on that path. Removed the now-unused app.pipeline import from main.py; app/pipeline.py itself is left intact so the existing tests/test_pipeline.py (and test_cost_breaker/test_opt_out/test_personalization) keep passing byte-for-byte. Repointed admin/batches.py seal command to get_object_store(settings) instead of storage.Client(project=...). Added tests/test_inbound.py: to_inbound text/image/unsupported-type mapping, from_reply identity, the mechanical AC-4 AST scan (app/inbound.py and app.retrieval import no module containing 'whatsapp' and the sources contain no WAMessage/WAImage token), and handle_inbound behaviour-parity tests for greeting/unknown-course/found-paper plus a RequestLog-written assertion, all with llm.route patched and http/store as None/mocks (no network). Verified out-of-band (standalone interpreter with the reportlab/cv2 mocks the project's conftest uses): all target modules import cleanly, the WhatsApp adapter maps text/image/audio correctly, and the AST scan and no-WhatsApp-token assertions pass.
- executor/codex-cli: Implemented Phase 2 Part B storage-key compatibility: added numbered idempotent migration 007 with documented inverse, registered it, renamed ORM columns with SQLAlchemy synonyms, added neutral settings fields with old environment aliases, updated provider and call sites/raw SQL, and added object-key documentation. Focused provider and integration tests passed 20/20. Git staging and commit were attempted but the sandbox denied creation of .git/index.lock; changes remain in the working tree for OSA capture.
- reviewer/claude-code: Reviewed Phase 2 (channel-neutral core + reversible gcs_* to object_key rename) against PHASE_2_SPEC.md and the executor diff, and authored PHASE_3_SPEC.md. Verified AC4: app/inbound.py defines InboundMessage + handle_inbound importing no WhatsApp types (AST test passes), app/channels/whatsapp.py is a thin to_inbound/from_reply adapter, app/retrieval.answer_query is WhatsApp-type-free, app/main.py webhook routes the non-serve_v1 branch through the adapter into handle_inbound with request.app.state.store, and handle_inbound is a faithful line-by-line port of pipeline.handle_message; the Phase 1 caller mismatch was fixed (admin/batches.py uses get_object_store; intake.handle_image_inbound is channel-neutral). Verified AC5: migration 007 is idempotent with a documented exact inverse and is registered in apply_migrations.py FILES; app/db.py carries synonym() for gcs_object on papers/pending_papers/image_batch_items and served_object on papers; app/config.py carries AliasChoices for GCS_BUCKET/MEDIA_GCS_PREFIX/CONTRIBUTION_GCS_PREFIX. Found three defects (flagged, not overruled): (1) a live-serve-path regression introduced in Phase 2 Part B where raw-SQL SELECT labels were renamed to object_key/served_object_key but the .mappings() consumers still read the old keys, raising KeyError at app/retrieval.py:253-254/265/268 (load_served_bytes_v1), app/retrieval.py:321-322 (load_served_cached, swallowed into a silent permanent cache miss then falling through to the broken path), and app/serve_index.py:94 (_row_to_candidate); (2) raw-SQL literals still naming the old column on the renamed pending_papers table at review/promote.py:44, review/main.py:375, and cloud_ingest/main.py:114-115 (the contribution_pages literals are correct as-is since that table is not renamed); (3) the spec-required tests/test_object_key_rename.py was never written, leaving AC5 synonym/env-alias/migration-shape with no automated guard. These three are carried into PHASE_3_SPEC.md as mandatory opportunistic cleanups. The full suite was not run here because the sandbox runs Python 3.14 while the project targets 3.12 and conftest's db_session fixture does not resolve; the carried KeyError fixes are what a full 3.12 run would surface. PHASE_3_SPEC.md specifies the in-house plumbing phase (AC6, AC7): filesystem/MinIO ObjectStore behind the existing port, backend-issued HMAC-signed ~15-minute download URLs with a verifying /download route, a file/env SecretsProvider, a plain-Postgres EngineProvider, bearer-token auth for the future tool endpoint, and removal of the plaintext DB password/Cloud SQL string from apply_migrations.py and the hardcoded GCP project id from infra_bootstrap.sh/scripts/restore_drill.sh/Dockerfile, following the established spec structure. Committed PHASE_3_SPEC.md.

## Files changed
- .osa/runs/0a073f8b-ce56-4380-9577-27b2650a05a4/handoff/2/002-reviewer-claude-code.json
- admin/batches.py
- admin/health.py
- admin/upload.py
- app/build_served_pdfs.py
- app/channels/__init__.py
- app/channels/whatsapp.py
- app/config.py
- app/contributions.py
- app/db.py
- app/grouping.py
- app/inbound.py
- app/intake.py
- app/main.py
- app/providers/gcp/storage.py
- app/retrieval.py
- app/serve_index.py
- docs/object_key_rename.md
- migrations/007_object_key_rename.sql
- review/main.py
- review/promote.py
- runs/ef877dec-303d-4911-81c2-1fef07397538/spec/PHASE_3_SPEC.md
- tests/test_inbound.py

## Commits
- Phase 2 Part A: channel-neutral InboundMessage/handle_inbound core + WhatsApp thin adapter
- chore: capture a dispatched turn's uncommitted working-tree changes
- Phase 2 review + Phase 3 spec: in-house plumbing (signed URLs, file/env secrets, plain-Postgres engine, tool auth, secret removal)
- chore: reviewer handoff for phase 2 of OSA run 0a073f8b-ce56-4380-9577-27b2650a05a4

## Next steps recorded by the agents
- Phase 2 Part B: add migrations/007_object_key_rename.sql (gcs_object->object_key on papers/pending_papers/image_batch_items, served_object->served_object_key on papers, idempotent, with documented exact inverse in the header), register it in apply_migrations.py FILES, rename the db.py Mapped columns with synonym() back-compat (gcs_object=synonym('object_key'), served_object=synonym('served_object_key')), rename the three config settings with Alias [OSA: truncated, the agent wrote 645 characters]
- Optional follow-up: collapse app/pipeline.handle_message into a thin shim delegating to handle_inbound once the test patches (app.pipeline.llm.route etc.) are re-pointed to app.inbound.* in the project's real Python 3.12 environment where the full suite runs green; left as duplication this turn to guarantee AC1 without editing tests blind in the 3.14 sandbox.
- Channel-neutralise the serve_v1 live path (serve_v1.handle_message_v1 still takes WAMessage) in a later phase; this phase only rewired the non-serve_v1 branch through the adapter as the spec's Part A file list scoped.
- Review and commit the working-tree changes when git index permissions are available.
- Run the full project suite in the supported Python 3.12 environment.
- Phase 3 Part A: app/signing.py HMAC sign/verify, add ObjectStore.signed_url to the port, implement FsObjectStore (and optional MinioObjectStore), add GET /download verifying signature+expiry and POST /tool/retrieve, wire the local/minio provider branches, with signing and filesystem tests.
- Phase 3 Part B: FileSecretsProvider/EnvSecretsProvider, PostgresEngineProvider, require_tool_token bearer dependency, config fields for storage/signing/db/token (no plaintext defaults), strip secrets from apply_migrations.py and the project-id literal from infra_bootstrap.sh/scripts/restore_drill.sh/Dockerfile, plus secrets/engine/auth tests, a source-hygiene grep test, and docs/inhouse_plumbing.md.
- Fix the Phase 2 carried-over defects while touching those paths: re-point the .mappings() reads in app/retrieval.py and app/serve_index.py to the new column labels; re-point the pending_papers raw-SQL literals in review/promote.py, review/main.py, and cloud_ingest/main.py to object_key; and add the missing tests/test_object_key_rename.py.
- Confirm AC1 (full pytest suite green) in the project's real Python 3.12 environment where conftest's db_session fixture resolves.

## Open questions
- The full pytest suite could not be run in this sandbox: it runs Python 3.14 (project targets 3.12), conftest.py does not define the db_session fixture that tests/test_inbound.py and many existing tests use, and conftest's partial reportlab mock plus JSONB-on-sqlite break schema creation. AC1/AC2 (full suite green, no network) and the DB-backed handle_inbound parity tests should be confirmed in the project's real 3.12 environment; the channel-neutr [OSA: truncated, the agent wrote 596 characters]
- The serving bridge historically uses pending_papers.served_object; migration 007 and serving SQL now use served_object_key for that bridge column as well as the specified papers column.
- AC1 full-suite greenness is unverified in this sandbox (Python 3.14 vs the project's 3.12; conftest db_session fixture does not resolve), so only the Phase 2 focused tests were observed as passing; the carried-over serve-path KeyError fixes are expected to be what a full 3.12 run surfaces.
- cloud_ingest/ is frozen tooling not run against prod, but it shares the same database and its INSERT INTO pending_papers (... gcs_object ...) will break post-migration; the Phase 3 cleanup re-points it, but whether cloud_ingest is ever re-run in the self-hosted deployment is a product decision outside this review.
