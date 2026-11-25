# Phase 2 — Channel-neutral core + reversible `gcs_*`→`object_key` rename

## Goal
Make the handler core channel-agnostic and the storage names provider-neutral without changing behaviour. Introduce an `InboundMessage` model and a `handle_inbound` entrypoint plus a retrieval callable that **import no WhatsApp-specific types**; demote WhatsApp to a thin adapter that maps its webhook payload to `InboundMessage` and maps replies back. Separately, rename the `gcs_*` DB columns and settings to neutral `object_key`-style names via a **reversible migration using SQLAlchemy synonyms**, keeping the **pre-existing env variable names resolving unchanged**. The existing pytest suite keeps passing (minimal re-pointing allowed). Satisfies AC 4, 5.

## Scope
In: a new `app/inbound.py` (the `InboundMessage`/`OutboundReply` channel-neutral models + `handle_inbound`), a new `app/channels/whatsapp.py` thin adapter (WhatsApp payload ↔ `InboundMessage`/reply), a clean retrieval callable in `app/retrieval.py` that takes a plain query and imports no WhatsApp types, the `main.py` webhook rewired to go WhatsApp-adapter → `handle_inbound`, a new numbered SQL migration renaming `gcs_object`/`served_object`/the `*_gcs_*` settings, SQLAlchemy `synonym()` mappings so old attribute names keep working, `AliasChoices` so old env names keep resolving, plus unit/integration tests and a short doc. Out: filesystem/MinIO object store, signed URLs, file/env secrets provider, plain-Postgres engine, tool-endpoint auth, removing hardcoded secrets (Phase 3); local embedder / re-embed / parity (Phase 4); Docker/Compose (Phase 5); any GCP teardown (Phase 6); any Azure work (never). No new runtime dependency; no retrieval behaviour change.

Rename rule used throughout: DB column `gcs_object` → `object_key` and `served_object` → `served_object_key`; ORM keeps the old Python attribute via `synonym("object_key")` so `paper.gcs_object` still reads/writes the renamed column. Setting field `gcs_bucket` → `object_store_bucket`, `media_gcs_prefix` → `media_prefix`, `contribution_gcs_prefix` → `contribution_prefix`, each carrying `AliasChoices("<new_env>", "<old_env>")` so `GCS_BUCKET`/`MEDIA_GCS_PREFIX`/`CONTRIBUTION_GCS_PREFIX` still resolve. No raw SQL string literals referencing the old column names are left unmigrated.

## Part A (first agent)

### Files
- `app/inbound.py` (new) — `InboundMessage`, `OutboundReply` union, and `handle_inbound`.
- `app/channels/__init__.py`, `app/channels/whatsapp.py` (new) — the WhatsApp thin adapter.
- `app/retrieval.py` (edit) — add/confirm a channel-neutral retrieval callable `answer_query(session, query, *, prefer_courses=None) -> RetrievalResult` importing no WhatsApp types.
- `app/main.py` (edit) — webhook builds `InboundMessage` via the WhatsApp adapter, calls `handle_inbound`, maps the `OutboundReply` back through the adapter to `whatsapp.send_reply`.
- `tests/test_inbound.py` (new) — unit tests for the neutral core + adapter round-trip.

### Interfaces and behaviour
- `app/inbound.py`:
  - `InboundMessage` (pydantic `BaseModel`): `channel: str`, `sender: str`, `message_id: str`, `kind: Literal["text","image","other"]`, `text: str | None`, `media_id: str | None`, `raw: dict | None` (opaque channel passthrough). It carries **no** `WAMessage`/`WAImage` fields or imports.
  - `OutboundReply`: reuse the existing `Reply`/`TextReply`/`DocumentReply` from `app.schemas` (these are already channel-neutral — they contain no WhatsApp wire types); `handle_inbound` returns one of them. Do **not** move them into `inbound.py`; just re-export the alias `OutboundReply = Reply` for callers.
  - `handle_inbound(session, msg: InboundMessage, http_client, store: ObjectStore) -> Reply` contains the routing/intent/retrieval logic currently in `app/pipeline.handle_message` and the image-intake dispatch currently in its image branch, expressed against `InboundMessage` only. It imports `app.retrieval`, `app.intake`, `app.profile`, `app.llm`, `app.pricing` — never `app.whatsapp`/`app.schemas` WhatsApp wire types. Behaviour (idempotency log, opt-out, rate/cost/token guards, routing, course guard, semantic fallback, reply bodies) is preserved verbatim; only the input type changes.
