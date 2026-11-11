# Conventions

Stack, tools and conventions this project uses. One fact per line.

- Technologies/libraries this project documents and relies on: Azure OpenAI Service, Azure AI Foundry, text-embedding-3-large, Azure AI Document Intelligence, Azure Database for PostgreSQL Flexible Server, pgvector, pg_trgm, Azure Container Apps, Azure Container Apps Jobs,... _(run 1535cf46, 2026-11-11)_
- Constraint: Match existing style: plain Python, pydantic-settings, SQLAlchemy 2.0; keep pgvector HNSW Vector(768) and pg_trgm. _(run 1535cf46, 2026-11-11)_
- Constraint: No retrieval behavior regressions; existing pytest must keep passing; no secrets committed to the repo. _(run 1535cf46, 2026-11-11)_
- Constraint: GCP prod (project 'ummah') untouched and reversible until explicit cutover approval; parallel run before cutover. _(run 1535cf46, 2026-11-11)_
- Constraint: Plan output limits: at most 10 in-scope items; every string field under 200 characters. _(run 1535cf46, 2026-11-11)_
