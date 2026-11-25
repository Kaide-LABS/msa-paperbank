# Baby PRD -- Migrate a FastAPI WhatsApp retrieval bot from GCP/Vertex to Azure with provider-neutral seams, reversibly

## TL;DR
- We will move the school's WhatsApp past-paper bot off Google Cloud and rebuild it on Microsoft Azure, keeping WhatsApp as the only live channel for now.
- The code gets clean 'swap points' for storage, AI models, secrets and the database so Azure parts drop in and Google parts come out later.
- AI reading of scanned papers and search quality must be proven as good as today before any real data is re-processed.
- The live Google system stays untouched: the Azure switchover and data move are fully written up and scripted but NOT run until the owner approves.
- You will know it works when the test suite still passes, search results match the old ones on a fixed set of questions, and the bot answers on Azure in a parallel run.

## Scope
narrow

## Baby PRD

### Problem
The msa-paperbank WhatsApp retrieval bot is tied to Google Cloud/Vertex AI, blocking ownership transfer to the school's Microsoft 365 tenant.

### Users / who it's for
The school taking ownership (M365 tenant admins/maintainers) and PAU students using the WhatsApp past-paper bot.

### In scope
- Add provider-neutral seams: storage (Blob), LLM/vision/embedding (Azure OpenAI/Foundry), secrets/config (Key Vault + managed identity), DB connection factory.
- Non-destructive rename of gcs_* identifiers/columns to neutral names; keep channel-agnostic handler core and WhatsApp-independent retrieval callable.
- Research and choose current (Nov 2026) Azure OpenAI/Foundry models; add A/B OCR gate vs Gemini on real paper sample; evaluate Azure AI Document Intelligence.
- Azure embeddings via text-embedding-3-large dimensions=768 keeping Vector(768) and HNSW index; add re-embed job with parity checks.
- Update pricing.py/config for new models, preserving the daily cost-cap breaker.
- Azure hosting: Container Apps (bot, review), Container Apps Jobs (ingest, served-PDF backfill), ACR, parameterized Bicep; remove hardcoded GCP project ids.
- Replace deploy.ps1/Makefile/cloud_ingest scripts with Azure equivalents.
- Keep GCP impl behind interfaces for parallel run/reversibility, plus a final step deleting all GCP code/deps once owner signs off.
- Document and script (not execute) data migration and cutover; rewrite restore drill for Azure backups.
- Replace Google Drive importer with Microsoft Graph (SharePoint/OneDrive) importer preserving sha256 dedupe; update README, RUNBOOK, LAUNCH.

### Out of scope
- Teams custom-engine bot, Teams study companion, and Entra SSO for the review app (explicitly later runs).
- Copilot Studio or declarative-agent approach for Teams.
- Running the ingest, the data migration, the cutover, or the WhatsApp webhook swap in this phase.
- Modifying or destroying any GCP prod resource (project 'ummah'); GCP teardown before owner sign-off.
- Adding channels other than WhatsApp in this phase.

### Acceptance criteria
1. The existing pytest suite (including tests/test_retrieval*.py, test_embeddings.py) passes with no regressions after the changes.
2. New tests exist and pass covering the storage, LLM/vision/embedding, and secrets/config abstractions.
3. No direct google.cloud.storage import remains in app code paths; all storage access goes through the Blob/storage interface.
4. A before/after top-k comparison on a fixed query set shows retrieval parity between old and re-embedded vector space, recorded as a passing check.
5. The OCR A/B gate on a real-paper sample reports Azure (OpenAI vision or Document Intelligence) accuracy vs Gemini, and re-ingest is not approved unless the gate passes.
6. Embedding output remains 768-dim; Vector(768) column and HNSW index definitions are unchanged.
7. pricing.py/config list the new Azure model prices and the daily cost-cap breaker still triggers in tests.
8. Bicep deploys bot and review Container Apps, ingest and backfill Container Apps Jobs, and ACR from parameters with no hardcoded GCP project ids.
9. A documented, scripted (not executed) migration+cutover plan exists covering SQL dump, GCS->Blob copy, re-embed, parallel run, webhook swap, and post-sign-off teardown.
10. The Microsoft Graph importer ingests from SharePoint/OneDrive and skips duplicates by sha256, verified by a test or run on sample files.
11. A GCP-removal step is defined such that after owner sign-off the repo contains no google imports or GCP scripts/deps.

### Constraints
- No retrieval behavior regressions; existing pytest suite must keep passing.
- Reversible: GCP prod untouched until explicit cutover approval.
- No secrets in the repo.
- Match existing style: plain Python, pydantic-settings, SQLAlchemy 2.0.
- Target DB is Azure Database for PostgreSQL Flexible Server with pgvector (HNSW) and pg_trgm.
- pgvector HNSW cap is 2000 dims; embeddings must stay at 768.
- At most 10 in-scope items; every string field under 200 characters.
- FastAPI app, ~6k LOC Python; gunicorn+uvicorn on :8080.

