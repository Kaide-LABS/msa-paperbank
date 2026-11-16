# Application check

**Failed** -- 7 requirement(s) not met.

## AC1: The existing pytest suite passes unchanged after Phase 1 (tests minimally re-pointed at new seams are allowed; no behavioural assertion changed).
Status: **unmet**

The full pytest suite fails during collection because scripts.drive_import is missing.

- `python -m pytest -q` (exit 2)

  ```
  ModuleNotFoundError: No module named 'scripts.drive_import'
  ```

## AC2: No unit test makes a network call during the test run.
Status: **met**

A network-guarded unit-test run completed without any socket call.

- `python -c "...socket connect guard...; pytest.main([...])"` (exit 0)

  ```
  27 passed, 3 warnings in 2.32s
  ```

## AC3: Ports exist for object store, embedder, secrets, and DB engine, selectable by a provider setting, with the existing GCP implementations behind them.
Status: **unmet**

The four ports exist, but the provider factory rejects the required gcp provider and no GCP adapters are present.

- `python -c "...print ports and test local/gcp factories..."` (exit 0)

  ```
  ports= ['ObjectStore', 'Embedder', 'SecretsProvider', 'EngineProvider']; local_embedder= LocalCpuEmbedder dim= 768 lazy= True; gcp_factory= ValueError unknown provider: gcp
  ```

## AC4: handle_inbound and the retrieval callable import no WhatsApp-specific types; WhatsApp is routed through a thin adapter.
Status: **met**

The neutral core imports no WhatsApp types and a real WhatsApp-shaped payload is translated by the thin adapter.

- `python -c "...WAMessage.model_validate(payload); to_inbound(...); print(i.model_dump())"` (exit 0)

  ```
  {'channel': 'whatsapp', 'sender': '2348000000000', 'message_id': 'm1', 'kind': 'text', 'text': 'MTH102', ...}
  ```

## AC5: The gcs_* rename is applied via a reversible migration using SQLAlchemy synonyms, and the pre-existing env variable names still resolve.
Status: **unmet**

Legacy environment aliases and ORM synonyms work, but the required migration runner is missing.

- `python -m pytest -q tests/test_object_key_rename.py` (exit 1)

  ```
  legacy_bucket= legacy-bucket; legacy_media_prefix= legacy-media/; 1 failed, 1 passed; FileNotFoundError: apply_migrations.py
  ```

## AC6: The ObjectStore issues signed download URLs that are accepted before ~15 minutes and rejected after expiry or on tampered signature.
Status: **met**

Signed URLs verify when fresh and reject expiry, signature tampering, and key tampering.

- `python -c "...create and verify signed URL..."` (exit 0)

  ```
  fresh= True; expired= False; tampered_sig= False; tampered_key= False
  ```

## AC7: No plaintext DB password, Cloud SQL connection string, or hardcoded GCP project id remains in apply_migrations.py, scripts, or the Dockerfile.
Status: **unmet**

No forbidden literals were found in the present scripts or Dockerfile, but apply_migrations.py is missing entirely.

- `python -m pytest -q tests/test_secrets_engine_auth.py::test_tracked_sources_contain_no_gcp_secret_literals tests/test_backup_restore.py::test_backup_restore_scripts_are_safe_and_valid; ...scan...` (exit 0)

  ```
  1 passed, 1 skipped; apply_migrations.py: MISSING; (none in scripts/Dockerfile)
  ```

## AC8: The local embedder produces 768-dimension vectors and the Vector(768) schema plus HNSW index are retained unchanged.
Status: **met**

The local embedder tests pass and the 768-dimensional schema and HNSW definition are present.

- `python -m pytest -q tests/test_local_embedder.py; rg -n 'Vector\(768\)|paper_chunks_hnsw|USING hnsw' app/db.py migrations/002_phase2.sql app/reembed.py` (exit 0)

  ```
  10 passed; app/db.py: embedding ... Vector(768); migrations/002_phase2.sql: CREATE INDEX ... USING hnsw
  ```

## AC9: A re-embed job repopulates chunk and title embeddings, and a recorded parity report compares old vs new top-k results on a fixed query set.
Status: **unmet**

Chunk re-embedding and parity calculations pass, but title embeddings are not re-embedded and the report records no measurement.

- `python -m pytest -q tests/test_reembed.py tests/test_parity.py; rg -n -i 'title.*embedding|embedding.*title|title_embedding' app migrations docs scripts cutover` (exit 0)

  ```
  7 passed; docs/parity_report.md: No populated local corpus was available ... no database-backed measurement is claimed here.
  ```

## AC10: docker compose up starts bot + Postgres (pgvector, pg_trgm) + optional MinIO, and each service reports healthy via its health check.
Status: **unmet**

Compose cannot be started from the repository because the required .env and apply_migrations.py are absent.

- `docker compose --env-file .env.example --profile minio config --services; docker compose --env-file .env.example --profile minio config; ...` (exit 1)

  ```
  db; minio; app; backup; env file ...\.env not found; apply_migrations_exists=False
  ```

## AC11: README and RUNBOOK exist covering startup, nightly backup, restore-from-backup drill, and HTTPS reverse proxy setup.
Status: **met**

README and RUNBOOK document startup, nightly backups, restore drills, and HTTPS reverse proxy setup.

- `rg -n -i 'docker compose|nightly backup|restore|reverse proxy|https|caddy|nginx' README.md RUNBOOK.md; python -m pytest -q tests/test_backup_restore.py::test_docs_cover_operations` (exit 0)

  ```
  README/RUNBOOK contain startup, backup, restore drill, HTTPS reverse proxy, Caddy, and nginx guidance; 1 passed
  ```

## AC12: After the Phase 6 final step, no google.cloud, google-genai, vertexai, or cloud-sql-connector imports remain in the codebase.
Status: **met**

The final import gate passes and no forbidden GCP import families remain in application code.

- `python -m pytest -q tests/test_no_gcp_imports.py` (exit 0)

  ```
  3 passed, 3 warnings in 0.65s
  ```

## AC13: Phase 6 migration/cutover/teardown scripts exist but are not executed, and GCP production remains running and reversible.
Status: **unmet** (the check could not exercise this criterion)

Cutover scripts exist and their dry-run safety tests pass, but GCP production state cannot be verified from this disposable offline copy.

- `python -m pytest -q tests/test_cutover_tooling.py` (exit 0)

  ```
  26 passed, 5 skipped in 0.39s
  ```

## S1: Importing app.db (and any module that imports it) performs no network call and does not construct a Cloud SQL Connector unless and until an engine is actually used; the module-level engine assignment must not itself open a connection.
Status: **met**

Importing app.db under a guarded PostgreSQL URL constructs only a SQLAlchemy Engine and makes no network call or Cloud SQL connector import.

- `python -c "...patch socket; import app.db; assert no cloud_sql modules..."` (exit 0)

  ```
  imported_engine= Engine; cloud_sql_connector_loaded= False
  ```
