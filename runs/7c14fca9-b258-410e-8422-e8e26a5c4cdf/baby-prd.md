# Baby PRD -- Migrating a FastAPI past-paper retrieval bot from GCP/Vertex AI to Azure with provider-neutral seams and no retrieval regressions

## TL;DR
- We will move the msa-paperbank WhatsApp bot (it finds past exam papers for students) off Google Cloud and onto Microsoft Azure, so the school can own it in its Microsoft 365 account.
- WhatsApp stays the only way students use it during this phase; nothing students see should change.
- We swap the plumbing: storage, AI models, secrets, and database all get a clean Azure version behind simple interchangeable layers.
- The AI that understands questions changes, so papers get re-indexed and search quality is checked to make sure answers stay as good as before.
- It works when the existing automated tests still pass, the system runs on Azure infrastructure defined in code, and the old Google setup is left fully intact until the owner approves the final switch.

## Scope
narrow

## Baby PRD

### Problem
The msa-paperbank bot runs entirely on Google Cloud and Vertex AI, but ownership is transferring to a school that uses a Microsoft 365 tenant. The code is tightly coupled to GCP (Cloud Run, Cloud SQL, GCS, Secret Manager, google-genai, Google Drive), which blocks the handover and future Microsoft-native features.

### Users / who it's for
The school taking ownership and its administrators/maintainers who will run the bot on Azure; indirectly the PAU students who query past papers over WhatsApp and must see no change in behaviour.

### In scope
- Provider-neutral seams: storage (Blob), LLM/vision/embedding (Azure OpenAI / Microsoft Foundry), secrets/config (Key Vault + managed identity), DB connection factory (Azure Postgres Flexible Server with pgvector + pg_trgm)
- Rename gcs_* identifiers to neutral names via migration where needed
- Re-embedding: migration for new Vector column + HNSW index, a re-embed job, and retrieval-quality parity check against existing retrieval/embedding tests
- Update pricing.py/config for new Azure models while preserving the daily cost-cap breaker
- Azure hosting via Bicep IaC: Container Apps (bot + review app), Container Apps Jobs (ingest + served-PDF backfill), ACR; replace deploy.ps1/Makefile/cloud_ingest scripts and remove hardcoded GCP project ids
- Documented and scripted (not executed) data-migration and cutover plan, plus Azure restore drill
- Replace Google Drive importer with a Microsoft Graph (SharePoint/OneDrive) importer preserving sha256 dedupe
- Update README, RUNBOOK, LAUNCH for Azure
- New tests covering the storage/LLM/secrets abstractions

### Out of scope
- Teams channel and Teams-only study companion
- Entra SSO for the review app
- Copilot-licensing question
- Executing the data migration, cutover, or WhatsApp webhook swap
- Running the full corpus ingest
- Modifying, destroying, or touching any live GCP prod resource in project ummah

### Acceptance criteria
1. All direct google.cloud.storage imports are removed from app/ and the listed modules, and storage access goes through a single Blob-backed interface with an Azure implementation
2. app/llm.py and app/embeddings.py call AI through a provider interface with an Azure OpenAI / Microsoft Foundry implementation, and no module imports google-genai
3. Secrets/config load through a Key Vault + managed-identity loader with no GCP Secret Manager calls and no secrets committed to the repo
4. A migration adds the new-dimension Vector column and HNSW index, and a re-embed job exists that can repopulate embeddings
5. Running the existing pytest suite (including tests/test_retrieval*.py and test_embeddings.py) passes with no retrieval regressions
6. New tests exist and pass for the storage, LLM, and secrets abstractions
7. Bicep templates provision Container Apps (bot + review), Container Apps Jobs (ingest + served-PDF backfill), and ACR, parameterized with no hardcoded GCP project ids
8. pricing.py and config reference the Azure models and the daily cost-cap breaker still triggers at the configured limit
9. A Microsoft Graph (SharePoint/OneDrive) importer replaces drive_import.py and still performs sha256 dedupe
10. A documented, scripted (unexecuted) migration/cutover plan and an Azure restore-drill script exist in the repo
11. README, RUNBOOK, and LAUNCH describe the Azure deployment
12. No GCP prod resource in project ummah is modified or destroyed by any code in this phase

### Constraints
- Target cloud: Microsoft Azure under the school's Microsoft 365 tenant/subscription
- Keep plain Python, pydantic-settings, SQLAlchemy 2.0 style; FastAPI; gunicorn+uvicorn
- Database must retain pgvector (HNSW) and pg_trgm
- No retrieval behavior regressions; existing pytest suite must keep passing
- Fully reversible: GCP prod untouched until explicit cutover approval; migration/cutover scripted but not executed
- No secrets in the repo
- WhatsApp is the only live channel this phase; leave clean seams for Teams/SSO/Copilot later

