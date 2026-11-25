# Handoff from phase 6

Outcome: completed.

## Turns
- turn 0 executor/claude-code: completed
- turn 1 executor/codex-cli: completed, continuity CONTINUED
- turn 2 reviewer/claude-code: completed, continuity CONTINUED

## Work done
- executor/claude-code: Verified and completed Phase 6 (Parts A and B) already present in the working tree, then committed it. Part A cutover tooling exists and passes its tests: cutover/01_dump_cloudsql.sh, 02_copy_bucket.sh (read-only, dry-run-by-default, --confirm + docs/SIGNOFF.md gated), 03_restore_selfhosted.sh and 04_reembed.sh/05_parity.sh (self-hosted writes only, reusing scripts/restore.sh, app.reembed, app.parity), 06_side_by_side.py (two-HTTP-endpoint top-k agreement, no google/app.providers.gcp import), 07_webhook_move.md, CUTOVER.md runbook, docs/SIGNOFF.md placeholder. Part B teardown is complete: app/config.py provider default is "local"; app/providers/__init__.py has no gcp branch (gcp raises ValueError); app/providers/gcp/ deleted; app/embeddings.py, cloud_ingest/, scripts/drive_import.py, scripts/upload_test_batch.py, scripts/restore_drill.sh deleted; app/main.py, app/llm.py, app/ocr.py, admin/*, review/main.py de-Vertexed; requirements.txt drops google-genai/google-cloud-storage/cloud-sql-python-connector/google-cloud-secret-manager/vertexai and google-api/auth packages. Confirmed via scan that the app/admin/review/scripts/migrations .py tree contains zero google.cloud/google.genai/vertexai/cloud_sql/storage.Client references (only the two test files carry the literal match strings). Made this turn's edits: corrected the now-inverted stale docstring in app/providers/__init__.py and the stale GCP-boot comments in app/main.py to reflect local-default/no-GCS reality; removed the redundant createdb --if-exists line in scripts/restore.sh (carried-over cosmetic); restored a Privacy/opt-out (STOP TRACKING) note and added a Cutover pointer to CUTOVER.md in README.md (carried-over docs). Ran focused suites under sandbox Python 3.14: test_cutover_tooling + test_no_gcp_imports (29), test_backup_restore + test_deploy_compose (37 cumulative), and test_parity + test_reembed + test_secrets_engine_auth + test_local_embedder (22) all pass.
- executor/codex-cli: Reviewed the Phase 6 spec, PRD, and context; removed eval-based execution of environment-controlled command values from cutover steps 01, 02, 03, and 05 while preserving dry-run output and safety guards; added a regression test forbidding unsafe eval; ran 29 focused Phase 6 tests successfully. Git commit was attempted but sandbox permissions denied creation of .git/index.lock, so the changes remain in the working tree for OSA capture.
- reviewer/claude-code: Reviewed the Phase 6 executor output (cutover tooling + GCP teardown) against PHASE_6_SPEC.md and the diff. Read every prior-turn artifact_written (cutover/01,02,03,05 and tests/test_cutover_tooling.py) and matched each SHA-256 to the prior handoff. Verified Part A: all eight cutover steps present (cutover/01-07 + CUTOVER.md + docs/SIGNOFF.md), every prod-touching script dry-run-by-default and gated on --confirm plus a committed docs/SIGNOFF.md GRANTED marker, read-only prod access (export/rsync), no secret literals, 06_side_by_side.py pure and importing no google.*/app.providers.gcp symbol. Verified Part B teardown: provider default flipped to local in app/config.py, app/providers/__init__.py gcp branches removed (raises ValueError for gcp), app/providers/gcp/ and the Vertex/GCS modules (admin/health.py, admin/upload.py, app/embeddings.py, app/build_title_embeddings.py, etc.) deleted, requirements.txt free of the GCP/Vertex packages, app/main.py constructs no GCS client. Confirmed AC 12 (tests/test_no_gcp_imports.py repo-wide scan + requirements check + removed-provider ValueError) and AC 13 (scripts exist, gated, none executed; code teardown git-reversible, prod untouched). Ran focused suites under sandbox Python 3.14: tests/test_cutover_tooling.py + tests/test_no_gcp_imports.py = 34 passed; tests/test_deploy_compose.py + tests/test_secrets_engine_auth.py + tests/test_local_embedder.py + tests/test_reembed.py + tests/test_parity.py = 27 passed. Confirmed carried-over cleanup state: README privacy/opt-out note restored, restore.sh createdb --if-exists corrected (flag now only on the dropdb line), MinIO healthcheck still uses mc ready local (optional, off-by-default, not addressed). Flagged non-blocking: the MinIO healthcheck and a stale app/config.py provider comment. Authored BUILD_COMPLETE.md as the build completion record (per-phase summary, AC 1-13 verification table, test status, run/operate instructions, deferred items).

