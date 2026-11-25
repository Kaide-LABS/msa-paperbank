# Handoff from phase 4

Outcome: completed.

## Turns
- turn 0 executor/claude-code: completed
- turn 1 executor/codex-cli: completed, continuity CONTINUED
- turn 2 reviewer/claude-code: completed, continuity CONTINUED

## Work done
- executor/claude-code: Completed Phase 4. Verified and committed the local CPU embedder stack: LocalCpuEmbedder (all-mpnet-base-v2, native 768-dim, CPU, lazily loaded, L2-normalized, injectable encoder, EmbeddingError on dim mismatch) behind the Embedder port, selected by get_embedder for provider local/minio with gcp unchanged; config fields (embedding_model_name/path/device/normalize/batch_size, embedding_dim stays 768); rerouted app/retrieval.py and app/intake.py onto the active embedder via the factory seam and app.state.embedder built at lifespan; reembed_all over paper_chunks/pending_paper_chunks; parity harness (jaccard_at_k, rank_correlation, run_parity) with data/parity_queries.json (18 queries), docs/parity_report.md, docs/local_embedder.md; sentence-transformers added to requirements.txt. Fixed a real E2 defect in app/reembed.py: the optional index fast-path dropped/created a wrongly-named index (ix_paper_chunks_embedding_hnsw) missing the WITH (m=16, ef_construction=64) params; corrected to recreate migration 002's exact paper_chunks_hnsw definition. All 13 phase-4 unit tests pass network-free under the sandbox Python.
- executor/codex-cli: Added a tracked-source hygiene regression test covering forbidden GCP project, Cloud SQL instance, and plaintext database password literals, with source-root exclusions for documentation and fixtures. Focused tests passed; the broader run had one unrelated sandbox tmp_path permission error.
- reviewer/claude-code: Reviewed the Phase 4 diff (local CPU embedder behind the Embedder port, factory selection, retrieval/intake reroute, re-embed job, parity harness, fixed query set, recorded parity report) plus the prior turn's carried-over Phase 3 source-hygiene regression test in tests/test_secrets_engine_auth.py. Ran the focused Phase 4 and hygiene tests (tests/test_local_embedder.py, tests/test_parity.py, tests/test_reembed.py, tests/test_secrets_engine_auth.py): 18 passed under Python 3.14. AC 8 (768-dim local embedder, lazy/injectable encoder, L2-normalized, EmbeddingError on dim mismatch, Vector(768)/HNSW/pg_trgm unchanged) and AC 9 (in-place re-embed job over both chunk tables, parity metrics + fixed query set + recorded report with proposed threshold) are substantively met. Flagged two test-depth gaps (no end-to-end reembed_all idempotency test, no seeded run_parity test) and a Phase 5 boot blocker (lifespan unconditionally builds storage.Client and _warmup calls Vertex directly, which fails under provider=local without GCP credentials). Authored runs/ef877dec-303d-4911-81c2-1fef07397538/spec/PHASE_5_SPEC.md (deployment: Dockerfile with baked offline model, docker-compose bot+Postgres+optional MinIO with health checks, provider-gated GCP boot path, nightly backup + restore drill, README/RUNBOOK, HTTPS reverse-proxy) carrying the flagged items as E-criteria and carried-over cleanup.

## Files changed
- .osa/memory/failures.md
- .osa/runs/7f28cd03-ed1f-4c31-abf5-02f3980df6c8/handoff/4/002-reviewer-claude-code.json
- app/config.py
- app/intake.py
- app/main.py
- app/parity.py
- app/providers/__init__.py
- app/providers/local/embedder.py
- app/reembed.py
- app/retrieval.py
- data/parity_queries.json
- docs/local_embedder.md
- docs/parity_report.md
- requirements.txt
- runs/ef877dec-303d-4911-81c2-1fef07397538/spec/PHASE_5_SPEC.md
- runs/ef877dec-303d-4911-81c2-1fef07397538/step14/executor-context.md
- runs/ef877dec-303d-4911-81c2-1fef07397538/step14/phase-4-handoff.md
- runs/ef877dec-303d-4911-81c2-1fef07397538/step14/phase-4-summary.md
- runs/ef877dec-303d-4911-81c2-1fef07397538/summary.md
- tests/test_local_embedder.py
- tests/test_parity.py
- tests/test_reembed.py
- tests/test_secrets_engine_auth.py

## Commits
- Phase 4: local CPU embedder behind Embedder port, re-embed job, top-k parity harness
- chore: capture a dispatched turn's uncommitted working-tree changes
- Phase 4 review + Phase 5 spec: deployment (Docker Compose, health, backup/restore, RUNBOOK)

## Next steps recorded by the agents
- Reviewer to confirm the full suite is green under the project's Python 3.12 environment (sandbox runs 3.14 where conftest reportlab mock breaks modules importing app.pdfgen).
- Carried Phase 3 gap, optional: add the source-hygiene grep test asserting zero plaintext DB password / Cloud SQL / GCP project-id matches over tracked sources (AC 7 regression guard).
- Reviewer should verify the full suite in the project Python 3.12 environment.
- The working-tree change should be committed when .git write access is available.
- Phase 5 executors must provider-gate the lifespan storage.Client construction and route _warmup through app.state.embedder so the container boots healthy under provider=local with no GCP credentials.
- Phase 5 executors should add the carried-over end-to-end tests: reembed_all idempotency on a seeded sqlite session and run_parity over a seeded corpus.
- Confirm the full pytest suite green in the project's Python 3.12 environment (the sandbox Python 3.14 reportlab-mock collection error blocks app.pdfgen-importing modules).

## Warnings
- chat log: credential-shaped content detected in phase 4 turn 1 (executor/codex-cli, response entry). The log was written verbatim -- nothing was redacted, masked, or altered.
