# Baby PRD -- Migrating a FastAPI/SQLAlchemy/pgvector retrieval bot off GCP+Vertex to self-hosted Docker with a local CPU embedder

## TL;DR
- We will move the PAU past-paper bot off Google Cloud so the school can run it on its own Linux servers.
- The bot will run in Docker with a local Postgres, store files on disk or MinIO, and hand out short-lived download links.
- Search will use a small CPU model that runs on the school's hardware instead of Google's Vertex AI, with no change in what users get.
- WhatsApp keeps working; the code is reshaped so a future Teams agent can plug in later without touching GCP.
- You'll know it works when the existing tests still pass, a before/after search comparison matches, and the whole thing starts with one Docker Compose command.

## Scope
narrow

## Baby PRD

### Problem
The msa-paperbank retrieval bot is tied to Google Cloud and Vertex AI, which blocks handing ownership to the school. It must be migrated to self-hostable, provider-neutral infrastructure the school can run in-house, with no behaviour regression and GCP production left untouched and reversible until sign-off.

### Users / who it's for
The school's IT/operations staff who will own and run the bot in-house, and the students who query PAU past papers via WhatsApp (and later a Teams Copilot Studio agent). Developers maintaining the migrated codebase are also users.

### In scope
- Phase 1: provider-neutral seams (ports for object store, embedder, secrets, DB engine); existing GCP code moved behind them; a provider setting; no behaviour change; existing pytest suite passes unchanged.
- Phase 2: InboundMessage model + handle_inbound entrypoint + retrieval callable that import no WhatsApp types; WhatsApp becomes a thin adapter; reversible gcs_* -> object_key rename via migration and SQLAlchemy synonyms; old env names keep working.
- Phase 3: filesystem/MinIO ObjectStore behind interface with HMAC-signed ~15min expiring URLs; file/env secrets provider; plain Postgres engine factory; auth for the future tool endpoint; remove hardcoded secrets.
- Phase 4: local CPU embedding model (768 dims) behind Embedder interface; re-embed job over paper_chunks.text and title embeddings; before/after top-k parity harness on a fixed query set with a recorded report.
- Phase 5: Dockerfile + Docker Compose (bot, Postgres w/ pgvector+pg_trgm, optional MinIO); health checks; logging; nightly backup job; README and RUNBOOK for school IT; public HTTPS reverse proxy guidance.
- Phase 6: cutover tooling scripted but NOT executed (dump Cloud SQL, copy bucket, restore, re-embed, parity, side-by-side, webhook move, restore drill); final sign-off-gated step deleting all GCP code, deps, scripts.

### Out of scope
- OCR, scan ingest, student photo contributions, review queue changes, Drive/Graph importers, OCR A/B gate.
- Azure hosting of any kind (Container Apps, Bicep, ACR, Key Vault, managed identity, Azure Postgres, Azure OpenAI, Document Intelligence).
- Local LLMs, GPUs, or any LLM/model API dependency in the backend.
- The daily model cost-cap breaker (make it harmless or remove it).
- Study companion, Teams push notifications, and the Copilot Studio agent itself.
- Topic-level search and question-index work (separate later run).
- Modifying or running ingest against GCP production (project ummah); corpus frozen to existing prod DB.
- Executing the data migration, re-embed, webhook swap, or GCP teardown (scripted/planned only, gated on written sign-off).

### Acceptance criteria
1. The existing pytest suite passes unchanged after Phase 1 (tests minimally re-pointed at new seams are allowed; no behavioural assertion changed).
2. No unit test makes a network call during the test run.
3. Ports exist for object store, embedder, secrets, and DB engine, selectable by a provider setting, with the existing GCP implementations behind them.
4. handle_inbound and the retrieval callable import no WhatsApp-specific types; WhatsApp is routed through a thin adapter.
5. The gcs_* rename is applied via a reversible migration using SQLAlchemy synonyms, and the pre-existing env variable names still resolve.
6. The ObjectStore issues signed download URLs that are accepted before ~15 minutes and rejected after expiry or on tampered signature.
7. No plaintext DB password, Cloud SQL connection string, or hardcoded GCP project id remains in apply_migrations.py, scripts, or the Dockerfile.
8. The local embedder produces 768-dimension vectors and the Vector(768) schema plus HNSW index are retained unchanged.
9. A re-embed job repopulates chunk and title embeddings, and a recorded parity report compares old vs new top-k results on a fixed query set.
10. docker compose up starts bot + Postgres (pgvector, pg_trgm) + optional MinIO, and each service reports healthy via its health check.
11. README and RUNBOOK exist covering startup, nightly backup, restore-from-backup drill, and HTTPS reverse proxy setup.
12. After the Phase 6 final step, no google.cloud, google-genai, vertexai, or cloud-sql-connector imports remain in the codebase.
13. Phase 6 migration/cutover/teardown scripts exist but are not executed, and GCP production remains running and reversible.

