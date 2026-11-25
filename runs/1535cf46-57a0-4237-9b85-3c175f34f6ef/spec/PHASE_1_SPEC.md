# Phase 1 — Provider-neutral seams (GCP behind interfaces)

## Goal
Introduce provider-neutral ports for storage, AI (LLM/vision + embeddings), secrets/config, and the database engine, with the existing GCP implementations moved behind them and selected by a factory. Reroute all runtime storage call sites through the `ObjectStore` port. This is a pure refactor: **no Azure code, no network calls, no behaviour change.** The existing pytest suite passes; new unit tests cover each abstraction.

## Scope
- In: `app/ports.py`, `app/providers/` (adapters + factory), rerouting storage in `app/`, `admin/`, `review/`, `cloud_ingest/`; secrets-loader and DB-engine seams; new tests; a README "Provider seams" section.
- Out: see "Out of scope" below.
- A new setting `cloud_provider: str = "gcp"` is added to `app/config.py` and read by the factory.

## Part A (first agent)
Delivers the two most pervasive/core seams — **storage (fully rerouted)** and **AI (ports + thin GCP adapters)** — plus the ports module and factory skeleton.

### Files
- `app/ports.py` (new) — all Protocols and neutral types (shared by both parts):
  - `@dataclass(frozen=True) class LlmPart` with fields `text: str | None = None`, `image_bytes: bytes | None = None`, `mime_type: str | None = None`; helpers `LlmPart.of_text(s)` and `LlmPart.of_image(b, mime)`.
  - `@dataclass class JsonCompletion` with `text: str`, `input_tokens: int = 0`, `output_tokens: int = 0`.
  - `class ObjectStore(Protocol)`: `download_bytes(self, key: str) -> bytes`; `upload_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None`; `exists(self, key: str) -> bool`.
  - `class StructuredLLM(Protocol)`: `generate_json(self, *, model: str, system: str, parts: list[LlmPart], schema: type, max_output_tokens: int, temperature: float = 0.0, thinking_budget: int = 0) -> JsonCompletion`.
  - `class Embedder(Protocol)`: `embed(self, text: str, *, kind: str) -> list[float]` (kind in `{"document","query"}`); `embed_many(self, texts: list[str], *, kind: str, concurrency: int | None = None) -> list[list[float]]`.
  - Declare `SecretsProvider` and `make_engine` contracts too (implemented in Part B) so the module is complete.
- `app/providers/__init__.py` (new) — factory: `get_object_store(settings) -> ObjectStore`, `get_structured_llm(settings) -> StructuredLLM`, `get_embedder(settings) -> Embedder` (Part B adds `get_secrets_provider`, `get_engine`). Each dispatches on `settings.cloud_provider`; only the `"gcp"` branch exists now, and an unknown value raises `ValueError`.
- `app/providers/gcp_storage.py` (new) — `GcsObjectStore`: constructor `(client, bucket_name)`; classmethod `from_settings(settings)` builds `storage.Client(project=settings.gcp_project)` and uses `settings.gcs_bucket`; methods map to `bucket.blob(key).download_as_bytes()` / `.upload_from_string(data, content_type=content_type)` / `.exists()`.
- `app/providers/gcp_ai.py` (new) — `GeminiStructuredLLM` and `GeminiEmbedder`, thin wrappers that **lazily import and delegate** to existing `app.llm` / `app.embeddings` logic (no logic duplication). `GeminiStructuredLLM.generate_json` translates `list[LlmPart]` → `list[google.genai.types.Part]` and calls the existing Gemini `client`, returning `JsonCompletion(text, input_tokens, output_tokens)` from `usage_metadata` (0 if absent). `GeminiEmbedder` delegates to `app.embeddings.embed_one`/`embed_query`/`embed_many` mapping `kind`→task type.
- Refactor `app/llm.py`: change `call_pro_vision(parts: list[LlmPart], system_instruction, response_schema)` to accept neutral parts (translate internally); keep `route`, `validate_contribution_image`, `read_masthead`, `probe_page_boundary` behaviour identical. Preserve all prompts, temperatures, `max_output_tokens`, and `thinking_budget=0`.
- Refactor `app/ocr.py`: build `list[LlmPart]` (via `LlmPart.of_image(b, "image/png")`) instead of `types.Part`, and call `call_pro_vision` with them.
- Reroute storage in `app/`: `app/main.py` lifespan sets `app.state.store = get_object_store(settings)` (remove `app.state.gcs`); `app/retrieval.py`, `app/pdfgen.py`, `app/intake.py`, `app/build_served_pdfs.py` change signatures from `(gcs_client: storage.Client, bucket_name: str)` to `(store: ObjectStore)` and use `store.download_bytes`/`upload_bytes`/`exists`. Update their callers within `app/`.
- Add `cloud_provider: str = "gcp"` to `app/config.py` `Settings`.