### Research plan
- Topic: Migrate a FastAPI WhatsApp retrieval bot from GCP/Vertex to Azure with provider-neutral seams, reversibly
- Time range: last 18 months, prioritising current state as of Nov 2026
- Items:
  1. azure-openai-foundry-models | Current Azure OpenAI / Foundry models | Which current chat and vision models with structured JSON output replace the Gemini flash/pro router, OCR, and probe roles? | modules: general-web, github-debug
  2. azure-embeddings-768 | Shortened Azure embeddings to 768 dims | How to use text-embedding-3-large with dimensions=768 and confirm HNSW/Vector(768) compatibility and retrieval parity? | modules: general-web, stackoverflow
  3. azure-document-intelligence-ocr | OCR options for scanned papers | How does Azure AI Document Intelligence vs Azure OpenAI vision compare for OCR of scanned exam papers, and how to A/B gate it? | modules: general-web, academic-papers
  4. azure-postgres-pgvector | Azure Postgres Flexible Server pgvector/pg_trgm | How to enable pgvector HNSW and pg_trgm on Flexible Server and connect via managed identity/connection factory? | modules: general-web, stackoverflow
  5. container-apps-jobs-acr-bicep | Container Apps, Jobs, ACR via Bicep | How to parameterize Bicep for two Container Apps, two Jobs, ACR, Key Vault and managed identity in another subscription? | modules: general-web, github-debug
  6. keyvault-managed-identity-config | Key Vault + managed identity secrets loader | How to load secrets/config from Key Vault with managed identity in a pydantic-settings style without secrets in repo? | modules: general-web, stackoverflow
  7. graph-sharepoint-importer | Microsoft Graph SharePoint/OneDrive import | How to list and download files from SharePoint/OneDrive via Graph with app auth, preserving sha256 dedupe? | modules: general-web, github-debug
  8. gcs-sql-to-azure-migration | Data migration GCS->Blob, Cloud SQL->Azure PG | How to script Cloud SQL dump to Azure Postgres and GCS-to-Blob copy, plus Azure backup/restore drill, for a reversible cutover? | modules: general-web, stackoverflow
- Official docs to read:
  - Azure OpenAI Service
  - Microsoft Foundry (Azure AI Foundry)
  - Azure AI Document Intelligence
  - text-embedding-3-large
  - Azure Database for PostgreSQL Flexible Server
  - pgvector
  - pg_trgm
  - Azure Container Apps
  - Azure Container Apps Jobs
  - Azure Container Registry
  - Azure Key Vault
  - Azure Managed Identity
  - Bicep
  - Microsoft Graph API
  - SharePoint
  - OneDrive
  - Azure Blob Storage
  - FastAPI
  - SQLAlchemy 2.0
  - pydantic-settings
  - WhatsApp Business Platform / Cloud API
  - gunicorn
  - uvicorn
- Academic searches:
  - OCR accuracy large vision-language models scanned exam documents evaluation
  - dimensionality reduction text embeddings Matryoshka retrieval quality tradeoff
- Prior-art searches:
  - FastAPI Azure OpenAI structured output JSON response_schema example repo
  - pgvector HNSW Azure PostgreSQL Flexible Server sample
  - Azure Container Apps Jobs Bicep deployment example
  - Microsoft Graph SharePoint download files python sha256 dedupe
  - storage provider abstraction interface google cloud storage azure blob python

## Assumptions
- [risky] Links/paths referenced in the prompt (deploy.ps1, migrations, etc.) describe existing repo files I will inspect; I cannot open external links in the prompt, so none are guessed at.
- [risky] The storage/LLM/secrets/DB interfaces will be Python Protocol/ABC classes selected by a config/env flag choosing gcp vs azure.
- [risky] The A/B OCR gate and top-k parity thresholds are not numerically specified, so I will pick reasonable pass thresholds and record them for owner review.
- [risky] Azure OpenAI vision models can read the scanned papers; if the A/B gate fails, Azure AI Document Intelligence is the fallback OCR path.
- [risky] text-embedding-3-large at dimensions=768 is available in the school's Azure region; if not, a comparable 768-capable model is substituted.
- [risky] The school's Azure subscription, region, and Entra tenant details are unknown, so Bicep exposes them as parameters with placeholder defaults.
- [risky] Graph importer uses an app registration with application permissions (Sites.Read.All/Files.Read.All) rather than delegated user auth.
- [risky] Existing migrations (001, 002_phase2.sql) stay valid against Azure Postgres; the rename is an additive new migration keeping old columns until cutover.
- [risky] Pricing figures for new Azure models will be taken from public Azure pricing at build time and may need owner confirmation for negotiated rates.
- [safe] The 'review app' is the review/ web app and should be hosted as its own Azure Container App alongside the bot.
- [safe] WhatsApp integration uses the Meta WhatsApp Business Cloud API and stays unchanged except the eventual webhook URL swap.
- [safe] Container Apps (not AKS or App Service) is the intended Azure compute, matching the stated target, and scales to the bot's load.

## Recommended questions
- (none)

## Original request (authoritative)

The person's own words, unedited. Where anything above differs from this, this request wins.

