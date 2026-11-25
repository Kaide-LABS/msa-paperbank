# Phase 1 — Provider-neutral seams (GCP adapters only)

## Goal
Introduce four provider ports (object store, embedder, secrets, DB engine), move the existing GCP code behind GCP adapters selected by a new `provider` setting, and wire the bot to obtain implementations through a factory — with **no behaviour change** and the **existing pytest suite passing** (minimal re-pointing allowed). Satisfies AC 1, 2, 3.

## Scope
In: `app/ports.py`, `app/providers/` package with `gcp/` adapters, a factory, a `provider` setting, rerouting the object store through the live serve path + the DB engine + the secrets loader, plus unit/integration tests and a short providers doc. Out: the `gcs_*`→`object_key` rename (Phase 2), signed URLs/local/MinIO (Phase 3), local embedder (Phase 4), Docker/Compose (Phase 5), any GCP teardown (Phase 6), any Azure work (never). No new runtime dependency.

Reroute rule used throughout: replace `gcs_client.bucket(bucket).blob(key).download_as_bytes()` → `store.download_bytes(key)`; `...blob(key).upload_from_string(data, content_type=ct[, timeout=t])` → `store.upload_bytes(key, data, content_type=ct[, timeout=t])`; `...blob(key).exists()` → `store.exists(key)`; `...blob(key).delete()` → `store.delete(key)`. Function signatures change from `(…, gcs_client: storage.Client, bucket_name: str)` to `(…, store: ObjectStore)`.

## Part A (first agent)

### Files
- `app/ports.py` (new) — the four `Protocol` ports.
- `app/providers/__init__.py` (new) — factory functions.
- `app/providers/gcp/__init__.py`, `app/providers/gcp/storage.py`, `app/providers/gcp/embedder.py`, `app/providers/gcp/secrets.py`, `app/providers/gcp/engine.py` (new) — GCP adapters.
- `app/config.py` (edit) — add the `provider` setting.
- `app/main.py` (edit) — build the object store via the factory in `lifespan`; pass it into the serve path.
- `app/retrieval.py`, `app/serve_v1.py`, `app/pdfgen.py` (edit) — reroute their object-store use to `ObjectStore`.
- `tests/test_ports.py` (new) — unit tests for ports, adapters, factory.

### Interfaces and behaviour
- `app/ports.py` — `@runtime_checkable` Protocols, no heavy imports (use `TYPE_CHECKING` for `sqlalchemy.Engine`):
  - `ObjectStore`: `download_bytes(key: str) -> bytes`; `upload_bytes(key: str, data: bytes, content_type: str | None = None, timeout: int | None = None) -> None`; `exists(key: str) -> bool`; `delete(key: str) -> None`.
  - `Embedder`: `embed_one(text: str) -> list[float]`; `embed_query(text: str) -> list[float]`; `embed_documents(texts: list[str], concurrency: int | None = None) -> list[list[float]]`; property `dim: int`.
  - `SecretsProvider`: `get(ref: str) -> str` (resolve one secret reference).
  - `EngineProvider`: `create_engine() -> "Engine"`; `dispose() -> None`.