### Interfaces and behaviour
- Behaviour is byte-for-byte unchanged: the Gemini adapter produces the same requests as today; the storage adapter performs the same blob operations. Only the plumbing (how objects are obtained and passed) changes.
- Call sites receive a port, never a concrete SDK client. `app.state.store` is the single app-scoped `ObjectStore`.

### Tests
- `tests/test_ports_storage.py` (new): an in-memory fake implementing `ObjectStore` round-trips `upload_bytes`→`download_bytes`→`exists`; `GcsObjectStore` with a mocked `storage.Client` asserts `download_bytes`/`upload_bytes(content_type=...)`/`exists` translate to the expected blob calls, and that a retrieval loader (`app.retrieval.load_pdf_bytes`) works against the fake store.
- `tests/test_ai_seam.py` (new): `get_structured_llm(settings)` returns a `StructuredLLM`; with `app.llm`'s Gemini `client` monkeypatched to a stub returning canned JSON + usage, `generate_json` returns a `JsonCompletion` carrying the stub's token counts, and `thinking_budget`/`temperature`/`max_output_tokens` reach the stub unchanged; `GeminiEmbedder.embed` delegates and returns a 768-length vector (embedder monkeypatched).
- Keep `tests/test_embeddings.py` green by pointing its monkeypatch at the embedder seam.

## Part B (second agent)
Delivers the **dependent** seams (secrets/config, DB engine), reroutes the remaining storage call sites, and adds edge/error tests, an integration test, and docs. Builds on Part A's commits.

### Files
- `app/providers/gcp_secrets.py` (new) — `GcpSecretsProvider` wrapping `google.cloud.secretmanager`: `resolve(self, ref: str) -> str` (accesses the secret version named by `ref`); classmethod `from_env()`.
- `app/providers/gcp_db.py` (new) — move the Cloud SQL `getconn()` (connector + `pg8000`) here; expose `make_engine(settings)` returning a SQLAlchemy `Engine` (connector-creator path), and a `dispose()` that closes the connector. Preserve pool settings (`pool_size=2, max_overflow=2, pool_pre_ping=True, pool_recycle=1800`).
- `app/ports.py` — ensure `SecretsProvider(Protocol)` (`resolve(ref) -> str`) is present (declared in Part A, finalised here).
- `app/providers/__init__.py` — add `get_secrets_provider(settings_or_env) -> SecretsProvider` and `get_engine(settings) -> Engine`, gated on `cloud_provider`.
- Refactor `app/config.py`: `load_settings_with_secret_manager()` resolves each `*_FROM_SECRET` via `get_secrets_provider(...)` instead of importing `secretmanager` directly (the GCP import now lives only in `gcp_secrets.py`).
- Refactor `app/db.py`: build the engine via `get_engine(settings)` when `DATABASE_URL_TEST` is unset (otherwise keep the sqlite/`DATABASE_URL_TEST` path); `dispose()` delegates to the provider. ORM models and `Vector(768)` are unchanged.
- Reroute remaining storage call sites to the `ObjectStore` port: `review/main.py`, `cloud_ingest/main.py`, `admin/curate.py`, `admin/upload.py`, `admin/batches.py`, `admin/health.py`.

### Interfaces and behaviour
- Config loading and DB engine creation are behaviourally identical; only the construction path is seamed. No secret values are logged or committed.
- After this phase, direct `google.cloud.storage` / `secretmanager` / Cloud SQL connector usage exists **only** inside `app/providers/gcp_*.py` (Gemini genai internals still live in `app/llm.py`/`app/embeddings.py`, to be removed in Phase 8).