### Constraints
- Python 3.12; keep FastAPI, SQLAlchemy 2.0, pydantic-settings, pgvector, pg_trgm.
- Existing pytest suite must keep passing; no network calls in unit tests.
- No secrets committed to the repository.
- Backend has no LLM or model API dependency; runs in Docker Compose on no-GPU school Linux servers.
- Embeddings are 768-dimension from a local CPU model; Vector(768) schema and HNSW index stay.
- Never modify GCP production (project ummah) and never run ingest; GCP prod stays running and reversible until explicit written sign-off.
- Each in-scope item under 300 chars, at most 10 items; each research topic under 150 chars.
- Copilot Studio tool integration is a later run; this migration only leaves a channel-neutral handler core and a clean retrieval callable.
- Backend reachable over public HTTPS; one tool call per request (MCP or REST) for the future agent.

### Research plan
- Topic: Migrating a FastAPI/SQLAlchemy/pgvector retrieval bot off GCP+Vertex to self-hosted Docker with a local CPU embedder
- Time range: last 3 years
- Items:
  1. local-cpu-embedder-768 | Local CPU embedding models producing 768-dim vectors | Which CPU-friendly sentence-embedding models output 768 dims, how to run them (sentence-transformers/ONNX) without GPU, and their retrieval quality vs Vertex. | modules: general-web, academic-papers, github-debug
  2. topk-parity-harness | Before/after top-k retrieval parity methodology | How to build a fixed-query-set top-k parity check across different embeddings (overlap/rank metrics) and what a reasonable pass threshold looks like. | modules: general-web, academic-papers
  3. pgvector-hnsw-reembed | pgvector HNSW re-embedding without schema change | How to re-embed existing rows into an unchanged Vector(768) column with an HNSW index and keep pg_trgm hybrid search working. | modules: general-web, github-debug, stackoverflow
  4. hmac-signed-urls | HMAC-signed expiring download URLs | Patterns for backend-issued short-lived HMAC-signed URLs (~15 min) with tamper and expiry rejection, over filesystem and MinIO/S3 storage. | modules: general-web, stackoverflow, github-debug
  5. objectstore-minio-fs | ObjectStore abstraction over filesystem and MinIO | How to design one ObjectStore interface backing both local filesystem and MinIO (S3 API) for put/get/signed-url in Python. | modules: general-web, github-debug
  6. sqlalchemy-synonym-rename | Reversible column rename via SQLAlchemy synonyms | How to rename a DB column (gcs_* -> object_key) with a reversible migration while keeping old attribute access via synonyms and old env names working. | modules: general-web, stackoverflow, github-debug
  7. compose-postgres-backup | Docker Compose Postgres+pgvector deploy and backup | Compose setup for Postgres with pgvector/pg_trgm, health checks, nightly pg_dump backup and restore drill, and HTTPS reverse proxy guidance. | modules: general-web, stackoverflow
  8. channel-neutral-tool-endpoint | Channel-neutral handler and MCP/REST tool endpoint | How to structure a channel-neutral InboundMessage/handle_inbound core and an authed single-call retrieval endpoint callable later by Copilot Studio (MCP or REST). | modules: general-web, github-debug
- Official docs to read:
  - FastAPI
  - SQLAlchemy 2.0
  - pydantic-settings
  - pgvector
  - pg_trgm
  - PostgreSQL
  - Docker Compose
  - MinIO
  - sentence-transformers
  - ONNX Runtime
  - Hugging Face Transformers
  - Meta WhatsApp Cloud API
  - Model Context Protocol (MCP)
  - Alembic
- Academic searches:
  - CPU-efficient sentence embedding models retrieval quality benchmark
  - evaluating embedding model substitution impact on top-k retrieval overlap
- Prior-art searches:
  - FastAPI pgvector semantic search self-hosted reference implementation
  - sentence-transformers ONNX CPU embedding FastAPI service
  - Python ObjectStore interface filesystem MinIO S3 signed URL
  - HMAC signed expiring download link FastAPI example

## Assumptions
- [risky] The local CPU embedder uses a sentence-transformers / Hugging Face model with native 768-dim output (e.g. all-mpnet-base-v2 class), run via sentence-transformers or ONNX Runtime; exact model chosen to maximise top-k parity.
- [risky] The top-k parity harness passes if new-vs-old top-k result sets meet a defined overlap/rank-correlation threshold on the fixed query set; the threshold is proposed in the report since the prompt specifies the check but not a number.
- [risky] ObjectStore defaults to local filesystem for development and MinIO is optional/for production, selected by configuration.
- [risky] The future tool endpoint uses a static bearer/shared-secret token for auth now, with a view to Copilot Studio-compatible auth later.
- [risky] The authoritative tree is the root-level codebase (app/, admin/, review/, cloud_ingest/, scripts/, migrations/, tests/); any nested msa-paperbank/ mirror is not edited.
- [risky] Column rename uses Alembic (the existing migrations/ tooling) for the reversible migration carrying the SQLAlchemy synonyms.
- [risky] Making the daily model cost-cap breaker 'harmless' means turning it into a no-op/removing it, since the backend no longer calls any paid model API.
- [safe] The fixed parity query set is newly authored (a representative sample of real past-paper queries) since none was provided.
- [safe] Signed URLs use HMAC-SHA256 over path + expiry, verified by the backend before serving the file.
- [safe] Reverse proxy guidance targets nginx or Caddy for TLS termination in front of the FastAPI backend.
- [safe] Dependency management stays on the project's existing tooling (e.g. requirements/pyproject) unchanged; no switch to a new package manager.
- [safe] Earlier project-memory notes that place Azure adapters in Phase 3 and defer the gcs_* rename to Phase 4 are superseded by this prompt (no Azure; rename in Phase 2); the prompt's stated phases govern.
- [safe] No external links were supplied in the prompt, so none needed to be opened.

