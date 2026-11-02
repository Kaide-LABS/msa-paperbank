# Phase 1 — Provider-neutral seams, channel-agnostic core, non-destructive rename

## Goal
Introduce the provider-neutral interfaces and GCP adapters that every later phase plugs into, wire the storage seam through the live serve path, expose a WhatsApp-type-free handler core and retrieval callable, and land the non-destructive `gcs_*`→neutral rename — all with **zero behavior change** and the **existing pytest suite passing unchanged**.

## Scope
In: `app/ports.py`, `app/providers/` (gcp only), `cloud_provider` config, storage-seam wiring in `app/main.py`+`app/retrieval.py`+`app/pdfgen.py`, neutral `InboundMessage`/`handle_inbound`, migration `007` + ORM synonyms, and new tests for the storage/secrets/AI abstractions and the channel-agnostic core.
Out: any `azure-*` code or dependency; rewriting `serve_v1` internals; migrating every storage call site; touching `apply_migrations.py`, deploy scripts, or GCP prod.

## Part A (first agent)
Delivers the interfaces, the GCP adapters, the factory + config switch, the storage-seam wiring into the serve path, and the storage/secrets abstraction tests.

### Files
- **`app/ports.py` (new).** `Protocol`s:
  - `ObjectStore`: `download_bytes(key: str) -> bytes`; `upload_bytes(key: str, data: bytes, content_type: str, *, timeout: int | None = None) -> None`; `exists(key: str) -> bool`. (The store owns its bucket/container name; keys are bare object keys.)
  - `StructuredLLM`: `generate_json(contents, system_instruction: str, response_schema: type, *, model: str, max_output_tokens: int, temperature: float) -> str` (returns raw JSON text; caller validates).
  - `VisionOCR`: `read_paper(image_bytes_list: list[bytes]) -> "OcrPaperExtraction"`.
  - `Embedder`: `embed(text: str, *, query: bool) -> list[float]`; `embed_batch(texts: list[str]) -> list[list[float]]`.
  - `SecretsProvider`: `get_secret(ref: str) -> str`.
  - `EngineFactory`: `build_engine() -> "sqlalchemy.Engine"`.