### Tests
- `tests/test_secrets_provider.py` (new): a fake `SecretsProvider` resolves a `*_FROM_SECRET` env mapping through the loader; importing `app.config` does not require `google.cloud.secretmanager` (patched/absent) when `GCP_LOAD_FROM_SECRETS` is unset.
- `tests/test_db_factory.py` (new): `make_engine`/`get_engine` returns an `Engine` for the `DATABASE_URL_TEST` path; the Cloud SQL connector path is constructed lazily (not at import) and is selected only when `DATABASE_URL_TEST` is unset.
- `tests/test_storage_edges.py` (new): `ObjectStore` error semantics — `exists` returns `False` for a missing key, `download_bytes` on a missing key propagates the adapter error; an upload with an explicit `content_type` is forwarded.
- Integration: an existing retrieval/pipeline test passes end-to-end through the store seam (add/adjust one test to assert the serve path uses `app.state.store`); update `tests/test_curate_promote.py` to patch the store seam instead of `admin.curate.storage.Client`.
- Full-suite check: `pytest` is green (sqlite fallback, offline).

### Docs
- Add a "Provider seams" section to `README.md`: the ports in `app/ports.py`, the adapters in `app/providers/`, the `cloud_provider` setting and factory, and how an Azure provider plugs in later by implementing the same Protocols. No secrets, no cloud commands, no instructions to run anything against a live cloud.

## Acceptance-criteria mapping
| AC | Phase | Phase-1 concrete check |
|----|-------|------------------------|
| 1 — existing pytest passes against the seamed config | **1** | `pytest` green (sqlite fallback) after the refactor, incl. re-pointed internal-patch tests. |
| 2 — tests cover storage, LLM/vision/embedding, secrets/config abstractions | **1** | `test_ports_storage.py`, `test_ai_seam.py`, `test_secrets_provider.py` (+ `test_db_factory.py`, `test_storage_edges.py`) pass. |
| 5 — handler core/retrieval callable invocable without WhatsApp types | 2 | n/a (Phase 2). |
| 6 — 768-dim Azure embedding; column/HNSW unchanged | 3 | n/a. |
| 10 — cost-cap breaker triggers under new pricing | 3 | n/a. |
| 4 — no hardcoded project ids / plaintext secrets | 4 | n/a. |
| 7 — before/after top-k parity recorded | 5 | n/a. |
| 8 — OCR A/B gate report with per-sample verdict | 6 | n/a. |
| 9 — `az deployment` Bicep provisions ACA/Jobs/ACR/Postgres | 7 | n/a. |
| 11 — README/RUNBOOK/LAUNCH Azure + restore drill | 7 | n/a. |
| 3 — no google/vertex/cloud-sql imports in final codebase | 8 | n/a. |

## Documentation sources
- Azure Storage Blobs client library for Python (shapes the `ObjectStore` surface): https://learn.microsoft.com/en-us/python/api/overview/azure/storage-blob-readme?view=azure-python
- Azure Identity client library for Python (DefaultAzureCredential, for later adapters): https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme
- Settings Management — Pydantic (settings_customise_sources / AzureKeyVaultSettingsSource, shapes the secrets seam): https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/
- How to use structured outputs with Azure OpenAI (shapes the `StructuredLLM` port): https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs
- Generate embeddings with Azure OpenAI — `dimensions` param (shapes the `Embedder` port): https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/embeddings
- SQLAlchemy 2.0 Intro / Installation (engine factory, sync 2.0 style): https://docs.sqlalchemy.org/en/20/intro.html#installation
- FastAPI — Events: startup and shutdown (lifespan wiring of `app.state.store`): https://fastapi.tiangolo.com/advanced/events/

## Out of scope for this phase
- Any Azure SDK code or configuration; adding `azure-*` dependencies.
- The channel-agnostic handler core / retrieval callable refactor (Phase 2).
- Renaming `gcs_*` identifiers/columns to neutral names (Phase 4); the column/setting names stay as-is.
- Updating `pricing.py`/config for new models and the cost-cap test (Phase 3).
- Bicep/hosting, deploy-script replacement, Graph importer, re-embed/parity, OCR A/B gate, migration/cutover plan, restore drill (Phases 5–7).
- Removing Google imports / deps (Phase 8).
- Editing the stale `msa-paperbank/` mirror, `scripts/*` one-offs, or touching any GCP prod resource (project `ummah`).

