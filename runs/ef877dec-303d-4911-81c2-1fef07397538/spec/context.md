# Project context — msa-paperbank GCP→self-hosted migration

## What this is
`msa-paperbank` is a PAU past-paper retrieval bot (~6k LOC, repo root): Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL with `pgvector` (HNSW, `Vector(768)`) and `pg_trgm`. Students query past papers over WhatsApp (Meta Cloud API webhook); the bot does hybrid fuzzy (`pg_trgm`) + semantic (pgvector) retrieval and serves PDFs. Today it is wired to Google Cloud: Vertex/`google-genai` for embeddings and the LLM router, Cloud SQL (via `cloud-sql-connector`), GCS (`google-cloud-storage`), and Secret Manager.

The whole project migrates the bot off GCP+Vertex onto self-hostable, provider-neutral infrastructure the school can run in-house, with **no behaviour regression** and **GCP production (project `ummah`) left untouched and reversible** until explicit written sign-off. This document plus `PHASE_1_SPEC.md` governs Phase 1.

## Stack and why
- **FastAPI / SQLAlchemy 2.0 / pydantic-settings / pgvector / pg_trgm** — retained unchanged; these are hard PRD constraints and already in the codebase.
- **`typing.Protocol` ports + per-provider adapters + a factory** — the mechanism for making GCP swappable without touching call sites; plain-Python, no new dependency.
- Phase 1 adds **no new runtime dependencies**. Later-phase technology (chosen from research, for context only): a local CPU embedder producing 768-dim vectors via `sentence-transformers` (`all-mpnet-base-v2` class) and/or ONNX Runtime CPU (Phase 4); `itsdangerous`/HMAC-SHA256 signed URLs and filesystem/MinIO object store (Phase 3); Alembic `op.alter_column(new_column_name=...)` + SQLAlchemy `synonym()` for the reversible `gcs_*`→`object_key` rename (Phase 2); `pgvector/pgvector` Docker image + Docker Compose + Caddy/nginx reverse proxy (Phase 5).

## Repo layout (authoritative root tree)
- `app/` — bot core: `config.py` (pydantic-settings `Settings`), `db.py` (engine + ORM models), `embeddings.py` (Vertex embeddings), `llm.py` (Vertex genai client + router/OCR), `retrieval.py`, `serve_v1.py`, `pipeline.py`, `intake.py`, `contributions.py`, `pdfgen.py`, `build_served_pdfs.py`, `main.py` (FastAPI app + WhatsApp webhook), `deps.py`.
- `admin/` — operator CLIs (`curate.py`, `upload.py`, `health.py`, `batches.py`, …).
- `review/` — separate review web service (same DB+bucket).
- `cloud_ingest/`, `scripts/` — ingest/import tooling (frozen; not run against prod).
- `migrations/` — raw SQL `001..006`; `apply_migrations.py` applies them (contains hardcoded secrets — remediated in Phase 3).
- `tests/` — pytest suite; `conftest.py` sets dummy env, mocks heavy deps, defaults DB to sqlite.
- `msa-paperbank/` — **stale mirror; do not edit.**

## Conventions
- Settings accessed only through `app.config.settings`; no ad-hoc `os.environ` reads in business logic.
- Ports are structural `typing.Protocol`; adapters delegate to existing modules rather than duplicating logic.
- Adapters never open network clients at import time — only lazily / via `from_settings`.
- Unit tests make **no network calls**; mock at the seam, or use in-memory fakes.
- No secrets committed. Commit messages: no AI-attribution trailers.

## Constraints
- Python 3.12; keep FastAPI, SQLAlchemy 2.0, pydantic-settings, pgvector(HNSW)/`pg_trgm`, `Vector(768)`.
- Existing pytest suite must keep passing (minimal re-pointing at new seams allowed; no behavioural assertion changed); no network calls in unit tests.
- Backend ends up with no LLM/model-API dependency and runs in Docker Compose on no-GPU Linux servers.
- Never modify or run ingest against GCP prod (`ummah`); it stays running and reversible until sign-off.

## Glossary
- **Port** — a `typing.Protocol` interface (ObjectStore, Embedder, SecretsProvider, EngineProvider).
- **Adapter** — a concrete implementation of a port for one provider (GCP this phase).
- **Factory** — `app/providers/__init__.py` functions returning the adapter chosen by `settings.provider`.
- **Seam** — the single point where code obtains an implementation via the factory instead of importing a vendor SDK.
- **Parity** — before/after top-k retrieval comparison on a fixed query set (Phase 4).

## Research digest (one paragraph)
Research confirms every retained library is current and stable for this use: FastAPI (lifespan context manager + `Depends()` for swappable ports), SQLAlchemy 2.0.x (`select()`/`Session.execute`/`scalars`, and `synonym()` for the later rename), pydantic-settings 2.16.x (`SettingsConfigDict`, `AliasChoices`, `secrets_dir`), and pgvector 0.8.x where `Vector(768)` + HNSW are well within limits and require no schema change. For later phases it points to `sentence-transformers all-mpnet-base-v2` (native 768-dim, CPU) and/or ONNX Runtime CPU for the embedder, custom HMAC-SHA256 signed URLs (uniform across filesystem and MinIO) for downloads, drop-index/bulk-update/rebuild for re-embedding without touching the HNSW/`pg_trgm` schema, Jaccard@k + rank-correlation (no relevance labels) for the parity harness, Alembic `alter_column(new_column_name=…)` for the reversible rename, and the `pgvector/pgvector` image + Compose health-gated services for deployment. None of this is needed in Phase 1, which is a pure provider-seam refactor using only the existing stack.