- `app/channels/whatsapp.py`:
  - `to_inbound(wa: WAMessage) -> InboundMessage` maps `from_`→`sender`, `id`→`message_id`, `type`→`kind` (`"text"`/`"image"` pass through, everything else → `"other"`), `text.body`→`text`, `image.id`→`media_id`, and stashes the original under `raw`.
  - `from_reply(reply: Reply) -> Reply` is identity this phase (replies are already neutral); it exists so the seam is named and Phase 3+ can diverge. The media download/send still lives in `app.whatsapp`; the adapter only translates the inbound envelope and selects the paper loader.
- `app/retrieval.py` — expose `answer_query(session, query: str, *, prefer_courses: list[str] | None = None) -> RetrievalResult` wrapping the existing `find_paper` / `find_paper_by_semantic_query` logic so the future tool endpoint (Phase 3) and `handle_inbound` share one callable. It imports no WhatsApp types. Existing `find_paper*` functions stay; `answer_query` composes them. (If a clean extraction is not yet warranted, `handle_inbound` may call the existing `retrieval.find_paper*` directly — but the callable must exist and be WhatsApp-type-free for AC 4.)
- `app/main.py` — in `webhook_inbound`, for each WA message: `inbound = whatsapp_channel.to_inbound(msg)`, `reply = handle_inbound(session, inbound, request.app.state.http, request.app.state.store)`. Keep the existing `serve_v1_enabled` switch if still present, but route both branches’ inbound construction through the adapter; the paper loader keeps using `request.app.state.store`. No behaviour change to send-side.

### Tests (`tests/test_inbound.py`)
- `to_inbound` maps a text `WAMessage` and an image `WAMessage` to the correct `InboundMessage` (`kind`, `sender`, `media_id`), and maps an unsupported type to `kind="other"`.
- A static scan asserts `app/inbound.py` and the retrieval callable import no WhatsApp types: `import ast; "whatsapp" not in {imported module names}` for `app/inbound.py`, and `answer_query`’s module does not reference `WAMessage`/`WAImage`. (Mechanical AC-4 check.)
- `handle_inbound` with a text `InboundMessage` for a known greeting / an unknown course / a found paper returns the same reply bodies the old `pipeline.handle_message` returned for the equivalent `WAMessage` (behaviour-parity, driven against `db_session` with `llm.route` patched).
- `isinstance(handle_inbound(...), Reply)` and no network call is made (http client + store are mocks/fakes).

## Part B (second agent)

### Files
- `migrations/007_object_key_rename.sql` (new) — reversible column rename.
- `app/db.py` (edit) — rename the `Mapped` columns to `object_key`/`served_object_key` and add `synonym()` so old attribute names keep working.
- `app/config.py` (edit) — rename the three settings fields and attach `AliasChoices` carrying the old env names.
- Call-site touch-ups where a raw SQL string names the old column (`app/build_served_pdfs.py` `MIGRATE`/queries, any `text("... gcs_object ...")`), re-pointed to the new column name.
- `tests/test_object_key_rename.py` (new) — synonym + env-alias + migration-reversibility tests.
- `docs/object_key_rename.md` (new) — what was renamed, the synonyms, the env back-compat, and how to roll back.

### Interfaces and behaviour
- `migrations/007_object_key_rename.sql` — plain numbered SQL applied by `apply_migrations.py` (there is **no Alembic** in this project; migrations are numbered SQL files `001`–`006`, and this adds `007`). Forward: `ALTER TABLE papers RENAME COLUMN gcs_object TO object_key;` `ALTER TABLE papers RENAME COLUMN served_object TO served_object_key;` `ALTER TABLE pending_papers RENAME COLUMN gcs_object TO object_key;` `ALTER TABLE image_batch_items RENAME COLUMN gcs_object TO object_key;` Each wrapped so re-apply is safe (guard with `IF EXISTS` on the old name / `information_schema` check, mirroring the existing migrations’ idempotency style). Include a commented, exact inverse (`RENAME COLUMN object_key TO gcs_object`, …) in the file header so the rename is demonstrably reversible. Register `007_object_key_rename.sql` in `apply_migrations.py`’s `FILES` list. (Do **not** edit the hardcoded credentials in `apply_migrations.py`; that is Phase 3. Do not run the migration against GCP prod.)
- `app/db.py` — rename the three `gcs_object: Mapped[str]` columns to `object_key: Mapped[str]` and `served_object` to `served_object_key`, and add on each model a backward-compat synonym: `gcs_object = synonym("object_key")` (and `served_object = synonym("served_object_key")` on `Paper`). All existing reads/writes of `.gcs_object`/`.served_object` across `app/`, `admin/`, `review/`, `scripts/`, `cloud_ingest/`, and tests keep working unchanged through the synonym. The `TEST_DB_URL` branch, `SessionLocal`, `Base`, and pool settings stay byte-for-byte; `conftest`’s `Base.metadata.create_all` now creates the new column names, and the synonyms mean no test query string needs editing except raw-SQL literals.
- `app/config.py` — rename `gcs_bucket`→`object_store_bucket`, `media_gcs_prefix`→`media_prefix`, `contribution_gcs_prefix`→`contribution_prefix`. Each field gets `Field(validation_alias=AliasChoices("OBJECT_STORE_BUCKET", "GCS_BUCKET"))` (and the equivalent for the two prefixes) so both the new and the pre-existing env var names resolve; `case_sensitive=False` is preserved. Update in-repo references to `settings.gcs_bucket`/`settings.media_gcs_prefix`/`settings.contribution_gcs_prefix` to the new attribute names (the GCP storage adapter’s `from_settings` reads `settings.object_store_bucket`). No other setting changes; the secret-manager bootstrap is untouched.
- Raw-SQL call sites — `app/build_served_pdfs.py`’s `MIGRATE` DDL and any `text("… gcs_object … / served_object …")` query are updated to the new column names (the ORM synonym does not cover raw SQL strings). After this, no raw SQL in the repo references the old column names.

