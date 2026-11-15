# Providers

Phase 1 introduces four provider-neutral ports so the bot's GCP dependencies can be
swapped out, one at a time, in later phases without touching call sites.

## Ports (`app/ports.py`)

Four structural `typing.Protocol` interfaces, `@runtime_checkable` so tests and call
sites can assert conformance with `isinstance(...)`:

- **`ObjectStore`** — `download_bytes`, `upload_bytes`, `exists`, `delete`. The exact
  blob operations the code performs today against GCS.
- **`Embedder`** — `embed_one`, `embed_query`, `embed_documents`, and a `dim` property.
  Mirrors `app.embeddings`.
- **`SecretsProvider`** — `get(ref) -> str`, resolving one secret reference.
- **`EngineProvider`** — `create_engine()` / `dispose()` for the non-test SQLAlchemy
  engine.

## The `provider` setting

`app.config.Settings.provider` (env `PROVIDER`, default `"gcp"`) selects which adapters
the factory returns. This phase only `"gcp"` is a valid value; `"local"` / `"minio"`
arrive in Phase 3/4. An unknown value raises `ValueError` at factory call time.

## The factory (`app/providers/__init__.py`)

- `get_object_store(settings)`, `get_embedder(settings)`, `get_engine_provider(settings)`
  switch on `settings.provider`.
- `get_secrets_provider()` switches on the `PROVIDER` environment variable directly
  (the secrets loader runs before `Settings` is built, so it cannot depend on it).

Adapter modules are imported lazily inside each factory function, and every GCP
adapter builds its underlying client lazily (on first use, or in `from_settings`),
never at import time — so importing `app.providers` or any adapter module opens no
network connection.

## How the pieces are built

- `app/main.py`'s `lifespan` builds `app.state.store = get_object_store(settings)` once
  at boot and passes it down the live serve path (`serve_v1.handle_message_v1`,
  `retrieval.load_served_cached`, `retrieval.load_pdf_bytes`).
- `app/db.py` builds the non-test engine via `get_engine_provider(settings).create_engine()`;
  `dispose()` delegates to the provider. The `DATABASE_URL_TEST` / sqlite pytest branch
  is untouched.
- `app/config.load_settings_with_secret_manager()` resolves each `*_FROM_SECRET` env var
  via `get_secrets_provider().get(ref)` instead of calling Secret Manager directly; it
  stays a no-op unless `GCP_LOAD_FROM_SECRETS=1`.
- `admin/curate.py`, `app/intake.py`, `app/contributions.py`, `app/build_served_pdfs.py`
  obtain the object store via `get_object_store(settings)` (CLIs/build scripts at entry;
  request/sweep paths receive it as a parameter) and call `store.download_bytes` /
  `store.upload_bytes` / `store.delete` instead of raw `storage.Client` calls.

## Adding a new provider

1. Add a new package under `app/providers/<name>/` implementing the ports you need
   (`ObjectStore`, `Embedder`, `SecretsProvider`, `EngineProvider`).
2. Extend each factory function in `app/providers/__init__.py` with a branch for the new
   provider name, importing the new adapter module lazily inside the branch.
3. Set `PROVIDER=<name>` (and any adapter-specific settings) in the environment.

No call site outside `app/providers/` needs to change — they depend only on the ports.
