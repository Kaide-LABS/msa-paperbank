# Project context — msa-paperbank GCP→Azure migration (Phase A)

## What this project is
`msa-paperbank` is a ~6k-LOC Python FastAPI bot that serves PAU past exam papers to students over WhatsApp. It routes a message's intent, OCRs scanned papers, embeds and retrieves them from Postgres+pgvector, and returns a PDF. Today it is tightly coupled to Google Cloud / Vertex AI. This project rebuilds the cloud plumbing to run entirely on Microsoft Azure so the bot can be handed to a school on a Microsoft 365 tenant, with the GCP and Azure stacks running side by side behind swappable adapters until an explicit owner-approved cutover. WhatsApp stays the only live channel; retrieval behaviour must not regress.

## Stack and why
- **Python 3 + FastAPI 0.120.x / Uvicorn / Gunicorn** — the existing runtime; locked by the PRD (no framework switch). `lifespan` context manager already in use for startup/shutdown.
- **SQLAlchemy 2.0 (sync) + pgvector `Vector(768)` + pg_trgm** — existing declarative models; locked. HNSW cosine index unchanged.
- **pydantic-settings 2.x** — existing config style; the Azure secrets path will later use its built-in `AzureKeyVaultSettingsSource`.
- **Current GCP deps being seamed off:** `google-genai` (Vertex, Gemini flash/pro vision + `gemini-embedding-001` at 768 dims), `google-cloud-storage`, `cloud-sql-python-connector`+`pg8000`, `google-cloud-secret-manager`, Google Drive import.
- **Azure targets (later phases, research-selected):** Azure OpenAI / Microsoft Foundry v1 API chat+vision with strict JSON structured outputs; `text-embedding-3-large`/`-small` with `dimensions=768`; Azure Blob (`azure-storage-blob`); Key Vault + user-assigned managed identity (`azure-identity`); Azure Database for PostgreSQL Flexible Server (pgvector/pg_trgm allow-listed via `azure.extensions`); Azure Container Apps + Jobs + ACR via parameterized Bicep; Microsoft Graph (`msgraph-sdk`) importer; optional Azure AI Document Intelligence `prebuilt-read` for the OCR A/B gate.

## Repo layout (authoritative root tree)
- `app/` — runtime: `main.py` (FastAPI, webhook), `config.py` (pydantic-settings + Secret Manager), `db.py` (engine + ORM models, `Vector(768)`), `llm.py` (google-genai client, router/vision/masthead/boundary), `embeddings.py`, `ocr.py`, `retrieval.py`, `serve_v1.py`, `pipeline.py`, `pdfgen.py`, `intake.py`, `build_served_pdfs.py`, `deps.py`, `pricing.py`.
- `admin/` — CLI/admin ops (curate, upload, batches, health, …). `review/` — review web app. `cloud_ingest/` — Cloud Run Job ingest. `scripts/` — `drive_import.py`, `restore_drill.sh`, etc.
- `migrations/001–006_*.sql` — schema (002 creates `vector`/`pg_trgm`, `paper_chunks`, HNSW index). `tests/` — pytest suite (sqlite fallback via `DATABASE_URL_TEST`, mocks `cv2`/`reportlab`).
- Deploy: `deploy.ps1`, `Makefile`, `cloud_ingest/cloudbuild.yaml`, `Dockerfile`s. (All GCP-specific; replaced in Phase 7.)
- **New in Phase 1:** `app/ports.py` (Protocols), `app/providers/` (adapters + factory).

## Conventions
- Plain Python, explicit functions, pydantic-settings for config, SQLAlchemy 2.0 declarative. No secrets in the repo. Match surrounding comment density and naming.
- Tests are offline and deterministic: fakes/mocks for all providers, sqlite fallback DB. Never call a real cloud in a test.
- Do not touch, run against, or destroy any GCP prod resource (project `ummah`). All migration/cutover work is scripted-but-unexecuted and gated on owner sign-off.

## Constraints (from PRD)
- No retrieval behaviour regressions; existing pytest keeps passing; new tests cover the storage/LLM/vision/embedding/secrets abstractions.
- Keep FastAPI, SQLAlchemy 2.0, pydantic-settings, pgvector HNSW `Vector(768)`, pg_trgm. Embeddings must stay 768-dim.
- GCP impl stays behind the seams for a parallel run; only the final post-sign-off phase deletes GCP code/deps so no `google.*`/`vertexai`/`cloud-sql-connector` imports remain. Plan output: ≤10 in-scope items; string fields <200 chars.

## Research digest (one paragraph)
The research confirms the Azure target surface is stable and 768-dim-compatible: Azure OpenAI's v1 GA API (`/openai/v1/`, plain `OpenAI()` client) supports strict `json_schema` structured outputs and a `dimensions` parameter on `text-embedding-3-*` models, so `Vector(768)` and the HNSW index need no change (pgvector's HNSW 2000-dim cap is far above 768). Blob, Key Vault (RBAC + managed identity), and Postgres Flexible Server (pgvector/pg_trgm must be allow-listed via the `azure.extensions` server parameter before `CREATE EXTENSION`) all authenticate cleanly from Container Apps via a user-assigned managed identity (`azure-identity` `DefaultAzureCredential`). Container Apps + Jobs + ACR are provisionable with parameterized Bicep pinned to GA API versions, pulling images via the `AcrPull` role. Microsoft Graph replaces Drive but does NOT expose sha256 (only quickXorHash/sha1), so sha256 dedupe must be computed locally from downloaded bytes. Current (Nov 2026) model names and pricing are flagged uncertain by the report and are deferred to the Azure-adapter and pricing phases, re-verified against live Azure sources at implementation time.

