# Conventions

Stack, tools and conventions this project uses. One fact per line.

- Technologies/libraries this project documents and relies on: Azure OpenAI Service, Azure AI Foundry, text-embedding-3-large, Azure AI Document Intelligence, Azure Database for PostgreSQL Flexible Server, pgvector, pg_trgm, Azure Container Apps, Azure Container Apps Jobs,... _(run 1535cf46, 2026-11-11)_
- Constraint: Match existing style: plain Python, pydantic-settings, SQLAlchemy 2.0; keep pgvector HNSW Vector(768) and pg_trgm. _(run 1535cf46, 2026-11-11)_
- Constraint: No retrieval behavior regressions; existing pytest must keep passing; no secrets committed to the repo. _(run 1535cf46, 2026-11-11)_
- Constraint: GCP prod (project 'ummah') untouched and reversible until explicit cutover approval; parallel run before cutover. _(run 1535cf46, 2026-11-11)_
- Constraint: Plan output limits: at most 10 in-scope items; every string field under 200 characters. _(run 1535cf46, 2026-11-11)_
- Technologies/libraries this project documents and relies on: FastAPI, SQLAlchemy 2.0, pydantic-settings, pgvector, pg_trgm, PostgreSQL, Docker Compose, MinIO, sentence-transformers, ONNX Runtime, Hugging Face Transformers, Meta WhatsApp Cloud API, Model Context Protocol... _(run ef877dec, 2026-11-11)_
- Constraint: Python 3.12; keep FastAPI, SQLAlchemy 2.0, pydantic-settings, pgvector, pg_trgm. _(run ef877dec, 2026-11-11)_
- Constraint: Existing pytest suite must keep passing; no network calls in unit tests. _(run ef877dec, 2026-11-11)_
- Constraint: No secrets committed to the repository. _(run ef877dec, 2026-11-11)_
- Constraint: Backend has no LLM or model API dependency; runs in Docker Compose on no-GPU school Linux servers. _(run ef877dec, 2026-11-11)_
- Constraint: Embeddings are 768-dimension from a local CPU model; Vector(768) schema and HNSW index stay. _(run ef877dec, 2026-11-11)_
- Technologies/libraries this project documents and relies on: FastAPI, Starlette, Pydantic, Python standard library (mimetypes), Python standard library (os.path / posixpath), Microsoft Copilot Studio, OpenAPI Specification, Swagger 2.0 _(run 3ff2966e, 2026-11-16)_
- Constraint: Edit only app/main.py and the tests; touch nothing else and do not modify spike/copilot-studio/. _(run 3ff2966e, 2026-11-16)_
- Constraint: No new dependencies (standard library only for mimetype lookup and sanitising). _(run 3ff2966e, 2026-11-16)_
- Constraint: No secrets and no GCP references anywhere in the changes. _(run 3ff2966e, 2026-11-16)_
- Constraint: Target Python 3.12. _(run 3ff2966e, 2026-11-16)_
- Constraint: Existing tests must keep passing unchanged. _(run 3ff2966e, 2026-11-16)_