## Phase plan
- **Phase 1 (this spec):** provider-neutral seams — ports for object store, embedder, secrets, DB engine; existing GCP code moved behind GCP adapters; a `provider` setting; no behaviour change; existing pytest passes. (AC 1, 2, 3)
- **Phase 2:** channel-neutral core — `InboundMessage` + `handle_inbound` + a retrieval callable importing no WhatsApp types; WhatsApp becomes a thin adapter; reversible `gcs_*`→`object_key` rename via Alembic migration + SQLAlchemy `synonym()`; old env names still resolve. (AC 4, 5)
- **Phase 3:** in-house plumbing — filesystem/MinIO `ObjectStore` with HMAC-signed ~15-min URLs; file/env secrets provider; plain Postgres engine factory; auth for the future tool endpoint; remove hardcoded secrets. (AC 6, 7)
- **Phase 4:** local CPU embedder (768-dim) behind the `Embedder` port; re-embed job over chunk + title embeddings; before/after top-k parity harness with a recorded report. (AC 8, 9)
- **Phase 5:** Dockerfile + Docker Compose (bot, Postgres w/ pgvector+pg_trgm, optional MinIO), health checks, logging, nightly backup, README + RUNBOOK, HTTPS reverse-proxy guidance. (AC 10, 11)
- **Phase 6:** cutover tooling scripted but NOT executed; final sign-off-gated step deleting all GCP code/deps/scripts. (AC 12, 13)

## Planned architecture
Ports-and-adapters (hexagonal). Four structural `typing.Protocol` ports in `app/ports.py` (`ObjectStore`, `Embedder`, `SecretsProvider`, `EngineProvider`) describe exactly the operations the codebase performs today against GCS, Vertex embeddings, Secret Manager, and Cloud SQL. Each provider implements them in `app/providers/<provider>/`; this phase ships only `app/providers/gcp/`, whose adapters are thin wrappers that delegate to the current modules (`google.cloud.storage`, `app.embeddings`, `google.cloud.secretmanager`, the Cloud SQL `Connector`) so there is zero behaviour change. A factory in `app/providers/__init__.py` returns the adapter chosen by `settings.provider` (default `"gcp"`), and the FastAPI `lifespan` builds the concrete object store once and stashes it on `app.state`, mirroring how `app.state.gcs`/`app.state.http` already work. The DB engine and secrets loader are rebuilt through their providers at the same boot points they are constructed today.

This structure models the migration's actual lifecycle: today everything is GCP; Phase 3–4 add `local`/`minio` and local-embedder adapters behind the same ports with no call-site churn; Phase 6 deletes `app/providers/gcp/` and the vendor imports wholesale once the provider default flips. Keeping call sites dependent only on the ports (not on `google.cloud.*` types) is what lets later phases swap one adapter at a time and lets the final teardown be a clean delete.

Two choices a reviewer will probe. First, **`Protocol` rather than ABC**: it matches the "plain Python" constraint, avoids inheritance coupling, and makes in-memory fakes trivial for network-free unit tests — at the cost of no enforced base class, which we accept because tests assert conformance. Second, **we do not reroute every GCS/Vertex call site in Phase 1**: the object store is rerouted across the live serve path and the one call site the existing tests exercise, while embedder/secrets/engine are "moved behind" their ports via adapters + factory with internal call sites flipped where cheap and the rest deferred to the phase that actually swaps them. This bounds the blast radius and keeps the suite green now, at the cost of some raw `storage.Client`/`app.embeddings` calls lingering in non-serve paths until their phase — a deliberate trade favouring reversibility over a big-bang refactor.

## Architecture decision

An independent reviewer proposed: Strangler-fig direct swap (no ports/provider layer); Sidecar services for embedder and storage (network process boundary); Single composition-root 'Environment' object instead of four ports.

**Chosen:** the planned architecture

**Why:** The ports-and-adapters layer is load-bearing for two specific PRD mechanics the alternatives all weaken. The phased plan swaps implementations independently — object store in Phase 3, embedder in Phase 4 — which Alt 3's bundled `Environment` makes awkward (mixed GCP-secrets/local-storage states mid-migration) and Alt 1's scattered per-site branches turn into repeat call-site churn each phase. AC 12/13's "clean delete of all GCP code" is a one-line `rm -rf app/providers/gcp/` under the plan but a diff-by-diff audit across 8 files under Alt 1; AC 2's network-free fakes need one seam, not eight. Alt 2's sidecars add containers, network hops on the retrieval hot path, and RUNBOOK/restore-drill surface that directly contradict the PRD's "simple for school IT, one Docker Compose command, no behaviour regression" — overkill for one small in-process CPU model the research confirms loads fine at FastAPI lifespan. The planned design's cost (some speculative ports not fully rerouted in Phase 1) is real but cheap, and is exactly what contains the existing 8-file sprawl before teardown.