### Research plan
- Topic: Migrating a FastAPI past-paper retrieval bot from GCP/Vertex AI to Azure with provider-neutral seams and no retrieval regressions
- Time range: last 2 years
- Items:
  1. azure-container-apps-hosting | Azure Container Apps + Jobs + ACR hosting model | How to host a FastAPI gunicorn/uvicorn service and run ingest/backfill batch jobs on Container Apps with managed identity, and how this maps from Cloud Run / Cloud Run Jobs | modules: general-web, github-debug
  2. azure-postgres-pgvector | Azure Database for PostgreSQL Flexible Server with pgvector and pg_trgm | How to enable pgvector (HNSW) and pg_trgm, connect via managed identity, and the migration/backup/restore story versus Cloud SQL | modules: general-web, stackoverflow
  3. azure-openai-structured-output | Azure OpenAI / Microsoft Foundry models and structured JSON output | Which models support response-schema/structured JSON for router, vision OCR, boundary probe, and validation, and how to replace Gemini thinking_budget/response_schema semantics | modules: general-web
  4. azure-embeddings-dimensions | Azure embedding models, dimensions, and HNSW re-embedding | Available embedding models, their dimensions, and how changing vector space affects the pgvector column, HNSW index, and retrieval parity | modules: general-web, academic-papers
  5. azure-keyvault-managed-identity | Key Vault + managed identity secrets loader | How to load secrets at runtime via Key Vault with managed identity in Container Apps, replacing GCP Secret Manager FROM_SECRET patterns | modules: general-web
  6. azure-blob-storage-sdk | Azure Blob Storage SDK and interface design | Python SDK patterns for blob upload/download/signed-URL equivalents to replace direct google-cloud-storage use behind one interface | modules: general-web, stackoverflow
  7. microsoft-graph-file-import | Microsoft Graph SharePoint/OneDrive file importer | How to list and download files from SharePoint/OneDrive via Microsoft Graph with app auth, to replace the Google Drive importer while keeping sha256 dedupe | modules: general-web, github-debug
  8. bicep-iac-parameterization | Bicep IaC for parameterized multi-subscription provisioning | How to structure parameterized Bicep so the school's subscription can stand up Container Apps, Jobs, ACR, Postgres, Key Vault, and Storage with no hardcoded ids | modules: general-web, github-debug
- Official docs to read:
  - Azure Container Apps
  - Azure Container Apps Jobs
  - Azure Container Registry
  - Azure Database for PostgreSQL Flexible Server
  - pgvector
  - pg_trgm
  - Azure OpenAI Service
  - Microsoft Foundry
  - Azure Key Vault
  - Azure Managed Identity
  - Azure Blob Storage
  - azure-storage-blob Python SDK
  - azure-identity Python SDK
  - Microsoft Graph API
  - Bicep
  - FastAPI
  - SQLAlchemy 2.0
  - pydantic-settings
  - gunicorn
  - uvicorn
- Academic searches:
  - dense retrieval parity after changing embedding model vector space
  - HNSW index recall quality text-embedding-3 versus gemini-embedding
- Prior-art searches:
  - FastAPI app provider-neutral storage abstraction GCS Azure Blob
  - GCP Cloud Run to Azure Container Apps migration Bicep example
  - pgvector HNSW re-embedding migration script Postgres
  - Microsoft Graph SharePoint file download Python sha256 dedupe

## Assumptions
- [risky] Azure OpenAI with gpt-4o-class models (structured JSON output) replaces Vertex Gemini for router/vision/boundary/validation/masthead tasks.
- [risky] text-embedding-3-large (3072-dim) replaces gemini-embedding-001 (768-dim), requiring the new Vector column dimension and HNSW rebuild.
- [risky] Application object storage targets Azure Blob Storage, while Microsoft Graph (SharePoint/OneDrive) is used only for the corpus importer.
- [risky] The provider-neutral interfaces retain a GCP implementation alongside the Azure one, selectable via config, to support parallel run and reversibility.
- [risky] Authentication to Azure services uses managed identity in Container Apps rather than connection strings or keys where supported.
- [risky] gcs_* identifiers are renamed to neutral names like blob_object / object_store_bucket via a non-destructive migration.
- [risky] The daily cost-cap breaker keeps its existing logic and thresholds, only re-pointing to Azure model prices in pricing.py/config.
- [risky] The review web app remains a FastAPI/server app hosted on Container Apps with no auth change in this phase (Entra SSO deferred).
- [safe] The Bicep IaC is organized as parameterized modules with environment parameter files rather than a single monolithic template.
- [safe] Retrieval-quality parity is judged by the existing retrieval/embedding tests plus a before/after top-k comparison on a fixed query set, not a new formal benchmark.
- [safe] Any external links referenced in the prompt could not be opened and were not relied upon; design is based solely on the prompt text and code description.