## Phase plan
1. **Provider-neutral seams (this phase).** Define `ObjectStore`, `StructuredLLM`/vision, `Embedder`, `SecretsProvider`, and a DB engine factory as ports; add GCP adapters behind them and a provider factory; reroute storage call sites. Pure refactor, no Azure, no behaviour change. (AC1, AC2)
2. **Channel-agnostic core.** Extract a handler core + retrieval callable invocable without importing WhatsApp types; WhatsApp becomes a thin adapter. (AC5)
3. **Azure adapters.** Azure OpenAI/Foundry LLM+vision (strict JSON), Azure embeddings `dimensions=768`, Blob, Key Vault+managed identity, Postgres Flexible Server engine; update `pricing.py`/config for Azure models preserving the daily cost-cap breaker; 768-dim test. (AC6, AC10, AC2-extended)
4. **Neutral rename + hygiene.** Non-destructive migration renaming `gcs_*` identifiers/columns to neutral names; repo grep is clean of hardcoded GCP project ids and plaintext secrets. (AC4)
5. **Re-embed + parity.** Re-embed job (Container Apps Job entrypoint) and before/after top-k parity on a fixed query set, recorded for review. (AC7)
6. **OCR A/B gate.** Azure Document Intelligence + Azure vision vs current Gemini on real scanned papers; per-sample pass/fail report. (AC8)
7. **Azure hosting + handover docs.** Parameterized Bicep (Container Apps bot+review, Jobs ingest+backfill, ACR, Postgres Flexible Server); replace GCP deploy scripts; README/RUNBOOK/LAUNCH for Azure; scripted-unexecuted data-migration/cutover plan + Azure restore-drill script. (AC9, AC11)
8. **GCP deletion (post sign-off).** Remove all GCP code/deps/scripts; no `google.cloud`/`google-genai`/`vertexai`/`cloud-sql-connector` imports remain. (AC3)

## Planned architecture
A **ports-and-adapters (hexagonal)** layout. A single `app/ports.py` declares structural `Protocol`s for each external dependency the PRD calls a "seam": `ObjectStore` (blob/object storage), `StructuredLLM` (JSON-schema chat + vision), `Embedder` (768-dim vectors), `SecretsProvider` (secret resolution), and an engine-factory contract for the database. Provider-specific code lives under `app/providers/` (`gcp_storage.py`, `gcp_ai.py`, `gcp_secrets.py`, `gcp_db.py`), and a thin factory in `app/providers/__init__.py` returns the right adapter based on `settings.cloud_provider`. Every call site depends only on a port obtained from the factory, so a later phase adds `azure_*` adapters implementing the same Protocols without editing call sites — enabling the required side-by-side parallel run and a clean final deletion.

The GCP adapters are deliberately **thin wrappers over the existing, proven code** (the Gemini router/vision calls in `app/llm.py`, the embedder in `app/embeddings.py`, the Cloud SQL connector in `app/db.py`), not rewrites. This preserves exact retrieval and OCR behaviour (including the load-bearing `thinking_budget=0`), keeps the diff reviewable, and defers removal of Google imports to the explicit post-sign-off phase. The one seam fully rerouted now is storage, because it is the most pervasive coupling (direct `google.cloud.storage` use across ~20 files) and the Azure Blob parity run depends on every read/write flowing through the `ObjectStore` port.

Key choices a reviewer will challenge, with rationale: **Protocols over ABCs** — structural typing matches "plain Python", lets the existing functions satisfy the port without inheritance, and keeps adapters import-light for tests; **wrap-not-rewrite** — minimises regression risk and blast radius against the "no retrieval regressions / existing pytest passes" constraint; **sync SQLAlchemy retained** — the current engine is sync and the PRD forbids gratuitous stack changes, so Entra-token/async concerns are addressed inside the DB adapter in the Azure phase, not by rearchitecting now; **storage rerouted but AI/DB internals left in place** — balances the parallel-run requirement against phase size, with full Google-import removal scheduled explicitly for Phase 8.

## Architecture decision

An independent reviewer proposed: Strangler-fig per-route cutover; Shadow-mode dual execution; Provider-split services behind a gateway.

**Chosen:** the planned architecture

**Why:** The deciding trade-off is lifecycle fit against the PRD's narrow scope, 10-item cap, and single-repo/delete-after-sign-off mandate — ports-and-adapters with one `cloud_provider` factory switch models exactly that lifecycle (GCP behind interfaces, parallel run via config, clean final deletion) with the least surface. Alternative 1 (strangler-fig) trades one switch for N per-route flags, multiplying config surface and the bookkeeping needed to prove every call site flipped before deletion — real cost, no benefit the PRD asks for. Alternative 3 (gateway-split services) introduces a network hop, auth surface, and infra component that the "narrow / no-new-infra / plain-Python" constraints and item cap forbid, and only pays off for a permanent multi-cloud product rather than a one-time handover. Alternative 2 (shadow-mode) is the only idea worth anything, but the PRD already specifies a scripted before/after top-k on a fixed query set and explicitly defers parallel run to manual — so continuous dual execution doubles cost/latency/quota to buy evidence we're not required to gather; it belongs as a cheap, optional addition scoped to the Phase-5 fixed-query comparison, not as a replacement for the planned architecture, and that does not change Phase 1.