### Tests
- `tests/test_object_key_rename.py`:
  - ORM synonym: with the sqlite test DB, `Paper(object_key="k")` is readable as `paper.gcs_object == "k"`, and setting `paper.gcs_object = "k2"` updates `object_key` (same for `pending_papers`, `image_batch_items`, and `served_object`/`served_object_key`).
  - Env back-compat: constructing `Settings` with only the **old** env names set (`GCS_BUCKET`, `MEDIA_GCS_PREFIX`, `CONTRIBUTION_GCS_PREFIX`) populates `object_store_bucket`/`media_prefix`/`contribution_prefix`; constructing with the new names also works; the new name wins if both are set.
  - Migration shape: parse `migrations/007_object_key_rename.sql` and assert it renames all four columns forward and documents the exact inverse (string assertions; no DB connection). Assert `007` is registered in `apply_migrations.py`’s `FILES`.
  - No network call in any of the above.
- `tests/test_curate_promote.py` and the existing suite keep passing unchanged (the synonyms and env aliases are what make this true); only raw-SQL-literal tests, if any, are re-pointed.
- `docs/object_key_rename.md` documents the renamed columns and settings, the `synonym()`/`AliasChoices` back-compat, that migration `007` is reversible (with the inverse SQL), and that it must not be run against GCP prod. It must not instruct running any fetched code and must not edit the PRD.

## Acceptance-criteria mapping
- **AC 4 — `handle_inbound` and the retrieval callable import no WhatsApp types; WhatsApp is a thin adapter:** `app/inbound.py` defines `InboundMessage` + `handle_inbound`; `app/channels/whatsapp.py` translates the Meta webhook payload to/from the neutral envelope; `app/retrieval.answer_query` is WhatsApp-type-free. Check: `tests/test_inbound.py`’s AST scan asserts no WhatsApp import in the core, plus behaviour-parity tests.
- **AC 5 — reversible `gcs_*` rename via SQLAlchemy synonyms, old env names still resolve:** migration `007` renames the columns (with a documented inverse), `app/db.py` carries `synonym()` for every old attribute, `app/config.py` carries `AliasChoices` for every old env name. Check: `tests/test_object_key_rename.py` asserts synonym read/write, old+new env resolution, and the migration’s forward/inverse shape.
- **AC 1 (carried) — existing pytest passes unchanged:** synonyms + env aliases keep every old attribute/env access working; only raw-SQL literals and the webhook’s inbound construction change; no behavioural assertion altered. Check: `pytest` passes.
- **AC 2 (carried) — no network in unit tests:** adapter + core tests use fakes/mocks; the migration test parses SQL text without a DB. Check: suite runs with no outbound network.

## Documentation sources
- SQLAlchemy 2.0 — `synonym()` / mapping column aliases: https://docs.sqlalchemy.org/en/20/orm/mapped_attributes.html
- SQLAlchemy 2.0 Documentation (en/20 index): https://docs.sqlalchemy.org/en/20/
- Settings Management — Pydantic `AliasChoices` / env aliases: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/
- FastAPI Advanced — Lifespan Events: https://fastapi.tiangolo.com/advanced/events/
- PostgreSQL — `ALTER TABLE ... RENAME COLUMN`: https://www.postgresql.org/docs/current/sql-altertable.html

