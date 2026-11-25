# Baby PRD -- Migrate a FastAPI retrieval bot from GCP/Vertex to Azure: OpenAI/Foundry models, Postgres+pgvector, Container Apps, Graph import

## TL;DR
- We will move the WhatsApp past-paper bot off Google Cloud and rebuild it to run entirely on Microsoft Azure, ready for the school to own it.
- The bot keeps working the same way on WhatsApp; only the cloud plumbing underneath changes.
- We add swappable 'adapters' for storage, AI, secrets and database so Azure and Google versions can run side by side during the switch.
- Nothing in Google's live system is touched or deleted until the owner explicitly approves the cutover.
- You will know it worked when the existing automated tests still pass, the Azure version answers real questions, and search results match the old ones on a fixed set of queries.

## Scope
narrow

## Baby PRD

### Problem
The msa-paperbank bot is tightly coupled to Google Cloud/Vertex AI, blocking ownership transfer to a school that runs on Microsoft 365/Azure.

### Users / who it's for
The school taking ownership (Microsoft 365 tenant) and the maintainers; end users are PAU students querying past papers via WhatsApp.

### In scope
- Provider-neutral seams: storage (Blob), LLM/vision/embedding, secrets/config (Key Vault+managed identity), DB connection factory for Azure Postgres Flexible Server.
- Azure OpenAI/Foundry impl with structured JSON output behind the LLM interface; research selects current (Nov 2026) models, not gpt-4o.
- Vision OCR A/B gate on real scanned papers vs current Gemini before any re-ingest; evaluate Azure AI Document Intelligence as OCR alternative.
- Azure embedding with dimensions=768 so Vector(768) and HNSW index are unchanged; add re-embed job; parity check via tests and before/after top-k.
- Update pricing.py/config for new models, preserving the daily cost-cap breaker.
- Azure hosting via parameterized Bicep: Container Apps (bot, review), Container Apps Jobs (ingest, backfill), ACR; replace GCP deploy scripts; no hardcoded project ids.
- Non-destructive migration renaming gcs_* identifiers/columns to neutral names.
- Keep GCP impl behind interfaces for parallel run; final step deletes all GCP code/deps/scripts after owner sign-off (no google imports left).
- Documented, scripted-but-unexecuted data migration+cutover plan (SQL dump, Blob copy, re-embed, parallel run, webhook swap, teardown) + Azure restore drill.
- Microsoft Graph (SharePoint/OneDrive) importer replacing Drive import, preserving sha256 dedupe; update README/RUNBOOK/LAUNCH for Azure.

### Out of scope
- Teams custom-engine bot, Teams study companion, and Entra SSO for the review app (later runs; this phase only leaves clean seams).
- Executing the data migration, re-ingest, webhook swap, or GCP teardown (planned/scripted only, gated on owner approval).
- Modifying, destroying, or running ingest against any GCP prod resource (project 'ummah').
- Adding channels beyond WhatsApp; WhatsApp stays the only live channel this phase.
- Switching away from FastAPI, SQLAlchemy 2.0, pydantic-settings, pgvector(HNSW)/pg_trgm, or the Vector(768) schema.

### Acceptance criteria
1. The existing pytest suite passes unchanged against the Azure-backed configuration.
2. New tests exist and pass covering the storage, LLM/vision/embedding, and secrets/config abstractions.
3. No google.cloud, google-genai, vertexai, or cloud-sql-connector imports remain in the final (post-sign-off) codebase; dependency files list none.
4. grep of the repo finds no hardcoded GCP project ids and no plaintext secrets.
5. The handler core and retrieval callable can be invoked without importing WhatsApp-specific types.
6. An embedding call with the selected Azure model returns a 768-dimension vector; the DB column type and HNSW index definition are unchanged.
7. A before/after top-k comparison on a fixed query set is produced and its results are recorded for review.
8. The OCR A/B gate report comparing Azure OCR vs current Gemini on a sample of real scanned papers exists with a pass/fail verdict per sample.
9. `az deployment` using the Bicep templates with parameters provisions Container Apps, Container Apps Jobs, ACR, and Postgres Flexible Server in a fresh subscription.
10. The daily cost-cap breaker still triggers under the new pricing config (verifiable by a test that exceeds the cap).
11. README, RUNBOOK, and LAUNCH contain Azure deploy/operate steps and no GCP-only instructions, and the Azure restore drill script exists.