- `app/providers/gcp/storage.py` — `GcsObjectStore(client, bucket_name)` with `classmethod from_settings(settings)` building `storage.Client(project=settings.gcp_project)` and `settings.gcs_bucket`; methods map to `bucket.blob(key).download_as_bytes()` / `.upload_from_string(data, content_type=..., timeout=...)` (omit `timeout` kwarg when `None`) / `.exists()` / `.delete()`. Client built lazily (in `from_settings`/first use), never at import.
- `app/providers/gcp/embedder.py` — `GcpEmbedder(dim)` with `from_settings(settings)` (`dim=settings.embedding_dim`); each method lazily `from app import embeddings` and delegates (`embed_one`→`embeddings.embed_one`, `embed_query`→`embeddings.embed_query`, `embed_documents`→`embeddings.embed_many`). No logic duplication; `task_type` and the dim check stay in `app.embeddings`.
- `app/providers/gcp/secrets.py` — `GcpSecretsProvider.get(ref)` lazily constructs `secretmanager.SecretManagerServiceClient()` and returns `access_secret_version(name=ref).payload.data.decode("UTF-8")`.
- `app/providers/gcp/engine.py` — `GcpEngineProvider(settings)`; `create_engine()` reproduces today's `app/db.py` non-test branch exactly (Cloud SQL `Connector` creator with `pg8000`, `pool_size=2, max_overflow=2, pool_pre_ping=True, pool_recycle=1800`); `dispose()` disposes the engine and closes the connector. Does not read `DATABASE_URL_TEST` (that branch stays in `db.py`).
- `app/providers/__init__.py` — `get_object_store(settings) -> ObjectStore`, `get_embedder(settings) -> Embedder`, `get_engine_provider(settings) -> EngineProvider` switch on `settings.provider`; `get_secrets_provider() -> SecretsProvider` switches on `os.environ.get("PROVIDER", "gcp")`. `"gcp"` → the GCP adapters; any other value → `raise ValueError(f"unknown provider: {name}")`. Adapter modules imported lazily inside each function.
- `app/config.py` — add `provider: str = "gcp"` to `Settings` (env `PROVIDER`, case-insensitive like the rest). No other setting changes; secret-manager bootstrap untouched.
- `app/main.py` — in `lifespan`, keep `app.state.http`; set `app.state.store = get_object_store(settings)` (keep `app.state.gcs` for not-yet-rerouted call sites). In `webhook_inbound`, pass `request.app.state.store` to `serve_v1.handle_message_v1(...)`, `retrieval.load_served_cached(...)`, and `retrieval.load_pdf_bytes(...)` instead of `(request.app.state.gcs, settings.gcs_bucket)`.
- `app/retrieval.py` — change `load_pdf_bytes`, `load_served_bytes_v1`, `precompute_served_pdf`, `load_served_cached` to take `store: ObjectStore` (drop `gcs_client, bucket_name`) and apply the reroute rule; preserve the `precompute_served_pdf` retry loop and `timeout=600` by passing `timeout=600` to `store.upload_bytes`.
- `app/serve_v1.py` — change `handle_message_v1(session, msg, http, store)` and forward `store` wherever it currently forwards `gcs`.
- `app/pdfgen.py` — change `upload_pdf(store: ObjectStore, gcs_object: str, pdf_bytes: bytes)` to call `store.upload_bytes(gcs_object, pdf_bytes, content_type="application/pdf")`; update its `app/` callers.

### Tests (`tests/test_ports.py`)
- An in-memory `FakeObjectStore` implementing `ObjectStore` round-trips `upload_bytes`→`download_bytes`→`exists`→`delete`; `isinstance(fake, ObjectStore)` is `True` (runtime-checkable).
- `GcsObjectStore` with a `MagicMock` `storage.Client` asserts `download_bytes`/`upload_bytes(content_type=...)`/`exists`/`delete` translate to the expected `bucket().blob().*` calls; constructing the adapter opens no real client.
- `GcpEmbedder` with `app.embeddings` patched asserts delegation to `embed_one`/`embed_query`/`embed_many` and `dim == 768`.
- Factory: `get_object_store`, `get_embedder`, `get_engine_provider` return the GCP adapters for `provider="gcp"` and `raise ValueError` for an unknown provider; `get_engine_provider(...).create_engine` is not called (no DB connect in the unit test).
- No test performs a network call.

## Part B (second agent)

### Files
- `app/db.py` (edit) — build the non-test engine via `EngineProvider`.
- `app/config.py` (edit) — route `load_settings_with_secret_manager` through `SecretsProvider`.
- `app/intake.py`, `app/contributions.py`, `app/build_served_pdfs.py` (edit) — reroute remaining `app/` object-store use to `ObjectStore`.
- `admin/curate.py` (edit) — reroute its storage use to the store seam.
- `tests/test_curate_promote.py` (edit) — re-point the `@patch('admin.curate.storage.Client')` test at the new seam (no behavioural assertion changed).
- `tests/test_ports_integration.py` (new) — integration + error/edge tests.
- `docs/providers.md` (new) — usage/README doc.

