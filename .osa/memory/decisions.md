# Decisions

Choices made on this project and why. One fact per line. Written by OSA from each run's record; safe to edit by hand.

- Accepted risky assumption: The OCR A/B gate pass threshold (e.g. accuracy within a tolerance of Gemini) is unspecified; a concrete threshold will be defined in the gate report for owner review. _(run 1535cf46, 2026-11-11)_
- Accepted risky assumption: The Azure region/tier and Postgres Flexible Server SKU are not specified; a cost-reasonable default matching data-residency norms will be chosen and parameterized in Bicep. _(run 1535cf46, 2026-11-11)_
- Accepted risky assumption: Work stays in the single existing repo with GCP and Azure impls coexisting behind interfaces until the final deletion step. _(run 1535cf46, 2026-11-11)_
- Accepted risky assumption: The chosen Azure chat model's structured-output/reasoning-budget features will be mapped to the nearest equivalent of Gemini's response_schema and thinking_budget=0. _(run 1535cf46, 2026-11-11)_
- Architecture: kept the planned architecture -- The deciding trade-off is lifecycle fit against the PRD's narrow scope, 10-item cap, and single-repo/delete-after-sign-off mandate — ports-and-adapters with one `cloud_provider` factory switch models exactly that lifecycle (GCP... _(run 1535cf46, 2026-11-11)_
- Spec decision: The authoritative codebase is the root-level tree (`app/`, `admin/`, `review/`, `cloud_ingest/`, `scripts/`, `migrations/001–006`, `tests/`, `deploy.ps1`, `Makefile`). The nested `msa-paperbank/` directory is a stale partial mirror and is NOT edited this phase. _(run 1535cf46, 2026-11-11)_
- Spec decision: Provider seams are defined as structural `typing.Protocol` classes (not ABCs), to match the "plain Python" constraint and avoid inheritance coupling. _(run 1535cf46, 2026-11-11)_
- Spec decision: Ports live in a new `app/ports.py`; provider adapters live in a new `app/providers/` package; a factory in `app/providers/__init__.py` selects the implementation by a new setting `cloud_provider: str = "gcp"` (default `gcp`). _(run 1535cf46, 2026-11-11)_
- Spec decision: Phase 1 is a pure refactor with GCP implementations only; no Azure SDK code, no network calls, no behavior change. Azure adapters arrive in Phase 3. _(run 1535cf46, 2026-11-11)_
- Spec decision: The GCP AI adapter is a thin wrapper that delegates to the existing `app.llm.*` and `app.embeddings.*` functions (lazy import, no logic duplication), preserving `thinking_budget=0`, temperatures, token caps, and token-count returns exactly. _(run 1535cf46, 2026-11-11)_
- Spec decision: The storage port IS fully rerouted this phase (it is the broadest coupling and Blob parity needs it later); the AI/secrets/DB ports are introduced with GCP adapters and factory, and existing internal Gemini/Cloud-SQL calls remain in place behind them until the... _(run 1535cf46, 2026-11-11)_
- Spec decision: The `gcs_object` DB column and the `gcs_bucket` setting keep their names this phase; the non-destructive rename to neutral identifiers is deferred to Phase 4. The storage port is provider-neutral regardless of these names. _(run 1535cf46, 2026-11-11)_
- Spec decision: Existing tests that patch now-wrapped provider internals (e.g. `@patch('admin.curate.storage.Client')`) may be minimally re-pointed at the new seam; no behavioral assertion is changed. This is treated as satisfying "existing pytest passes." _(run 1535cf46, 2026-11-11)_
- Out of scope: Teams custom-engine bot, Teams study companion, and Entra SSO for the review app (later runs; this phase only leaves clean seams). _(run 1535cf46, 2026-11-11)_
- Out of scope: Executing the data migration, re-ingest, webhook swap, or GCP teardown (planned/scripted only, gated on owner approval). _(run 1535cf46, 2026-11-11)_
- Out of scope: Modifying, destroying, or running ingest against any GCP prod resource (project 'ummah'). _(run 1535cf46, 2026-11-11)_
- Out of scope: Adding channels beyond WhatsApp; WhatsApp stays the only live channel this phase. _(run 1535cf46, 2026-11-11)_
- Out of scope: Switching away from FastAPI, SQLAlchemy 2.0, pydantic-settings, pgvector(HNSW)/pg_trgm, or the Vector(768) schema. _(run 1535cf46, 2026-11-11)_