- **`app/providers/__init__.py` (new).** Factories `build_object_store(settings)`, `build_structured_llm(settings)`, `build_vision_ocr(settings)`, `build_embedder(settings)`, `build_secrets_provider(settings)`, `build_engine_factory(settings)`. Each dispatches on `settings.cloud_provider`: `"gcp"` → import from `app.providers.gcp` (lazy, inside the function); `"azure"` → `raise NotImplementedError("azure provider lands in a later phase")`; anything else → `raise ValueError`. No module-level `azure`/`google` imports here.
- **`app/providers/gcp.py` (new).** GCP adapters, each conforming to its Protocol:
  - `GcsObjectStore(client, bucket_name)` wrapping `google.cloud.storage`: `download_bytes` → `bucket.blob(key).download_as_bytes()`; `upload_bytes` → `blob.upload_from_string(data, content_type=..., timeout=...)`; `exists` → `blob.exists()`. A classmethod `from_settings(settings)` builds the `storage.Client(project=settings.gcp_project)` and resolves the bucket from `settings.object_store_bucket`.
  - `GeminiStructuredLLM`, `GeminiVisionOCR`, `GeminiEmbedder`: thin wrappers delegating to the existing `app.llm.call_pro_vision`/`app.llm.route`-style calls, `app.ocr.ocr_paper`, and `app.embeddings.embed_query`/`embed_one`/`embed_many` (import lazily; do not duplicate logic).
  - `SecretManagerSecrets`: wraps the existing Secret Manager access pattern in `app.config`.
  - `gcp_engine_factory`: returns the existing `app.db` engine (reuse, don't rebuild).
- **`app/config.py` (edit).** Add `cloud_provider: Literal["gcp","azure"] = "gcp"`. Add `object_store_bucket: str` using `AliasChoices("object_store_bucket","gcs_bucket")` so the existing `GCS_BUCKET` env keeps working; keep `gcs_bucket` readable as a property/alias for untouched call sites.
- **`app/main.py` (edit).** In `lifespan`, set `app.state.store = build_object_store(settings)`. Keep `app.state.gcs` as the underlying client for not-yet-migrated call sites. Update the serve-path `paper_loader` lambdas to call the refactored loaders with `app.state.store`.
- **`app/retrieval.py` (edit).** Change `load_pdf_bytes`, `load_served_bytes_v1`, `precompute_served_pdf`, `load_served_cached` to take `store: ObjectStore` instead of `(gcs_client, bucket_name)`; replace `gcs_client.bucket(bucket_name).blob(obj).download_as_bytes()`/`upload_from_string(...)` with `store.download_bytes(obj)`/`store.upload_bytes(...)`. Behavior identical (same retry/timeout semantics in `precompute_served_pdf`).
- **`app/pdfgen.py` (edit).** Change `upload_pdf` to take `store: ObjectStore` and call `store.upload_bytes(gcs_object, pdf_bytes, "application/pdf")`.

### Interfaces and behaviour
- Factories are pure functions of `settings`; no global state. `cloud_provider="gcp"` yields today's behavior exactly.
- `GcsObjectStore` must raise nothing new relative to current code paths (let SDK exceptions propagate as before).
- The serve path (`webhook_inbound` → `serve_v1.handle_message_v1` → `paper_loader`) must download/serve the same bytes it does today.

### Tests
- **`tests/test_ports_storage.py`:** a `FakeStorageClient` (in-memory dict) satisfies the GCS wrapper; assert `GcsObjectStore.upload_bytes`/`download_bytes`/`exists` round-trip; assert `build_object_store(settings)` returns a `GcsObjectStore` for `cloud_provider="gcp"`, raises `NotImplementedError` for `"azure"`, `ValueError` for `"bogus"`; assert `isinstance`-by-Protocol via `typing.runtime_checkable` or duck-method presence.
- **`tests/test_ports_secrets.py`:** assert `build_secrets_provider(settings)` returns the GCP `SecretsProvider` for `"gcp"`, and that `get_secret` is callable (patch the Secret Manager client); assert the azure branch raises `NotImplementedError`.
- Full suite stays green (`pytest`).

## Part B (second agent)
Builds on Part A: adds the channel-agnostic core, the LLM/vision/embedding abstraction tests, and the non-destructive `gcs_*`→neutral rename with its own tests.

### Files
- **`app/channel.py` (new).** Neutral models: `MediaRef(media_id: str, mime_type: str, sha256: str | None)` and `InboundMessage(phone: str, message_id: str, text: str | None, media: MediaRef | None)`. A translator `to_inbound(wa_message) -> InboundMessage` (imports `WAMessage` only here — the WhatsApp adapter boundary).
- **`app/handler_core.py` (new).** `handle_inbound(session, inbound: InboundMessage, http_client, store) -> Reply`. For Phase 1 it bridges to the existing live handler (reconstruct the minimal WhatsApp-shaped object the current handler needs, or pass neutral fields through) and returns the same `Reply` the webhook path returns today. The module imports `app.retrieval` and reply types but **not** `app.whatsapp`. Document the WAMessage bridge as a temporary shim.
- **`migrations/007_neutral_names.sql` (new).** Guarded, reversible rename of the storage-key column to `object_key` on `papers`, `pending_papers`, `image_batch_items`, using the idempotent pattern already used in the repo (e.g. `DO $$ ... IF EXISTS column gcs_object THEN ALTER TABLE ... RENAME COLUMN gcs_object TO object_key; END IF; $$;`). No data copied or dropped. Add a header comment stating it is non-destructive and how to reverse it.
- **`app/db.py` (edit).** On `Paper`, `PendingPaper`, `ImageBatchItem`: rename the mapped attribute to `object_key` (physical column `object_key`) and add `gcs_object = synonym("object_key")` so existing code/tests using `gcs_object=`/`.gcs_object` keep working. Do not change other columns.
- **`app/config.py` (edit).** Add neutral prefix aliases (`media_object_prefix`, `contribution_object_prefix`, `serve_precompute_prefix` already neutral) via `AliasChoices` that keep the existing `*_gcs_prefix` env names working.

### Interfaces and behaviour
- `handle_inbound` returns byte-for-byte the same `Reply` for the same input as the current webhook path; it is invokable in a test by constructing an `InboundMessage` directly (no WhatsApp type needed by the caller).
- Reading or writing `paper.object_key` and `paper.gcs_object` must refer to the same underlying column/value.

### Tests
- **`tests/test_ports_ai.py`:** with the google-genai client patched (as in `tests/test_embeddings.py`), assert `build_structured_llm`/`build_vision_ocr`/`build_embedder` return the GCP adapters for `"gcp"`, that `Embedder.embed` returns a 768-length vector and `embed_batch` preserves order, and that the azure branch raises `NotImplementedError`.
- **`tests/test_channel_agnostic.py`:** assert `app.retrieval` and `app.handler_core` module source contain no `import app.whatsapp` / `from app.schemas import WA...`; construct an `InboundMessage` (not a `WAMessage`) and call `handle_inbound` with a `FakeStorageClient`-backed `ObjectStore` and a stubbed LLM/retrieval, asserting a `Reply` comes back — proving the core is invokable without WhatsApp types.
- **`tests/test_neutral_names.py`:** create a `Paper`/`PendingPaper`/`ImageBatchItem` via `object_key=...`, read back `.gcs_object`; create via `gcs_object=...`, read back `.object_key`; assert equality both directions (synonym bridge). Verify migration `007` applies idempotently on a fresh sqlite/pg test DB without error.
- Full suite stays green (`pytest`).

## Acceptance-criteria mapping (Phase 1)
- **AC2** (tests cover storage, LLM/vision/embedding, secrets/config abstractions) → `tests/test_ports_storage.py`, `tests/test_ports_secrets.py` (Part A) + `tests/test_ports_ai.py` (Part B). Check: `pytest tests/test_ports_*.py` passes.
- **AC5** (handler core + retrieval callable invokable without WhatsApp types) → `tests/test_channel_agnostic.py` (Part B). Check: that test passes; `handle_inbound` runs from a neutral `InboundMessage`.
- **AC1** (existing suite passes unchanged) → verified both parts. Check: full `pytest` green with no edits to existing test files.
- **AC4** (no new hardcoded project ids / plaintext secrets) → provider selection lives in `cloud_provider` config; new files add no literals. Check: `grep -rniE "(ummah|gen-lang-client|password\\s*=\\s*['\"])" app/ports.py app/providers app/channel.py app/handler_core.py` finds nothing. (Full AC4 is Phase 6.)
- **PRD item 1** (rename `gcs_*` via non-destructive migration) → `migrations/007_neutral_names.sql` + ORM synonyms (Part B). Check: `tests/test_neutral_names.py` passes and migration re-runs cleanly.

## Documentation sources
- https://fastapi.tiangolo.com/advanced/events/
- https://fastapi.tiangolo.com/deployment/concepts/
- https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/
- https://pypi.org/project/pydantic-settings/
- https://learn.microsoft.com/en-us/python/api/overview/azure/storage-blob-readme?view=azure-python
- https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme

## Out of scope for this phase
- Any `azure-*` adapter or dependency (Phases 2–5).
- Azure OpenAI/embeddings/OCR, pricing changes, re-embed or top-k harness (Phases 3–4).
- Bicep, deploy-script replacement, Graph importer (Phase 5).
- Migration/cutover plan, restore drill, docs rewrite, GCP code deletion (Phase 6).
- Rewriting `serve_v1` internals, migrating non-serve storage call sites, and remediating `apply_migrations.py`.

## Spec assumptions

Gaps found while writing this spec were resolved as follows (nobody was asked):

- The repository contains both a root-level tree (`app/`, `admin/`, `tests/`, `migrations/`, `scripts/`, `review/`, `cloud_ingest/`) and a `msa-paperbank/` mirror; the root-level tree is treated as canonical and all Phase 1 work targets it. Keeping the mirror in sync is out of scope.
- A new setting `cloud_provider: Literal["gcp","azure"] = "gcp"` selects adapters. Phase 1 implements only the GCP adapters; the factory raises `NotImplementedError("azure provider lands in a later phase")` for `"azure"` and must not import any `azure-*` package.
- The provider-neutral seams use `typing.Protocol` (structural, not ABCs) to match the "plain Python" constraint and let the existing concrete objects satisfy them without inheritance churn.
- Neutral names: the storage key column/attribute becomes `object_key` (was `gcs_object`); the bucket/container setting becomes `object_store_bucket` (was `gcs_bucket`); neutral prefix settings mirror `*_gcs_prefix` as `*_object_prefix`.
- To satisfy "existing pytest passes unchanged", the rename keeps the old Python names working as SQLAlchemy `synonym()`s (`gcs_object` → `object_key`) and keeps old env var names working via pydantic `AliasChoices`; the SQL migration renames the physical column with a guarded, reversible `ALTER ... RENAME COLUMN` (data-preserving = non-destructive).
- Phase 1 migrates only the serve-path and composition-root storage call sites (`app/main.py`, the four `retrieval.load_*`/`precompute_*` loaders, `pdfgen.upload_pdf`) to the `ObjectStore` seam. Call sites exercised directly by existing tests with a mock `gcs_client` (e.g. `intake`, `contributions`, `admin/*`) keep their current signatures and are migrated in the Azure-storage phase, so the suite stays green.
- The channel-agnostic core is established as a neutral `InboundMessage` model plus a `handle_inbound(...)` entrypoint. In Phase 1 it bridges internally to the existing live WhatsApp handler (behavior preserved); fully rewriting `serve_v1` to consume `InboundMessage` is out of scope for this run.
- The live path remains `serve_v1` (`serve_v1_enabled=True` by default); Phase 1 does not change routing behavior or copy.
- Python 3.12 (current Dockerfile base) is retained; it satisfies the 3.10+ floor every Azure SDK requires.
- `apply_migrations.py` currently contains a hardcoded Cloud SQL instance and a plaintext DB password (a pre-existing AC4 violation). Phase 1 does not touch it; its remediation is owned by the DB-connection-factory/secrets phase. Phase 1 must introduce no new hardcoded project ids or secrets.
- Model-tier naming (`model_flash`/`model_pro`) is kept as-is in Phase 1; mapping to Azure "deployment name" chat tiers is deferred to the AI-adapter phase.
- `cloud_provider` is passed through the config object; factory functions take `settings` and perform lazy, provider-scoped imports so GCP and Azure runtimes never need each other's SDKs installed.

## Implications

Second-order consequences found by an independent review of this spec. This section only adds to the spec; the locked PRD is unchanged.

### Additional acceptance criteria

S1. Running migration 007 twice in a row on a fresh DB, and once on a DB where one target table already has object_key, both complete without error and leave all three tables with exactly one of object_key/gcs_object as the physical column. _(data: Migration 007's guarded ALTER TABLE RENAME COLUMN can leave schema inconsistent if it partially applies against a pre-existing object_key column on only some tables)_

### Explicitly out of scope

- Removing the gcs_object/gcs_bucket synonyms and AliasChoices fallbacks is deferred to Phase 6 cutover; Phase 1 does not schedule their removal. _(maintenance)_

### Noted, no action

- Azure-branch behavior is verified only via the NotImplementedError path in Phase 1; no azure code exists yet to misconfigure. _(security)_
- The WAMessage shim in handler_core.py is a Phase 1 stopgap; its removal is not scheduled by any acceptance criterion in this run. _(maintenance)_