## Recommended questions
- (none)

## Original request (authoritative)

The person's own words, unedited. Where anything above differs from this, this request wins.

> Migrate the msa-paperbank bot (PAU past-paper retrieval bot; Python 3.12 FastAPI, SQLAlchemy 2.0, Postgres with pgvector and pg_trgm; about 6k LOC; repo root) off Google Cloud and Vertex AI onto the school's own in-house Linux servers, for an ownership transfer to the school. Behaviour must not regress. Keep every plan and spec string short: each in-scope item under 300 characters, each research topic under 150 characters, at most 10 in-scope items.
>
> TARGET ARCHITECTURE (decided by the owner; do NOT plan Azure hosting):
> - The backend runs in Docker (Docker Compose) on school servers with NO GPU. No Azure Container Apps, Bicep, ACR, Key Vault, managed identity, Azure Postgres, Azure OpenAI or Document Intelligence.
> - The backend has no LLM or model API dependency. Routing, conversation and any study features are done by a Microsoft Copilot Studio agent in Teams (school pays Copilot Studio credits). That agent calls the backend over public HTTPS (one tool call per request, MCP or REST). Copilot Studio integration itself is a LATER separate run, but this migration must leave a channel-neutral handler core and a clean retrieval callable that the tool endpoint can call.
> - WhatsApp stays as a secondary channel, retrieval only, using the existing Meta webhook.
> - Semantic search embeddings move from Vertex to a small local CPU embedding model that produces 768-dimension vectors, so the Vector(768) schema and HNSW index stay. The existing paper_chunks.text and title text are re-embedded once; stored Vertex vectors are not comparable. A before/after top-k parity check on a fixed query set is required.
> - PDFs and files are served through short-lived signed links (about 15 minutes) issued by the backend. Storage is a local filesystem or MinIO behind an ObjectStore interface.
>
> DECIDED OUT OF SCOPE (do not build): OCR, scan ingest, student photo contributions, the review queue changes, Drive or Graph importers, OCR A/B gate, Azure anything, local LLMs or GPUs, the daily model cost-cap breaker (make it harmless or remove it), study companion, Teams push notifications, the Copilot Studio agent itself, and the topic-level search and question-index work (separate later run).
> The corpus is frozen to the existing production database (Cloud SQL project ummah). Never modify GCP production and never run ingest; GCP prod must stay running and reversible until the owner gives explicit written sign-off.
>
> PHASES (in order, each tested before the next):
> 1. Provider-neutral seams: interfaces for object store, embedder, secrets and DB engine; existing GCP code moved behind them; a provider setting; no behaviour change; existing pytest suite passes unchanged.
> 2. Channel-neutral core: an InboundMessage model and handle_inbound entrypoint plus a retrieval callable that import no WhatsApp types; WhatsApp becomes a thin adapter. Non-destructive rename of gcs_* names to neutral object_key style names via a reversible migration and SQLAlchemy synonyms, keeping old env names working.
> 3. In-house plumbing: filesystem or MinIO ObjectStore with HMAC-signed expiring URLs, file or environment secrets provider, plain Postgres engine factory, auth for the future tool endpoint, remove hardcoded secrets (apply_migrations.py has a plaintext DB password and Cloud SQL string; scripts and Dockerfile hardcode a GCP project id).
> 4. Local embedder: CPU embedding model (768 dims) behind the Embedder interface, re-embed job over the existing chunks and title embeddings, and a before/after top-k parity harness with a recorded report.
> 5. Deployment: Dockerfile and Docker Compose (bot, Postgres with pgvector and pg_trgm, optional MinIO), health checks, logging, nightly backup job, README and RUNBOOK for school IT, public HTTPS reverse proxy guidance.
> 6. Cutover plan and tooling, scripted but NOT executed: dump Cloud SQL, copy the bucket, restore, re-embed, parity check, run old and new side by side, move the WhatsApp webhook, restore-from-backup drill. Then a final step, gated on written sign-off, that deletes all GCP code, dependencies and scripts.
>
> CONSTRAINTS: keep FastAPI, SQLAlchemy 2.0, pydantic-settings, pgvector and pg_trgm; the existing pytest suite must keep passing; no secrets committed; no network calls in unit tests; Python 3.12. After the work, no google.cloud, google-genai, vertexai or cloud-sql-connector imports remain (phase 6 final step).