## Spec assumptions

Gaps found while writing this spec were resolved as follows (nobody was asked):

- The authoritative codebase is the root-level tree (`app/`, `admin/`, `review/`, `cloud_ingest/`, `scripts/`, `migrations/001–006`, `tests/`, `deploy.ps1`, `Makefile`). The nested `msa-paperbank/` directory is a stale partial mirror and is NOT edited this phase.
- Provider seams are defined as structural `typing.Protocol` classes (not ABCs), to match the "plain Python" constraint and avoid inheritance coupling.
- Ports live in a new `app/ports.py`; provider adapters live in a new `app/providers/` package; a factory in `app/providers/__init__.py` selects the implementation by a new setting `cloud_provider: str = "gcp"` (default `gcp`).
- Phase 1 is a pure refactor with GCP implementations only; no Azure SDK code, no network calls, no behavior change. Azure adapters arrive in Phase 3.
- The GCP AI adapter is a thin wrapper that delegates to the existing `app.llm.*` and `app.embeddings.*` functions (lazy import, no logic duplication), preserving `thinking_budget=0`, temperatures, token caps, and token-count returns exactly.
- The storage port IS fully rerouted this phase (it is the broadest coupling and Blob parity needs it later); the AI/secrets/DB ports are introduced with GCP adapters and factory, and existing internal Gemini/Cloud-SQL calls remain in place behind them until the final deletion phase.
- The `gcs_object` DB column and the `gcs_bucket` setting keep their names this phase; the non-destructive rename to neutral identifiers is deferred to Phase 4. The storage port is provider-neutral regardless of these names.
- Existing tests that patch now-wrapped provider internals (e.g. `@patch('admin.curate.storage.Client')`) may be minimally re-pointed at the new seam; no behavioral assertion is changed. This is treated as satisfying "existing pytest passes."
- SQLAlchemy stays synchronous (current `pg8000`/Cloud SQL connector engine); no async migration this phase. The `DATABASE_URL_TEST` sqlite fallback and `tests/conftest.py` env bootstrap are preserved.
- `LlmPart` (neutral) supports a text variant and an inline-image variant (`bytes` + `mime_type`) to cover both the text router and the vision/OCR paths; the GCP adapter translates `LlmPart` into `google.genai.types.Part`.
- `call_pro_vision`'s parameter type changes from `list[google.genai.types.Part]` to `list[LlmPart]`; its one runtime caller (`app/ocr.py`) and relevant tests are updated to build neutral parts.
- All Phase 1 tests run offline against fakes/mocks; no cloud credentials, Key Vault, or live model calls are required to pass the suite.

## Implications

Second-order consequences found by an independent review of this spec. This section only adds to the spec; the locked PRD is unchanged.

### Additional acceptance criteria

S1. ObjectStore.download_bytes() raises one provider-neutral exception type (e.g. a module-level ObjectNotFoundError in app.ports) on a missing key, not a raw SDK exception; test_storage_edges.py asserts this same type from both the fake store and GcsObjectStore. _(maintenance: The ObjectStore error contract is left as 'the adapter error propagates' with no single exception type specified. GCP raises google.api_core-style exceptions; the Azure adapter arriving in Phase 3 will raise a different azure.core exception for the same missing-key case, so any later caller that catches one type silently breaks on the other provider.)_
S2. Each repointed test (incl. test_curate_promote.py) asserts the ObjectStore mock was actually called with expected args/call-count, not just that no exception was raised, so it fails if the call site reverts to direct SDK use. _(maintenance: Part B repoints tests like test_curate_promote.py from patching admin.curate.storage.Client to patching the new ObjectStore seam. If the repointed test only checks that the call completes without error, it will keep passing even if a future edit reverts the call site to direct SDK usage, silently losing the regression guard the original patch provided.)_

### Noted, no action

- Lazy per-call imports in gcp_ai.py add negligible overhead (module already cached); acceptable for this phase. _(performance)_
