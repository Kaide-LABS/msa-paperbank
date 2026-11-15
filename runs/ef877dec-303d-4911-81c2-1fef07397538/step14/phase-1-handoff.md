# Handoff from phase 1

Outcome: NOT completed (exit 4).

## Turns
- turn 0 executor/claude-code: completed
- turn 1 executor/claude-code: failed

## Work done
- executor/claude-code: Implemented Phase 1 Part A (provider-neutral seams, GCP adapters only). Added app/ports.py with four runtime-checkable Protocol ports (ObjectStore, Embedder, SecretsProvider, EngineProvider), using TYPE_CHECKING for sqlalchemy.Engine and no vendor imports. Added app/providers/gcp/ adapters: GcsObjectStore (lazy storage.Client via from_settings; download/upload/exists/delete mapped to bucket.blob, timeout kwarg omitted when None), GcpEmbedder (lazy delegation to app.embeddings embed_one/embed_query/embed_many, dim property), GcpSecretsProvider (lazy SecretManagerServiceClient, access_secret_version decode), GcpEngineProvider (reproduces db.py non-test Cloud SQL Connector engine with pool_size=2/max_overflow=2/pool_pre_ping/pool_recycle=1800; connector built lazily, dispose closes both). Added app/providers/__init__.py factory: get_object_store/get_embedder/get_engine_provider switch on settings.provider, get_secrets_provider switches on os.environ PROVIDER; gcp returns adapters, any other value raises ValueError(unknown provider). Added provider setting (env PROVIDER, default gcp) to app/config.Settings. Rerouted the live serve path: app/main.py lifespan builds app.state.store via get_object_store and keeps app.state.gcs for not-yet-rerouted paths; webhook passes store to serve_v1.handle_message_v1, retrieval.load_served_cached, retrieval.load_pdf_bytes. app/retrieval.py load_pdf_bytes/load_served_bytes_v1/precompute_served_pdf/load_served_cached now take store: ObjectStore and use store.download_bytes/upload_bytes (timeout=600 preserved on precompute). app/serve_v1.py handle_message_v1 takes store and forwards it to contributions.sweep/handle. app/pdfgen.py upload_pdf takes store: ObjectStore and calls store.upload_bytes(content_type=application/pdf). Updated upload_pdf callers (admin/upload.py, scripts/drive_import.py) and the precompute_served_pdf caller in review/promote.py to build the store via get_object_store, keeping these non-scope files working after the signature changes. Added tests/test_ports.py: FakeObjectStore round-trip + isinstance, GcsObjectStore MagicMock translation + no-client-on-construct + lazy from_settings, GcpEmbedder delegation via patched app.embeddings functions + dim==768, factory returns GCP adapters for gcp and raises ValueError for unknown without calling create_engine, default provider==gcp. tests/test_ports.py passes (10 tests, no network). Committed as 23c7696. Note: the full suite could not be run green in this sandbox due to a pre-existing environment mismatch (Python 3.14 vs project 3.12: reportlab partially mocked in conftest breaks reportlab.lib.utils import; many existing tests request a db_session fixture this conftest does not define) — these failures predate and are independent of this turn's changes; all changed app modules import cleanly.

## Files changed
- admin/upload.py
- app/config.py
- app/main.py
- app/pdfgen.py
- app/ports.py
- app/providers/__init__.py
- app/providers/gcp/__init__.py
- app/providers/gcp/embedder.py
- app/providers/gcp/engine.py
- app/providers/gcp/secrets.py
- app/providers/gcp/storage.py
- app/retrieval.py
- app/serve_v1.py
- review/promote.py
- runs/7c14fca9-b258-410e-8422-e8e26a5c4cdf/baby-prd.md
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/fields.yaml
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/outline.yaml
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/report.md
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/academic-papers.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-azure-ai-document-intelligence.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-azure-container-apps-jobs.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-azure-container-registry.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-azure-database-for-postgresql-flexible-server.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-azure-key-vault.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-azure-managed-identity.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-azure-openai-service.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-microsoft-foundry-azure-ai-foundry.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-microsoft-graph-api.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-onedrive.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-pg-trgm.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-pgvector.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-sharepoint.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/docs-text-embedding-3-large.json
- runs/82e3ece4-2cd8-45d2-8c11-c129f1a79661/research/results/prior-art.json
- scripts/drive_import.py
- tests/test_ports.py

## Commits
- Phase 1 Part A: provider-neutral ports + GCP adapters + factory
- chore: capture a dispatched turn's uncommitted working-tree changes

## Next steps recorded by the agents
- Part B (second agent): route app/db.py non-test engine through EngineProvider with lazy construction per Implication S1; route load_settings_with_secret_manager through get_secrets_provider; reroute app/intake.py, app/contributions.py, app/build_served_pdfs.py and admin/curate.py object-store use to ObjectStore (build at entry for CLIs/build scripts, parameter for request/sweep paths).
- Part B: app/build_served_pdfs.py line 78 still calls retrieval.precompute_served_pdf with the old (gcs, bucket) signature and must be rerouted to pass the store (it is in Part B scope).
- Part B: re-point tests/test_curate_promote.py patch target from admin.curate.storage.Client to the new store seam (get_object_store); add tests/test_ports_integration.py and docs/providers.md.

## Problems
- ✖ Too big: expected string to have <=4000 characters
  → at work_done