## Out of scope for this phase
- Filesystem/MinIO `ObjectStore`, signed/expiring download URLs, file/env secrets provider, plain-Postgres engine factory, tool-endpoint auth, removing hardcoded secrets in `apply_migrations.py`/scripts/Dockerfile (Phase 3).
- Local CPU embedder, re-embed job, parity harness (Phase 4).
- Dockerfile/Compose/health checks/backup/RUNBOOK/reverse proxy (Phase 5).
- Any cutover tooling or GCP teardown; any modification to GCP prod (`ummah`); any Azure work.
- The authed single-call MCP/REST tool endpoint itself (Phase 3); this phase only leaves the clean `answer_query` callable it will wrap.
- Changing the daily cost-cap breaker.

## Spec assumptions

Gaps found while writing this spec were resolved as follows (nobody was asked):

- **Migrations are plain numbered SQL files (`001`–`006`) applied by `apply_migrations.py`; there is no Alembic.** The reversible rename is therefore a new numbered SQL migration (`007_object_key_rename.sql`) for the column rename, with the reversibility expressed as a documented exact-inverse `RENAME` plus the ORM `synonym()` layer — not an Alembic `op.alter_column`. (This overrides the earlier plan assumption that named Alembic.)
- The neutral names are `object_key` (columns), `served_object_key`, `object_store_bucket`/`media_prefix`/`contribution_prefix` (settings). Exact spellings may be adjusted by the executor if a cleaner neutral name is obvious, provided every old attribute keeps a `synonym()` and every old env name keeps an `AliasChoices` entry.
- `Reply`/`TextReply`/`DocumentReply` in `app/schemas.py` are already channel-neutral (no WhatsApp wire fields), so they are reused as the outbound type rather than re-modelled; only the inbound envelope and the webhook wiring are new.
- `app/pipeline.py`’s `handle_message` is the body migrated into `handle_inbound`; `pipeline.handle_message` may remain as a deprecated thin shim that builds an `InboundMessage` and delegates, or be removed if no longer referenced, provided the existing `tests/test_pipeline.py` still passes (re-pointed minimally if needed).
- The WhatsApp send-side (`app.whatsapp.send_reply`, media download) is unchanged this phase; only the inbound translation is adapter-ised. Channel-neutral *outbound* delivery is not required by AC 4 and is deferred.
- The authoritative codebase is the root-level tree; the nested `msa-paperbank/` mirror is not edited. The root-level `PHASE_*_SPEC.md`/`MASTER_PRD.md` files belong to the original product build and are **not** this run’s artifacts — do not edit or follow them.

## Implications

Second-order consequences found by an independent review of this spec. This section only adds to the spec; the locked PRD is unchanged.

### Additional acceptance criteria

S1. The `synonym()` mappings must cover **every** old attribute actually read or written in the repo (`gcs_object` on `papers`/`pending_papers`/`image_batch_items`, `served_object` on `papers`); a grep for `.gcs_object`/`.served_object` after the change must show every remaining use resolving through a synonym, with zero references to a now-nonexistent `Mapped` column. _(maintenance)_

S2. Raw SQL is not covered by ORM synonyms: every `text("… gcs_object …")`/`served_object` literal (notably `app/build_served_pdfs.py`’s `MIGRATE`) must be updated in the same commit as the migration, or the renamed DB will not match the query. A repo grep for the old column names inside SQL string literals must come back empty. _(correctness)_

### Carried-over Phase 1 cleanup (fix opportunistically while rewiring the inbound path)

- Phase 1 changed `app/intake.py`’s `handle_image`/`sweep_and_seal`/`sweep_and_seal_single` and `app/contributions.*` to take an `ObjectStore`, but two callers still pass a raw `storage.Client`: `app/pipeline.py` (`intake.sweep_and_seal(session, gcs_client)` and `intake.handle_image(session, http_client, gcs_client, msg)`) and `admin/batches.py:52` (`sweep_and_seal_single(session, gcs_client, …)`). These are latent `AttributeError`s on `store.download_bytes`/`upload_bytes` whenever the non-`serve_v1` fallback path or the `batches` CLI runs; the existing tests pass only because they inject `MagicMock`/`None`. Phase 2 rewires the webhook through `handle_inbound(..., request.app.state.store)`, which is the natural point to pass the real `ObjectStore` and to repoint `admin/batches.py` to `get_object_store(settings)`. _(correctness — flagged by the Phase 1 reviewer; not a Phase 1 blocker because the live `serve_v1` path is unaffected and the suite stays green.)_

### Noted, no action

- Renaming settings fields changes the attribute name used in business logic; because access is always through `app.config.settings`, the blast radius is a mechanical rename plus the `AliasChoices` back-compat, with no behaviour change on either old or new env names. _(data)_
