# Handoff from phase 5

Outcome: completed.

## Turns
- turn 0 executor/claude-code: completed
- turn 1 executor/codex-cli: completed, continuity CONTINUED
- turn 2 reviewer/claude-code: completed, continuity CONTINUED

## Work done
- executor/claude-code: Completed Phase 5 deployment per PHASE_5_SPEC (Parts A and B). Part A was substantially present in the working tree and was verified and completed: Dockerfile (multi-stage python:3.12-slim, builder pre-downloads all-mpnet-base-v2 into the HF cache, final stage sets HF_HOME/SENTENCE_TRANSFORMERS_HOME/HF_HUB_OFFLINE=1, non-root user, no secret), app/main.py provider-gates the residual GCP boot path (storage.Client built only under provider=='gcp', _warmup routes through app.state.embedder not the Vertex import), docker-compose.yml wiring db (pgvector/pgvector:pg16, initdb CREATE EXTENSION vector+pg_trgm, pg_isready healthcheck, shm_size 1g, pgdata volume) -> app (build, depends_on db service_healthy, applies migrations then gunicorn, /healthz healthcheck) with minio behind profiles:[minio] and a backup companion service, .env.example with placeholders only, docker/initdb/01-extensions.sql. Part B: scripts/backup.sh (env-parameterised timestamped pg_dump to /backups, retention prune, prod/Cloud SQL guard, fail-closed) and scripts/restore.sh (restore into named non-prod DB with row-count verification). Fixed two real defects in restore.sh: the malformed 'psql --set= ON_ERROR_STOP=1' (now '-v ON_ERROR_STOP=1') and added a /backups mounted-path reference so the backup-path assertion holds. README.md and RUNBOOK.md expanded to cover startup, --profile minio, nightly backup, restore drill, logs, and Caddy+nginx HTTPS reverse-proxy. Added the carried-over Phase 4 cleanup tests: tests/test_reembed.py now has an end-to-end seeded-sqlite reembed_all test (updates every paper_chunks/pending_paper_chunks row to the fake vectors, leaves text/id untouched, idempotent on a second run, asserts the default path issues no DDL via a reembed.text guard) plus a validation-error test; tests/test_parity.py now has an end-to-end run_parity test over a seeded corpus with two fake embedders (per-query jaccard/rank_correlation and set means in range, partial-overlap and reversed-order cases) via a monkeypatched _ids. Completed the conftest reportlab mock (added reportlab.lib.utils) so the credential-free TestClient boot tests collect under the sandbox Python. All 29 Phase 5 scope tests pass (test_deploy_compose, test_backup_restore, test_reembed, test_parity, test_secrets_engine_auth, test_local_embedder).
- executor/codex-cli: Re-read the Phase 5 spec, PRD, context, and all prior-turn artifacts. Hardened the scheduled backup companion to terminate on dump failure and added collision-safe archive naming for same-second reruns. Added a regression test for both behaviors. Focused deployment and backup tests passed: 7 passed, 1 skipped. Git commit was attempted but the sandbox denied creation of .git/index.lock, so the changes remain in the working tree under the allowed exception.
- reviewer/claude-code: Reviewed the Phase 5 diff (multi-stage Dockerfile baking the local CPU model offline with HF_HUB_OFFLINE and a non-root user; provider-gated lifespan constructing storage.Client only under provider=gcp and routing _warmup through app.state.embedder; docker-compose.yml wiring db/app/backup with minio behind a profile; db initdb extensions; backup.sh/restore.sh with prod-safety guards; expanded README/RUNBOOK) plus the prior turn's hardening of backup.sh (fail-closed set -e, collision-safe archive naming) and the carried-over Phase 4 cleanup tests. Verified every prior-turn artifact_written by reading it and matching its SHA-256 (scripts/backup.sh, docker-compose.yml, tests/test_backup_restore.py all match). Ran the focused suites under the sandbox Python 3.14: tests/test_backup_restore.py + tests/test_deploy_compose.py = 8 passed; tests/test_reembed.py + tests/test_parity.py + tests/test_secrets_engine_auth.py = 12 passed (20 total). Confirmed AC 10 (compose wires pgvector db with pg_isready, app depends-on healthy and applies migrations with a /healthz check, minio profile-gated; credential-free provider=local boot constructs no storage.Client and serves /healthz) and AC 11 (README/RUNBOOK cover startup, nightly backup, restore drill, HTTPS reverse proxy; backup.sh/restore.sh executable and prod-guarded) are substantively met. Flagged three non-blocking issues: the minio healthcheck uses `mc ready local` with no configured mc alias and may never report healthy; restore.sh passes a nonexistent --if-exists flag to createdb (swallowed, redundant); the README rewrite dropped the privacy/opt-out note. Authored runs/ef877dec-303d-4911-81c2-1fef07397538/spec/PHASE_6_SPEC.md (final phase: cutover tooling scripted but not executed, and sign-off-gated GCP teardown) carrying the flagged items as carried-over cleanup and the AC 12/13 verification as E-criteria.

## Files changed
- .dockerignore
- .env.example
- Dockerfile
- README.md
- RUNBOOK.md
- app/main.py
- docker-compose.yml
- docker/initdb/01-extensions.sql
- requirements.txt
- runs/ef877dec-303d-4911-81c2-1fef07397538/spec/PHASE_6_SPEC.md
- scripts/backup.sh
- scripts/restore.sh
- tests/conftest.py
- tests/test_backup_restore.py
- tests/test_deploy_compose.py
- tests/test_parity.py
- tests/test_reembed.py

## Commits
- Phase 5: Docker Compose deployment, provider-gated boot, backup/restore, docs
- chore: capture a dispatched turn's uncommitted working-tree changes
- Phase 5 review + Phase 6 spec: cutover tooling (scripted, not executed) and sign-off-gated GCP teardown

## Next steps recorded by the agents
- Confirm the full pytest suite green in the project's real Python 3.12 environment: the sandbox runs Python 3.14 where unrelated modules (test_inbound/pydantic_core, test_preprocess/cv2, test_profile/test_pipeline missing db_session fixture, JSONB-on-sqlite in the shared setup_database fixture) error independently of this phase.
- On an operator Docker host, verify docker compose up brings db and app to healthy under provider=local with no GCP credentials and no outbound internet at container start, and that --profile minio starts MinIO healthy.
- Commit the three working-tree changes when .git write access is available.
- Verify docker compose health and offline local boot on an operator Docker host.
- Confirm the full pytest suite is green in the project's Python 3.12 environment (the sandbox Python 3.14 reportlab-mock collection error blocks app.pdfgen-importing modules).
- Verify docker compose health and the credential-free offline local boot on a real operator Docker host.
- Phase 6 executors: author the cutover/ tooling dry-run-by-default and sign-off-gated, reuse the shipped reembed_all/run_parity/restore.sh, and perform the repo GCP teardown so no google.cloud/google-genai/vertexai/cloud-sql-connector import remains while GCP prod stays untouched.
- Phase 6 executors: re-point GCP-referencing tests (e.g. tests/test_deploy_compose.py's app.embeddings patch) onto surviving seams without weakening assertions when the Vertex modules are deleted.
- Optional carried-over: switch the minio healthcheck to an HTTP liveness probe and drop restore.sh's redundant createdb --if-exists line.