## Recommended questions
- (none)

## Original request (authoritative)

The person's own words, unedited. Where anything above differs from this, this request wins.

> PHASE A of a multi-run migration: move the msa-paperbank bot (PAU past-paper retrieval bot, FastAPI, ~6k LOC Python) completely off Google Cloud / Vertex AI onto Azure, as part of an ownership transfer to the school (Microsoft 365 tenant). WhatsApp stays the only live channel in this phase. Teams channel, Teams-only study companion, Entra SSO for the review app and the Copilot-licensing question are LATER runs; this phase only leaves clean seams for them.
>
> CURRENT GCP COUPLING (from the code)
> - Compute: Cloud Run (deploy.ps1, Makefile, Dockerfile, gunicorn+uvicorn :8080), review/ web app, cloud_ingest/ Cloud Run Job (cloudbuild.yaml, deploy.sh, teardown.sh), infra_bootstrap.sh, scripts/restore_drill.sh.
> - DB: Cloud SQL Postgres via cloud-sql-python-connector+pg8000 (app/db.py, apply_migrations.py, cloud_ingest/main.py, verify_db.py). Needs pgvector (HNSW, Vector(768)) and pg_trgm (migrations/002_phase2.sql).
> - Storage: google-cloud-storage imported directly in app/main.py, intake.py, retrieval.py, pdfgen.py, build_served_pdfs.py, review/main.py, admin/{batches,upload,curate,health}.py, scripts/upload_test_batch.py. DB columns are named gcs_object; config has gcs_bucket and several *_gcs_prefix/prefix settings.
> - Secrets: GCP Secret Manager (GCP_LOAD_FROM_SECRETS, *_FROM_SECRET) in app/config.py.
> - AI: google-genai vertexai=True in app/llm.py (router, vision OCR, page-boundary probe, contribution validation, masthead read; gemini flash/pro with response_schema JSON and thinking_budget=0), app/embeddings.py (gemini-embedding-001, 768-dim), app/ocr.py, admin/health.py, cloud_ingest/main.py; pricing in app/pricing.py and config price_* settings with a daily cost-cap breaker.
> - Corpus import: scripts/drive_import.py uses Google Drive.
> - Prod already exists on GCP (project 'ummah'); full ingest is gated on explicit owner go. Do not run ingest or modify/destroy any GCP prod resource.
>
> TARGET FOR PHASE A
> 1. Thin provider-neutral seams: a storage interface (Blob impl, replacing direct google.cloud.storage use), an LLM/vision/embedding interface in app/llm.py and app/embeddings.py (Azure OpenAI / Microsoft Foundry impl with structured JSON output), a secrets/config loader (Key Vault + managed identity), and a DB connection factory (Azure Database for PostgreSQL Flexible Server with pgvector and pg_trgm). Rename gcs_* identifiers to neutral names via migration where needed.
> 2. Re-embedding: the new embedding model changes dimension/vector space, so add a migration for the Vector column and HNSW index plus a re-embed job; retrieval-quality parity must be checked against tests/test_retrieval*.py and test_embeddings.py.
> 3. Update pricing.py/config for the new models while keeping the daily cost cap behavior.
> 4. Azure hosting: Azure Container Apps for bot and review app, Container Apps Jobs for ingest and served-PDF backfill, ACR; infrastructure-as-code (Bicep) parameterized so the school's subscription can stand it up; replace deploy.ps1/Makefile/cloud_ingest scripts and remove hardcoded GCP project ids.
> 5. Data migration and cutover plan (documented and scripted, NOT executed): Cloud SQL dump to Azure Postgres, GCS to Blob copy, re-embed, parallel run, WhatsApp webhook swap, GCP teardown only after owner sign-off. Restore drill rewritten for Azure backups.
> 6. Replace Google Drive import with a Microsoft Graph (SharePoint/OneDrive) importer that keeps sha256 dedupe.
> 7. Handover docs: update README, RUNBOOK, LAUNCH for Azure.
>
> CONSTRAINTS
> - No retrieval behavior regressions; the existing pytest suite must keep passing and new tests cover the storage/LLM/secrets abstractions.
> - Reversible: GCP prod stays untouched until explicit cutover approval. No secrets in the repo. Match existing style (plain Python, pydantic-settings, SQLAlchemy 2.0).
> - Keep the in-scope list short and each item concise.