### Interfaces and behaviour
- `app/db.py` — replace the non-`TEST_DB_URL` `engine`/`getconn` construction with a module-level `_engine_provider = get_engine_provider(settings)` and `engine = _engine_provider.create_engine()`; `dispose()` delegates to `_engine_provider.dispose()`. The `TEST_DB_URL` branch, `SessionLocal`, `Base`, and all ORM models stay byte-for-byte. (Import `get_engine_provider` lazily inside the module to avoid a config↔providers import cycle.)
- `app/config.py` — `load_settings_with_secret_manager()` keeps its exact semantics (no-op unless `GCP_LOAD_FROM_SECRETS == "1"`; resolve each `*_FROM_SECRET` env var and set the base name) but resolves each reference via `get_secrets_provider().get(ref)` instead of calling `secretmanager` directly.
- `app/intake.py`, `app/contributions.py`, `app/build_served_pdfs.py`, `admin/curate.py` — apply the reroute rule; obtain the store via `get_object_store(settings)` at the same point they build `storage.Client` today (CLIs/build scripts construct it at entry; `app/` request/sweep paths receive it as a parameter). After this, no raw `storage.Client` remains in these files.

### Tests
- `tests/test_curate_promote.py` — patch the store seam `admin.curate` uses now (e.g. `get_object_store`) instead of `storage.Client`; assertions unchanged.
- `tests/test_ports_integration.py`:
  - A retrieval loader (`app.retrieval.load_pdf_bytes`) runs end-to-end against a `FakeObjectStore` seeded with PDF bytes and returns `(bytes, filename)`.
  - `GcpSecretsProvider` is never constructed when `GCP_LOAD_FROM_SECRETS` is unset (loader is a no-op, no network).
  - `GcpEngineProvider.create_engine` used in the test path still honours `DATABASE_URL_TEST` via `app/db.py` (suite stays on sqlite; no network).
  - Error/edge: factory `ValueError` on unknown provider surfaces a clear message; an `Embedder` wrong-dim error from the underlying function propagates as `EmbeddingError`; `ObjectStore.download_bytes` on a missing key raises (fake mirrors the GCS not-found behaviour).
- `docs/providers.md` documents the four ports, the `provider` setting (`PROVIDER`, default `gcp`), how `app.state.store`/engine/secrets are built, and how a future provider is added (new `app/providers/<name>/`, extend the factory). It must not instruct running any fetched code and must not edit the PRD.

## Acceptance-criteria mapping
- **AC 1 — existing pytest passes unchanged (minimal re-pointing allowed):** full suite green after Parts A+B; only `tests/test_curate_promote.py`'s patch target changes; no behavioural assertion altered. Check: `pytest` passes.
- **AC 2 — no network calls in unit tests:** adapters build clients lazily; tests use fakes/mocks; `test_ports`/`test_ports_integration` exercise the seams without sockets, and assert the secrets loader is a no-op when unset. Check: suite runs with no outbound network.
- **AC 3 — ports exist for object store, embedder, secrets, DB engine, selectable by a provider setting, with GCP impls behind them:** `app/ports.py` defines all four; `app/providers/` holds GCP adapters; the factory returns them for `provider="gcp"`. Check: `tests/test_ports.py` asserts each factory call returns the GCP adapter and that `settings.provider` defaults to `"gcp"`.

## Documentation sources
- FastAPI Advanced — Lifespan Events: https://fastapi.tiangolo.com/advanced/events/
- FastAPI Tutorial — Dependencies: https://fastapi.tiangolo.com/tutorial/dependencies/
- SQLAlchemy 2.0 Documentation (en/20 index): https://docs.sqlalchemy.org/en/20/
- Settings Management — Pydantic documentation: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/
- pgvector/pgvector GitHub README: https://github.com/pgvector/pgvector