> PHASE A of a multi-run migration: move the msa-paperbank bot (PAU past-paper retrieval bot, FastAPI, ~6k LOC Python) completely off Google Cloud / Vertex AI onto Azure, as part of an ownership transfer to the school (Microsoft 365 tenant). WhatsApp stays the only live channel in this phase. DECIDED DIRECTION for later runs: Teams will be a CUSTOM-ENGINE bot (own router, own Azure OpenAI models, billed on Azure; not Copilot Studio or a declarative agent), plus a Teams-only study companion and Entra SSO for the review app. Those are LATER runs; this phase only leaves clean seams (channel-agnostic handler core, retrieval callable independent of WhatsApp types).
>
> CURRENT GCP COUPLING (from the code)
> - Compute: Cloud Run (deploy.ps1, Makefile, Dockerfile, gunicorn+uvicorn :8080), review/ web app, cloud_ingest/ Cloud Run Job (cloudbuild.yaml, deploy.sh, teardown.sh), infra_bootstrap.sh, scripts/restore_drill.sh.
> - DB: Cloud SQL Postgres via cloud-sql-python-connector+pg8000 (app/db.py, apply_migrations.py, cloud_ingest/main.py, verify_db.py). Needs pgvector (HNSW, Vector(768)) and pg_trgm (migrations/002_phase2.sql).
> - Storage: google-cloud-storage imported directly in app/main.py, intake.py, retrieval.py, pdfgen.py, build_served_pdfs.py, review/main.py, admin/{batches,upload,curate,health}.py, scripts/upload_test_batch.py. DB columns are named gcs_object; config has gcs_bucket and several prefix settings.
> - Secrets: GCP Secret Manager (GCP_LOAD_FROM_SECRETS, *_FROM_SECRET) in app/config.py.
> - AI: google-genai vertexai=True in app/llm.py (router, vision OCR, page-boundary probe, contribution validation, masthead read; gemini flash/pro with response_schema JSON and thinking_budget=0), app/embeddings.py (gemini-embedding-001, 768-dim), app/ocr.py, admin/health.py, cloud_ingest/main.py; pricing in app/pricing.py and config price_* settings with a daily cost-cap breaker.
> - Corpus import: scripts/drive_import.py uses Google Drive.
> - Prod already exists on GCP (project 'ummah'); full ingest is gated on explicit owner go. Do not run ingest or modify/destroy any GCP prod resource.
>
> TARGET FOR PHASE A
> 1. Thin provider-neutral seams: storage interface (Blob impl, replacing direct google.cloud.storage use), LLM/vision/embedding interface in app/llm.py and app/embeddings.py (Azure OpenAI / Microsoft Foundry impl with structured JSON output), secrets/config loader (Key Vault + managed identity), DB connection factory (Azure Database for PostgreSQL Flexible Server with pgvector and pg_trgm). Rename gcs_* identifiers to neutral names via non-destructive migration.
> 2. Models: research must choose CURRENT Azure OpenAI / Foundry models (as of Nov 2026), not assume gpt-4o. About 90% of the corpus is scans, so vision OCR must pass an A/B gate on a sample of real papers against current Gemini output before any corpus re-ingest is approved; consider Azure AI Document Intelligence as an OCR alternative.
> 3. Embeddings: pgvector HNSW on the vector type is capped at 2000 dimensions, so use an Azure embedding model with shortened output (e.g. text-embedding-3-large with dimensions=768) so Vector(768) and the HNSW index stay unchanged. The vector space still changes: add a re-embed job and check parity with tests/test_retrieval*.py, test_embeddings.py and a before/after top-k comparison on a fixed query set.
> 4. Update pricing.py/config for the new models, keeping the daily cost-cap behavior.
> 5. Azure hosting: Container Apps for bot and review app, Container Apps Jobs for ingest and served-PDF backfill, ACR; parameterized Bicep so the school's subscription can stand it up; replace deploy.ps1/Makefile/cloud_ingest scripts; remove hardcoded GCP project ids.
> 6. GCP code path: keep a GCP implementation behind the interfaces ONLY until cutover is verified (parallel run, reversibility). Include a final step deleting all GCP code, dependencies and scripts after owner sign-off, so the end state has no google imports.
> 7. Data migration and cutover plan (documented and scripted, NOT executed): Cloud SQL dump to Azure Postgres, GCS to Blob copy, re-embed, parallel run, WhatsApp webhook swap, GCP teardown only after owner sign-off. Restore drill rewritten for Azure backups.
> 8. Replace Google Drive import with a Microsoft Graph (SharePoint/OneDrive) importer that keeps sha256 dedupe.
> 9. Handover docs: update README, RUNBOOK, LAUNCH for Azure.
>
> CONSTRAINTS
> - No retrieval behavior regressions; existing pytest suite must keep passing and new tests cover the storage/LLM/secrets abstractions.
> - Reversible: GCP prod untouched until explicit cutover approval. No secrets in the repo. Match existing style (plain Python, pydantic-settings, SQLAlchemy 2.0).
> - OUTPUT SIZE LIMITS for the plan: at most 10 in-scope items; every string field, including the research topic, under 200 characters.