### Constraints
- Match existing style: plain Python, pydantic-settings, SQLAlchemy 2.0; keep pgvector HNSW Vector(768) and pg_trgm.
- No retrieval behavior regressions; existing pytest must keep passing; no secrets committed to the repo.
- GCP prod (project 'ummah') untouched and reversible until explicit cutover approval; parallel run before cutover.
- Plan output limits: at most 10 in-scope items; every string field under 200 characters.

### Research plan
- Topic: Migrate a FastAPI retrieval bot from GCP/Vertex to Azure: OpenAI/Foundry models, Postgres+pgvector, Container Apps, Graph import
- Time range: last 2 years (prioritise 2025-2026 current Azure offerings)
- Items:
  1. azure-openai-foundry-models | Current Azure OpenAI/Foundry models (Nov 2026) | Which current chat/vision models support structured JSON output and a thinking/reasoning budget equivalent, with pricing? | modules: general-web
  2. azure-structured-output | Structured JSON output on Azure OpenAI | How to enforce response_schema/JSON-mode and vision inputs via Azure OpenAI SDK to replace google-genai response_schema? | modules: general-web, stackoverflow
  3. azure-embeddings-768 | Azure embeddings shortened to 768 dims | How to call text-embedding-3-large (or current) with dimensions=768 and confirm HNSW<=2000 and Vector(768) parity? | modules: general-web, stackoverflow
  4. document-intelligence-ocr | Azure AI Document Intelligence vs LLM vision OCR | Accuracy/cost/API for scanned exam papers; how to A/B gate against Gemini OCR output on a sample? | modules: general-web, academic-papers
  5. postgres-flexible-pgvector | Azure Postgres Flexible Server pgvector+pg_trgm | Enabling pgvector/pg_trgm, HNSW support, connection via managed identity, and backup/restore drill mechanics? | modules: general-web, github-debug
  6. container-apps-bicep | Container Apps + Jobs + ACR via Bicep | Parameterized Bicep for web apps and jobs, ingress on 8080, managed identity, ACR pull; replacing Cloud Run scripts? | modules: general-web, github-debug
  7. keyvault-managed-identity | Key Vault + managed identity config loader | How to load secrets via Key Vault references/managed identity in Container Apps to replace GCP Secret Manager pattern? | modules: general-web, stackoverflow
  8. graph-sharepoint-import | Microsoft Graph SharePoint/OneDrive import | Graph API for listing/downloading drive files with auth and keeping sha256 dedupe, replacing Drive import? | modules: general-web, github-debug
- Official docs to read:
  - Azure OpenAI Service
  - Azure AI Foundry
  - text-embedding-3-large
  - Azure AI Document Intelligence
  - Azure Database for PostgreSQL Flexible Server
  - pgvector
  - pg_trgm
  - Azure Container Apps
  - Azure Container Apps Jobs
  - Azure Container Registry
  - Azure Key Vault
  - Azure Managed Identity
  - Microsoft Entra ID
  - Bicep
  - Microsoft Graph API
  - SharePoint
  - OneDrive
  - azure-storage-blob
  - azure-identity
  - FastAPI
  - SQLAlchemy
  - pydantic-settings
  - gunicorn
  - uvicorn
- Academic searches:
  - OCR accuracy evaluation scanned exam documents transformer vision models
  - document retrieval parity evaluation after embedding model change top-k overlap
- Prior-art searches:
  - FastAPI pgvector Azure PostgreSQL Flexible Server HNSW retrieval example
  - Azure Container Apps Bicep FastAPI gunicorn deployment template
  - Microsoft Graph SharePoint drive download Python sha256 dedupe
  - storage abstraction interface GCS Azure Blob Python adapter

## Assumptions
- [risky] The OCR A/B gate pass threshold (e.g. accuracy within a tolerance of Gemini) is unspecified; a concrete threshold will be defined in the gate report for owner review.
- [risky] The Azure region/tier and Postgres Flexible Server SKU are not specified; a cost-reasonable default matching data-residency norms will be chosen and parameterized in Bicep.
- [risky] Work stays in the single existing repo with GCP and Azure impls coexisting behind interfaces until the final deletion step.
- [risky] The chosen Azure chat model's structured-output/reasoning-budget features will be mapped to the nearest equivalent of Gemini's response_schema and thinking_budget=0.
- [safe] The prompt contains no external links to open; none were provided, so no link content was assumed or fetched.
- [safe] Managed identity will be user-assigned where shared across resources, system-assigned otherwise.
- [safe] The fixed query set for the before/after top-k parity check will be newly curated from representative past-paper queries since none is provided.
- [safe] Blob storage uses a standard general-purpose v2 account with default redundancy unless parameters override.

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