## Out of scope for this phase
- The `gcs_*`→`object_key` rename, SQLAlchemy `synonym()`, env `AliasChoices` (Phase 2).
- Signed/expiring download URLs, filesystem/MinIO object store, file/env secrets provider, plain-Postgres engine, tool-endpoint auth, removing hardcoded secrets in `apply_migrations.py`/scripts/Dockerfile (Phase 3).
- Local CPU embedder, re-embed job, parity harness (Phase 4).
- Dockerfile/Compose/health checks/backup/RUNBOOK/reverse proxy (Phase 5).
- Any cutover tooling or GCP teardown; any modification to GCP prod (`ummah`); any Azure work.
- Channel-neutral `InboundMessage`/`handle_inbound`, WhatsApp thin adapter (Phase 2).
- Changing the daily cost-cap breaker.

## Spec assumptions

Gaps found while writing this spec were resolved as follows (nobody was asked):

- The authoritative codebase is the root-level tree (`app/`, `admin/`, `review/`, `cloud_ingest/`, `scripts/`, `migrations/`, `tests/`, `apply_migrations.py`); the nested `msa-paperbank/` directory is a stale partial mirror and is NOT edited in any phase.
- Ports live in a new `app/ports.py` as `typing.Protocol` classes (structural, not ABCs); GCP adapters live in a new `app/providers/gcp/` package; a factory in `app/providers/__init__.py` selects implementations by a new setting.
- The provider setting is named `provider` (env `PROVIDER`), added to `app/config.Settings` with default `"gcp"`. This phase only `"gcp"` is a valid value; `"local"`/`"minio"` arrive in later phases. An unknown value raises `ValueError` at factory call time.
- Phase 1 is a pure refactor with GCP implementations only: no new runtime dependencies, no new network calls, no behaviour change. No Azure, no local embedder, no MinIO, no signed URLs this phase.
- The `ObjectStore` port this phase exposes `download_bytes`/`upload_bytes`/`exists`/`delete` only (the exact GCS operations the code uses today). `signed_url` is deferred to Phase 3.
- The `Embedder` port mirrors `app.embeddings` (`embed_one`, `embed_query`, `embed_documents`) plus a `dim` property; `GcpEmbedder` delegates to the existing `app.embeddings` functions by lazy import (no logic duplication), preserving `task_type` RETRIEVAL_QUERY/RETRIEVAL_DOCUMENT and the dimension check.
- The `gcs_object` DB columns and the `gcs_bucket`/`media_gcs_prefix`/`*_gcs_prefix` settings keep their names this phase; the neutral `object_key` rename is Phase 2 (per the PRD), so the storage port is provider-neutral regardless of these legacy names.
- The secrets provider is selected by a direct `os.environ` read (not via `Settings`) to avoid the secrets-load-before-settings bootstrap and a config↔providers circular import; it preserves the existing `GCP_LOAD_FROM_SECRETS` / `*_FROM_SECRET` behaviour exactly.
- Adapters instantiate their underlying GCP clients lazily (on first use / via `from_settings`), never at module import, so importing any provider module makes no network call.
- The existing test that patches `admin.curate.storage.Client` may be minimally re-pointed at the new store seam; no behavioural assertion is changed. This counts as satisfying "existing pytest passes unchanged."
- The `DATABASE_URL_TEST`/sqlite pytest branch in `app/db.py` and `tests/conftest.py` is preserved unchanged; only the non-test Cloud SQL engine construction is routed through the engine-provider port.
- The daily cost-cap breaker is left untouched this phase (the PRD's "make harmless or remove" is not a provider seam); it is addressed in a later phase.

## Implications

Second-order consequences found by an independent review of this spec. This section only adds to the spec; the locked PRD is unchanged.

### Additional acceptance criteria

S1. Importing app.db (and any module that imports it) performs no network call and does not construct a Cloud SQL Connector unless and until an engine is actually used; the module-level engine assignment must not itself open a connection. _(maintenance: Part B's db.py refactor builds the engine via EngineProvider at module import time, so importing app.db still triggers Cloud SQL Connector construction unless lazily deferred like other adapters.)_

### Explicitly out of scope

- Token rotation, multi-token support, and rate-limiting for the Phase 3 tool-endpoint auth are out of scope for this migration; a single static shared secret read from the secrets provider is sufficient for this phase. _(security)_

### Noted, no action

- Error messages surfaced by load_settings_with_secret_manager on a failed secret resolution may change wording after Part B, though success-path behaviour is unchanged. _(data)_