## Files changed
- .osa/runs/5069df1c-daa1-44f4-9f0b-26eaa8cf2290/handoff/6/002-reviewer-claude-code.json
- BUILD_COMPLETE.md
- CUTOVER.md
- README.md
- admin/health.py
- admin/upload.py
- app/build_title_embeddings.py
- app/config.py
- app/embeddings.py
- app/llm.py
- app/main.py
- app/ocr.py
- app/parity.py
- app/providers/__init__.py
- app/providers/gcp/__init__.py
- app/providers/gcp/embedder.py
- app/providers/gcp/engine.py
- app/providers/gcp/secrets.py
- app/providers/gcp/storage.py
- app/retrieval.py
- app/title_index.py
- cloud_ingest/Dockerfile
- cloud_ingest/__init__.py
- cloud_ingest/cloudbuild.yaml
- cloud_ingest/deploy.sh
- cloud_ingest/main.py
- cloud_ingest/requirements.txt
- cloud_ingest/teardown.sh
- cutover/01_dump_cloudsql.sh
- cutover/02_copy_bucket.sh
- cutover/03_restore_selfhosted.sh
- cutover/04_reembed.sh
- cutover/05_parity.sh
- cutover/06_side_by_side.py
- cutover/07_webhook_move.md
- docs/SIGNOFF.md
- requirements.txt
- review/main.py
- scripts/drive_import.py
- scripts/restore.sh
- scripts/restore_drill.sh
- scripts/upload_test_batch.py
- tests/test_cutover_tooling.py
- tests/test_deploy_compose.py
- tests/test_embeddings.py
- tests/test_no_gcp_imports.py
- tests/test_personalization.py
- tests/test_ports.py
- tests/test_ports_integration.py
- tests/test_retrieval_retired.py
- tests/test_retrieval_semantic.py

## Commits
- Phase 6: cutover tooling (dry-run, sign-off-gated) and GCP code teardown
- chore: capture a dispatched turn's uncommitted working-tree changes
- Phase 6 review: verify cutover tooling + GCP teardown; build completion record

## Next steps recorded by the agents
- Confirm the full pytest suite is green in the project's real Python 3.12 environment; the sandbox Python 3.14 reportlab-mock in conftest blocks collection of app.pdfgen-importing modules, so only the touched-surface suites were run here.
- On an operator Docker host, verify docker compose up brings db and app to healthy under provider=local with no GCP credentials.
- Optional carried-over: switch the profile-gated minio healthcheck off `mc ready local` to an HTTP liveness probe (left unchanged this turn to avoid introducing another image-tooling-dependent probe; MinIO is off by default).
- Run the full pytest suite in the project's Python 3.12 environment.
- Verify Docker Compose health and credential-free local boot on an operator Docker host.
- Confirm the full pytest suite is green in the project's real Python 3.12 environment (the sandbox Python 3.14 reportlab-mock collection error blocks app.pdfgen-importing modules).
- On an operator Docker host, verify docker compose up brings db and app to healthy under provider=local with no GCP credentials and no outbound internet at container start, and that --profile minio starts MinIO healthy.
- Execute the operational cutover (dump, bucket copy, re-embed, parity, side-by-side, webhook move) on the owner timeline only after docs/SIGNOFF.md reads Status: GRANTED.
- Optional non-blocking cleanup: switch the MinIO healthcheck to an HTTP liveness probe and correct the stale provider comment in app/config.py.
