# Research report -- Migrating a FastAPI/SQLAlchemy/pgvector retrieval bot off GCP+Vertex to self-hosted Docker with a local CPU embedder

Generated 2026-11-11T08:14:27.363Z by OSA. Researched by claude-code using its built-in web search. Time range: last 3 years.
Values marked [uncertain] could not be verified from a source the agent opened; they are repeated under *Open uncertainties*.

## Findings

### Official documentation: FastAPI
*Find the OFFICIAL documentation for "FastAPI": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

FastAPI is a modern async Python web framework built on Starlette and Pydantic, installed via `pip install "fastapi[standard]"`, currently at stable version 0.162.4 (released 2026-11-10 per PyPI) requiring Python >=3.10. This build will use its core routing decorators, Pydantic-model request/response validation, the `Depends()` dependency-injection system to wire swappable provider ports (ObjectStore/Embedder/Secrets/DB engine), and the `lifespan` async-context-manager pattern for startup/shutdown of DB engine and embedder resources. The main historical pitfall relevant here is the Pydantic v1→v2 migration at FastAPI 0.100.0 (2023-07-07) and a 0.106.0 (2023-12-25) change affecting dependencies-with-yield/HTTPException/BackgroundTasks interaction, both of which predate and are compatible with this build's target of FastAPI + Pydantic v2 + SQLAlchemy 2.0.

**Key findings**
- Current stable FastAPI version is 0.162.4, released 2026-11-10 (PyPI), requiring Python >=3.10 and supporting up through Python 3.15.
- Official install command is `pip install "fastapi[standard]"` (or `uv add "fastapi[standard]"`), which bundles Uvicorn, Pydantic, Jinja2, and python-multipart.
- Dependency injection uses `Depends()` with plain or `Annotated[...]` type aliases; dependencies can be sync or async functions or classes and can be nested (sub-dependencies), making them suitable for swappable provider ports.
- Startup/shutdown resource management is done via the `lifespan` async-context-manager parameter passed to `FastAPI(lifespan=...)`; code before `yield` runs at startup, code after `yield` runs at shutdown.
- The older `@app.on_event("startup"/"shutdown")` decorators are explicitly deprecated in official docs in favor of `lifespan`, and the docs warn the two mechanisms must not be mixed on the same app.
- FastAPI 0.100.0 (2023-07-07) was the major release moving to full Pydantic v2 support, with an official migration guide noted in the release notes.
- FastAPI 0.106.0 (2023-12-25) made a breaking change titled "Dependencies with yield, HTTPException and Background Tasks"; the release-notes page confirms this heading but the fetched excerpt did not render the full technical description [uncertain].
- FastAPI 0.115.0 (2024-09-17) added Query/Header/Cookie Parameter Models and the ability to forbid extra query/cookie/header parameters.
- Lifespan events only execute for the main ASGI app, not for mounted sub-applications, per the official advanced/events docs.

**Recommendations**
- Use `Depends()` with class-based dependencies (one class per port: ObjectStore, Embedder, SecretsProvider, DB engine/session) so the GCP and local implementations can be swapped via a provider setting without touching route or callable signatures.
- Manage the DB engine, embedder model load, and any object-store client via the `lifespan` async-context-manager on the FastAPI app instance, not the deprecated `on_event` hooks, to guarantee clean startup/shutdown ordering for Docker health checks.
- Keep provider classes free of request/response or WhatsApp-specific types so `handle_inbound` and the retrieval callable only depend on the port interfaces, satisfying the channel-neutral handler requirement.
- Pin an exact FastAPI version in requirements rather than a loose range, since the project releases frequently (multiple versions per month) and breaking-change clusters have occurred; re-run the pytest suite after any FastAPI bump.
- Verify the exact technical detail of the FastAPI 0.106.0 yield/HTTPException/BackgroundTasks change directly against the target pinned version's release notes before relying on dependency-with-yield error handling in the ObjectStore or DB session ports.

**current version:** 0.162.4 (released 2026-11-10 per PyPI)

**api surface**
- FastAPI(lifespan=...) app instantiation for managed DB engine/embedder/object-store client startup and shutdown
- @app.get/post/put/delete path operation decorators with Pydantic BaseModel request/response bodies
- Depends() dependency injection, including Annotated[...] type aliases and class-based dependencies for provider ports
- APIRouter for modular route organization (e.g., separating channel adapters from core handler)
- Automatic OpenAPI/Swagger UI generation for the single REST tool call surface needed by a future agent

**pitfalls**
- FastAPI 0.100.0 (2023-07-07) required migrating fully to Pydantic v2; mixed v1/v2 model usage from older code must be checked.
- FastAPI 0.106.0 (2023-12-25) changed behavior of dependencies-with-yield combined with HTTPException and BackgroundTasks; exact mechanics were not directly confirmed from the fetched excerpt [uncertain].
- The on_event("startup"/"shutdown") decorators are deprecated in favor of lifespan context managers and the two must not be combined on one app.
- Lifespan context managers do not run for mounted sub-applications, which matters if a future Teams/MCP adapter is mounted as a sub-app rather than routed through the main app.
- Frequent, rapid point releases (multiple per month, several marked 'breaking changes' through 2026) mean unpinned FastAPI versions risk silent behavior changes between CI runs.

*As of: 2026-11-10 (PyPI release date for FastAPI 0.162.4); FastAPI official docs and release notes as currently published*

**Sources**
- [FastAPI (official docs homepage)](https://fastapi.tiangolo.com/) (official-docs) -- "pip install "fastapi[standard]" ... FastAPI framework, high performance, easy to learn, fast to code, ready for production"
- [FastAPI Release Notes](https://fastapi.tiangolo.com/release-notes/) (official-docs) -- "0.106.0 ... Breaking Changes ... Dependencies with yield, HTTPException and Background Tasks"
- [fastapi · PyPI](https://pypi.org/project/fastapi/) (official-docs) -- "0.162.4 ... Requires: Python >=3.10"
- [FastAPI Tutorial - Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) (official-docs) -- "async def common_parameters(q: str | None = None, skip: int = 0, limit: int = 100): return {"q": q, "skip": skip, "limit": limit}"
- [FastAPI Advanced - Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) (official-docs) -- "If you use lifespan, startup and shutdown event handlers won't be called. Use one approach or the other, not both."


### Official documentation: SQLAlchemy 2.0
*Find the OFFICIAL documentation for "SQLAlchemy 2.0": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

The official SQLAlchemy docs confirm 2.0 is now the 'legacy version' maintenance series (latest patch 2.0.57, Nov 3 2026), with 2.1 (2.1.8) as the new current line; the build's constraint to 'keep SQLAlchemy 2.0' means pinning to the 2.0.x maintenance branch rather than the newer 2.1 line. The 2.0 ORM API this build needs is stable: Mapped/mapped_column typed declarative models, Session.execute(select(...)) with .scalars()/.scalars().all(), Session.get(), and synonym() for the reversible gcs_* column rename. No further breaking changes are expected within 2.0.x since it is in maintenance-only mode; the only breaking-change risk is the 1.4→2.0 migration semantics (Query vs select(), removed implicit autocommit), which are well documented and stable as of this writing.

**Key findings**
- Official docs header on docs.sqlalchemy.org/en/20/ marks the series as 'Release: 2.0.57 legacy version | Release Date: November 3, 2026'; docs.sqlalchemy.org/en/20/changelog/whatsnew_20.html confirms 2.0 is now 'Maintenance Release (2.0)' while 2.1 is 'Current Documentation'.
- sqlalchemy.org/download.html lists current overall stable as 2.1.8 (Nov 4, 2026); the build's own constraint pins to the 2.0 line, so 2.0.57 is the version to target, not 2.1.
- synonym() signature per docs.sqlalchemy.org/en/20/orm/mapped_attributes.html: sqlalchemy.orm.synonym(name, *, map_column=None, descriptor=None, comparator_factory=None, info=None, doc=None, ...) -> Synonym[Any]; usage: `status = synonym("job_status")` makes `status` mirror the value/expression behavior of the real mapped column, directly matching the gcs_* rename requirement.
- 2.0 ORM query style (docs.sqlalchemy.org/en/20/orm/queryguide/select.html): construct with select(Model), execute via session.execute(stmt) (returns Row tuples) or session.scalars(stmt) (returns entities directly); `.all()` materializes results; async usage is identical API via AsyncSession with await.
- Migration guide (docs.sqlalchemy.org/en/20/changelog/migration_20.html) states Query becomes a long-term legacy object replaced by select(); session.query(Model).get(id) becomes session.get(Model, id); engine-level autocommit/connectionless execution and Session.autocommit are removed; recommends running 1.4 with SQLALCHEMY_WARN_20=1 first to surface 2.0-incompatible patterns before upgrading.
- Declarative imports moved from sqlalchemy.ext.declarative to sqlalchemy.orm (declarative_base, declared_attr); models using plain type annotations without Mapped[] need `__allow_unmapped__ = True` on the base class to avoid mapping errors under 2.0's stricter typing.
- Doc notes hybrid_property is generally preferred over synonym() for new code with custom getter/setter logic, but synonym() is explicitly still supported and is the documented mechanism for attribute aliasing — appropriate for the reversible gcs_* rename.

**Recommendations**
- Pin the dependency to the SQLAlchemy 2.0.x maintenance line (e.g. sqlalchemy~=2.0.57) rather than upgrading to 2.1, consistent with the build's 'keep SQLAlchemy 2.0' constraint; 2.1 is a separate major line with its own migration guide and should not be adopted in this migration.
- Implement the gcs_* rename using `new_name = synonym("gcs_name")` (or vice versa) so both the legacy and provider-neutral attribute names resolve to the same mapped column — this is the exact reversible mechanism acceptance criterion 5 requires.
- Use 2.0-style select()/Session.execute()/session.scalars() throughout any new or touched retrieval code rather than the legacy Query API, since Query is a long-term legacy object in 2.0 and the codebase should not introduce new legacy-style calls during this migration.
- If any existing code still uses sqlalchemy.ext.declarative or implicit autocommit/connectionless engine.execute(), fix those during Phase 1 since they are removed in 2.0 — but only touch what is already broken or directly in scope, not unrelated 1.4-era patterns.
- Do not block on or plan around SQLAlchemy 2.1 features; treat 2.1 docs/changelog as out of scope for this build.

**current version:** 2.0.57 (legacy/maintenance line this build targets); overall project current stable is 2.1.8 but out of scope per build constraints

**api surface**
- sqlalchemy.orm.Mapped[...] / mapped_column(...) for typed declarative model columns
- sqlalchemy.orm.synonym(name, ...) for the reversible gcs_* attribute rename
- sqlalchemy.select(Model).where(...) built as a Select construct
- Session.execute(stmt) returning Row tuples; Session.scalars(stmt).all() returning ORM entities directly
- Session.get(Model, id) replacing legacy Query.get()
- engine.begin() / conn.begin() context managers for explicit transactions (autocommit removed)
- sqlalchemy.orm.declarative_base / declared_attr imported from sqlalchemy.orm (not sqlalchemy.ext.declarative)
- AsyncSession.execute(stmt) with await, same method names as sync Session, for any async FastAPI retrieval paths

**pitfalls**
- SQLAlchemy 2.0 is now the maintenance/legacy line as of the docs checked (Nov 2026); the actively developed current line is 2.1 — pin explicitly to avoid an unintended major-version drift.
- session.query(Model) is legacy; mixing it with select()/scalars() style in the same codebase is allowed but the docs mark Query as long-term-legacy, so new/modified code should use select().
- engine-level autocommit and connectionless execution (engine.execute()) were removed in 2.0 — any lingering 1.4-era calls will fail outright.
- Models using plain (non-Mapped) type annotations will raise mapping errors under 2.0 unless the base class sets __allow_unmapped__ = True.
- joinedload()-based collection results are not auto-deduplicated in 2.0 ORM-execute mode; call .unique() when needed to avoid subtly wrong result sets during the search parity comparison (acceptance criterion 9).
- hybrid_property is the documented preferred alternative to synonym() for anything beyond a simple name alias — use synonym() specifically because it is the minimal, reversible option for the gcs_* rename, not for new general-purpose aliasing.

*As of: 2026-11-11 (docs reflect SQLAlchemy 2.0.57, legacy/maintenance release dated 2026-11-03; current overall stable line is 2.1.8 per sqlalchemy.org/download.html)*

**Sources**
- [SQLAlchemy 2.0 Documentation (en/20 index)](https://docs.sqlalchemy.org/en/20/) (official-docs) -- "Release: 2.0.57 legacy version | Release Date: November 3, 2026"
- [What's New in SQLAlchemy 2.0? — SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/changelog/whatsnew_20.html) (official-docs) -- "Maintenance Release (2.0) ... Current Documentation (version 2.1)"
- [SQLAlchemy 2.0 - Major Migration Guide — SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html) (official-docs) -- "The Query object becomes a long term legacy object...replaced by the direct usage of the select() construct"
- [Changing Attribute Behavior — SQLAlchemy 2.0 Documentation (mapped_attributes)](https://docs.sqlalchemy.org/en/20/orm/mapped_attributes.html) (official-docs) -- "Denote an attribute name as a synonym to a mapped property, in that the attribute will mirror the value and expression behavior of another attribute."
- [ORM Querying Guide: Using SELECT statements — SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html) (official-docs) -- "when selecting a list of single-element rows containing ORM entities, it is typical to skip the generation of Row objects"
- [Download - SQLAlchemy](https://www.sqlalchemy.org/download.html) (official-docs) -- "current stable release is SQLAlchemy 2.1.8, released on November 4, 2026"
- [SQLAlchemy ORM Mapping API](https://docs.sqlalchemy.org/en/20/orm/mapping_api.html) (official-docs) -- "synonym_for() ... Decorator that produces a synonym() attribute in conjunction with a Python descriptor."


### Official documentation: pydantic-settings
*Find the OFFICIAL documentation for "pydantic-settings": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

pydantic-settings is the official Pydantic v2 companion package providing BaseSettings, which loads strongly-typed config from env vars, .env files, secrets files/dirs (e.g. Docker secrets at /run/secrets), and other sources, with precedence init > env > dotenv > secrets. Current stable release is 2.16.2, requiring Python >=3.11 and pydantic>=2.7.0, matching this build's Python 3.12/pydantic-settings stack. For this project, use SettingsConfigDict with env_prefix, env_nested_delimiter, and secrets_dir to back the new ObjectStore/Embedder/Secrets/DB provider ports while keeping the existing GCP_* env var names resolvable via validation_alias/AliasChoices, satisfying the requirement that pre-existing env variable names still resolve after the gcs_* rename.

**Key findings**
- Current stable version is 2.16.2 (confirmed from pydantic_settings/version.py in the main branch of the official GitHub repo).
- pyproject.toml on main specifies requires-python = '>=3.11' and pydantic>=2.7.0 as the core dependency.
- Install via `pip install pydantic-settings`; BaseSettings and SettingsConfigDict are the primary public API (SettingsConfigDict replaces the legacy inner Config class from pydantic v1 style).
- Source precedence order is: init arguments > environment variables > dotenv (.env) file variables > secrets directory variables > default field values.
- secrets_dir (e.g. SettingsConfigDict(secrets_dir='/run/secrets')) reads one secret per file, with the filename treated as the field/env name -- directly maps onto Docker/Compose secrets for the 'ports for secrets, selectable by provider' requirement.
- env_nested_delimiter (e.g. '__') allows flattening nested Pydantic models from env vars, useful for grouping provider-specific settings (e.g. OBJECTSTORE__BUCKET).
- validation_alias plus AliasChoices lets a single field accept multiple historical env var names (e.g. Field(validation_alias=AliasChoices('GCS_BUCKET', 'OBJECT_STORE_BUCKET'))), which is the mechanism to keep old GCP_*/gcs_* env names resolving after a rename.
- settings_customise_sources() can be overridden to add or reorder custom settings sources (e.g. a secrets-manager source), relevant if a future provider needs a non-file secrets backend.
- v2.16.0 (most recent minor) dropped Python 3.10 support (now 3.11+ only) and bumped the required python-dotenv to >=1.2.2 to address a CVE; also changed alias precedence semantics (validation_alias now takes precedence over alias in file/CLI sources) and made JSON/YAML config files read as UTF-8 by default instead of locale encoding. [uncertain: exact release date/version attribution for this change log, since two fetches of the GitHub releases page gave conflicting dates for the same version]
- BaseSettings validates default values by default (unlike BaseModel), controllable via validate_default=False -- worth noting since it can surprise tests if required-looking defaults silently fail validation.

**Recommendations**
- Pin pydantic-settings to 2.16.2 (or the latest 2.16.x) alongside pydantic>=2.7.0, both compatible with the project's Python 3.12 requirement.
- Define one SettingsConfigDict-based Settings class per provider port (ObjectStore, Embedder, Secrets, DBEngine) or a composed settings object with env_prefix per section, so each provider's config is swappable via a 'provider' field (e.g. object_store_provider: Literal['gcs','local','minio']).
- Use validation_alias=AliasChoices(...) on renamed fields so legacy GCS_* / gcs_* env var names keep resolving after the SQLAlchemy synonym rename, satisfying acceptance criterion 5 at the settings layer too.
- Use secrets_dir='/run/secrets' (or a configurable path) for the Secrets port in Docker Compose, so no plaintext DB password or GCP project id needs to live in env files or the Dockerfile, satisfying acceptance criterion 7.
- Avoid hand-rolling .env parsing or os.environ lookups elsewhere in the codebase; centralize all config access through the pydantic-settings Settings object so unit tests can inject values via init kwargs (no network/env dependency), supporting the 'no network calls in unit tests' criterion.
- Do not rely on Python 3.10-era assumptions or pre-2.7 pydantic patterns; verify CI/Docker base images use Python 3.11+ to satisfy pydantic-settings' own requires-python floor.

**current version:** 2.16.2

**api surface**
- BaseSettings (base class for all settings models)
- SettingsConfigDict(env_prefix=..., env_nested_delimiter=..., secrets_dir=..., case_sensitive=..., env_file=...)
- pydantic.Field(validation_alias=AliasChoices('OLD_NAME','NEW_NAME'))
- settings_customise_sources() override for custom/ordered settings sources
- secrets_dir / Docker secrets file-based loading (/run/secrets)
- env_nested_delimiter for nested provider-config models

**pitfalls**
- Python 3.10 support dropped as of the 2.16.x line; minimum is now Python 3.11, so Docker base images must be 3.11+ (project targets 3.12, which is fine).
- BaseSettings validates default values by default, unlike plain BaseModel -- can cause unexpected validation errors on fields with 'unsafe' defaults unless validate_default=False is set.
- Alias precedence semantics changed across 2.15/2.16: validate_by_alias=False now causes aliases to be ignored across all sources, and validation_alias now takes precedence over plain alias in file/CLI sources -- verify behavior explicitly with a test when relying on AliasChoices for legacy GCS_* env names.
- Case-sensitivity default changed in 2.15.0 for InitSettingsSource and config-file sources (now case-insensitive by default) -- could silently change matching behavior for renamed env vars if not pinned/tested.
- [uncertain] Exact release dates for 2.16.x versions were inconsistent between two independent fetches of the GitHub releases page (PyPI listed 2.16.2 as Oct 28, 2026; a GitHub releases summary listed it as Nov 6, 2024) -- treat specific dates as unverified; only the version number and changelog content claims were cross-checked against source files.

*As of: 2.16.2, verified against pydantic_settings/version.py on the main branch, accessed 2026-11-11*

**Sources**
- [Settings Management — Pydantic documentation](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/) (official-docs) -- "BaseSettings... allowing values to be overridden by environment variables... Priority order: init arguments > environment variables > dotenv files > secrets files"
- [pydantic-settings docs/index.md (GitHub, main branch)](https://github.com/pydantic/pydantic-settings/blob/main/docs/index.md) (official-docs) -- "pip install pydantic-settings"
- [pydantic-settings pyproject.toml (GitHub, main branch)](https://raw.githubusercontent.com/pydantic/pydantic-settings/main/pyproject.toml) (repo) -- "requires-python = '>=3.11' ... pydantic>=2.7.0"
- [pydantic_settings/version.py (GitHub, main branch)](https://raw.githubusercontent.com/pydantic/pydantic-settings/main/pydantic_settings/version.py) (repo) -- "VERSION = '2.16.2'"
- [pydantic-settings releases](https://github.com/pydantic/pydantic-settings/releases) (repo) -- "Python 3.10 is no longer supported; python-dotenv>=1.2.2 is now required"
- [pydantic-settings · PyPI](https://pypi.org/project/pydantic-settings/) (official-docs) -- "Current Version: 2.16.2"


### Official documentation: pgvector
*Find the OFFICIAL documentation for "pgvector": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

pgvector is the official Postgres extension providing vector similarity search; current stable release is v0.8.7 (2026-10-01), with a `vector(n)` type supporting up to 16,000 dimensions, L2/inner-product/cosine distance operators, and both HNSW and IVFFlat approximate-index types. The build's Vector(768) + HNSW index usage is squarely within supported limits and stable API territory. Official Docker images (`pgvector/pgvector:<ver>-pg<major>-<debian-codename>`) are published per Postgres major version and are the simplest path for the school's no-GPU Linux servers. The only breaking changes in the last 3 years are dropped support for old Postgres majors (12, then 13/14 in the unreleased 0.9.0) and some HNSW/IVFFlat vacuuming bug fixes — nothing affects the `vector(768)` + HNSW code path this build relies on.

**Key findings**
- Current stable release: v0.8.7, released 2026-10-01, per the GitHub CHANGELOG.md.
- Enable via `CREATE EXTENSION vector;` after installing the extension binary (apt: `postgresql-<ver>-pgvector`, source build, or Docker image).
- `vector(n)` column type supports up to 16,000 dimensions for storage; HNSW indexing of plain `vector` is practically limited to 2,000 dimensions per the README (768 is well within this limit).
- HNSW index type was added in v0.5.0 (2023-08-28) — this is the index type the build retains unchanged.
- v0.7.0 (2024-04-29) added `halfvec`, `sparsevec`, bit-vector Hamming/Jaccard distances — not used by this build but confirms the extension has actively evolved in-range.
- v0.8.0 (2024-10-30) added iterative index scans and dropped support for Postgres 12 (breaking change for anyone on PG12).
- Unreleased v0.9.0 will drop support for Postgres 13 and 14 — relevant only if the school picks an old Postgres major.
- Official Docker images are published as `pgvector/pgvector:<version>-pg<major>-<debian-codename>` (e.g. `0.8.7-pg18-trixie`), confirmed on Docker Hub.
- Distance operators relevant to this build: `<->` (L2), `<#>` (negative inner product), `<=>` (cosine) — cosine is the typical choice for embedding similarity search.
- Index creation syntax used by this build: `CREATE INDEX ON items USING hnsw (embedding vector_cosine_ops);` (or `vector_l2_ops` depending on chosen distance metric) — operator class must match the query's distance operator or the index won't be used.
- NULL and zero vectors are not indexed by HNSW/IVFFlat (zero vectors specifically excluded for cosine distance) — relevant if any chunk/title ends up with an empty embedding.

**Recommendations**
- Pin an explicit pgvector version in the Dockerfile/compose (e.g. `pgvector/pgvector:0.8.7-pg16-<codename>` or whichever Postgres major the project already uses) rather than tracking `latest`, since minor releases have included index-build bug fixes that matter for data integrity.
- Create the HNSW index with the operator class matching the distance operator actually used in queries (e.g. `vector_cosine_ops` if using `<=>`), and verify queries use `ORDER BY embedding <=> $1 LIMIT k` so the planner uses the index.
- Keep `Vector(768)` as-is — 768 dimensions is well under both the 16,000 storage limit and the ~2,000 practical HNSW indexing limit, so no schema or index-type change is required for parity acceptance criterion #8.
- Before the parity/re-embed job (criterion #9), confirm no chunk or title embedding is a zero/NULL vector, since those rows silently won't be indexed and would skew a before/after top-k comparison.
- If picking the Postgres major for self-hosting, avoid Postgres 12 (unsupported since pgvector 0.8.0) and be aware that a future pgvector 0.9.0 will drop 13/14 — prefer Postgres 15+ for longevity.
- pg_trgm (needed per the build's constraints) is a standard Postgres contrib module distributed with Postgres itself, not part of pgvector — enable separately with `CREATE EXTENSION pg_trgm;`; verify it's present in whichever base Postgres image is chosen. [uncertain]

**current version:** 0.8.7 (released 2026-10-01); 0.9.0 unreleased/in development

**api surface**
- CREATE EXTENSION vector;
- vector(768) column type
- CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) [or vector_l2_ops to match distance metric]
- Distance operators: <-> (L2), <#> (negative inner product), <=> (cosine)
- ORDER BY embedding <=> query_vector LIMIT k (index-eligible query pattern)
- Standard Postgres: CREATE EXTENSION pg_trgm; (separate contrib module, not pgvector itself)

**pitfalls**
- pgvector 0.8.0 (2024-10-30) dropped support for Postgres 12 — breaking for anyone on that major.
- Unreleased pgvector 0.9.0 will drop support for Postgres 13 and 14 — a forward-looking constraint when choosing the self-hosted Postgres version.
- Multiple 2025-2026 patch releases (0.8.2 through 0.8.7) fixed buffer overflows and index-corruption bugs in HNSW/IVFFlat builds — pin a recent patch version rather than an old 0.8.x.
- Index usage requires the query's ORDER BY distance operator and operator class to match; mismatches silently fall back to sequential scan.
- NULL vectors are never indexed, and zero vectors are excluded from indexing specifically for cosine distance — can cause silent gaps in HNSW recall if any embedding is zero/null.
- Standard `vector` type HNSW indexing is effectively capped around 2,000 dimensions per the README despite the type supporting storage up to 16,000 — not a concern for this build's 768-dim vectors but a relevant ceiling if dimensions ever change.

*As of: 2026-11 (pgvector v0.8.7, released 2026-10-01)*

**Sources**
- [pgvector/pgvector GitHub README](https://github.com/pgvector/pgvector) (official-docs) -- "CREATE EXTENSION vector; ... CREATE INDEX ON items USING hnsw (embedding vector_l2_ops);"
- [pgvector CHANGELOG.md](https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md) (official-docs) -- "0.5.0 (2023-08-28) Added HNSW index type ... 0.8.0 (2024-10-30) Dropped support for Postgres 12"
- [pgvector/pgvector Docker Hub page](https://hub.docker.com/r/pgvector/pgvector) (official-docs) -- "docker pull pgvector/pgvector:0.8.7-pg18-trixie"


### Official documentation: pg_trgm
*Find the OFFICIAL documentation for "pg_trgm": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

pg_trgm is a trusted PostgreSQL contrib extension providing trigram-based text similarity functions, operators, and GiST/GIN index operator classes; it is enabled per-database with `CREATE EXTENSION pg_trgm` and does not require superuser privileges. The current official docs (PostgreSQL 18, with the module also documented identically for 14-17) show stable API surface: similarity()/word_similarity()/strict_word_similarity() functions, the %, <->, <%, %>, <<%, %>> operators, and gin_trgm_ops/gist_trgm_ops index classes, configurable via pg_trgm.similarity_threshold and related GUCs. No breaking API changes occurred in the last 3 years; the main relevant event was a security/bug fix (CVE-2026-14678) in the GiST picksplit function patched in e.g. PostgreSQL 16.15, which could cause bad index splits or crashes on affected point releases. For this build, pg_trgm is used for trigram similarity/fuzzy matching alongside pgvector HNSW search, and the pre-existing GIN/GiST trigram index and extension declaration should carry over unchanged into the Dockerized Postgres image.

**Key findings**
- Official docs confirm pg_trgm is enabled via `CREATE EXTENSION pg_trgm;` and is a 'trusted' extension installable by non-superusers with CREATE privilege on the database (verified on postgresql.org/docs/current/pgtrgm.html, PostgreSQL 18 docs).
- Core functions per official docs (PG17/PG18): similarity(text,text)->real, word_similarity(text,text)->real, strict_word_similarity(text,text)->real, show_trgm(text)->text[]; show_limit()/set_limit() exist but are documented as deprecated in favor of the pg_trgm.similarity_threshold GUC.
- Operators per official docs: % (similarity threshold), <-> (distance), <%/%> (word similarity), <<-> / <->> (word similarity distance), <<%/%>> (strict word similarity), <<<-> / <->>> (strict word similarity distance).
- GUC parameters with documented defaults: pg_trgm.similarity_threshold = 0.3, pg_trgm.word_similarity_threshold = 0.6, pg_trgm.strict_word_similarity_threshold = 0.5.
- Index support is via GiST (gist_trgm_ops, optional siglen parameter) or GIN (gin_trgm_ops) operator classes, both of which also accelerate LIKE/ILIKE/regex (~ , ~*) and equality, in addition to similarity operators.
- The documented API surface (functions, operators, GUCs) is identical across PostgreSQL 14 through 18 per the official docs pages opened for versions 17 and current/18 -- no breaking changes to pg_trgm's SQL-level interface in this window.
- A confirmed security/bug fix exists: PostgreSQL 16.15 release notes (opened directly) document 'Fix datatype error in contrib/pg_trgm's GiST picksplit function... reading past the end of the buffer, typically causing bad split decisions; but a crash could ensue if very unlucky' (CVE-2026-14678). This affects pg_trgm GiST indexes on unpatched point releases prior to the fix.

**Recommendations**
- Declare `CREATE EXTENSION IF NOT EXISTS pg_trgm;` in the Docker-based migration/init scripts alongside pgvector and pg_trgm requires no superuser, so it is safe to run as part of normal app migrations in Compose.
- Pin the self-hosted Postgres Docker image to a patched point release (>=16.15, or the corresponding patched 17.x/18.x/15.x/14.x) to avoid the GiST picksplit bug (CVE-2026-14678) affecting pg_trgm GiST indexes.
- If the existing schema uses a GiST trigram index, prefer GIN (gin_trgm_ops) for the new self-hosted deployment if index build time/update throughput allow, since GIN is generally faster for static/batch-loaded text and was not implicated in the picksplit CVE; otherwise simply ensure the patched Postgres version is used.
- Do not rely on the deprecated show_limit()/set_limit() functions in new code; use `SET pg_trgm.similarity_threshold = ...` instead, matching current official documentation.
- Since pg_trgm's API surface has been stable for 3+ years, no migration risk is expected for this extension itself -- scope the Phase 1/2 migration risk to pgvector/HNSW and GCP removal, not pg_trgm.

**current version:** pg_trgm as documented for PostgreSQL 18 (current stable); same API surface documented unchanged back through PostgreSQL 14

**api surface**
- CREATE EXTENSION IF NOT EXISTS pg_trgm;
- similarity(text, text) -> real
- word_similarity(text, text) -> real
- strict_word_similarity(text, text) -> real
- Operators: %, <->, <%, %>, <<%, %>>
- CREATE INDEX ... USING GIN (col gin_trgm_ops) / USING GIST (col gist_trgm_ops)
- SET pg_trgm.similarity_threshold = 0.3 (and word_similarity_threshold, strict_word_similarity_threshold GUCs)

**pitfalls**
- CVE-2026-14678: datatype error in contrib/pg_trgm's GiST picksplit function could read past buffer end, causing bad splits or crashes; fixed in PostgreSQL 16.15 (and corresponding patched releases of other major versions) -- pin to a patched point release.
- show_limit() and set_limit() functions are deprecated in favor of GUC parameters (pg_trgm.similarity_threshold etc.); avoid using the deprecated functions in new code.
- pg_trgm is a 'trusted' extension installable without superuser, but this depends on the Postgres version/packaging used in the Docker base image having the extension marked trusted and available -- ensure the chosen Postgres Docker image includes contrib modules (e.g. the official postgres image or a pgvector-bundled image that also ships pg_trgm).

*As of: PostgreSQL 18 official documentation (current docs, retrieved 2026-11-11); fix details confirmed from PostgreSQL 16.15 release notes (released per postgresql.org docs/release/16.15)*

**Sources**
- [PostgreSQL: Documentation: current (18): F.35. pg_trgm — support for similarity of text using trigram matching](https://www.postgresql.org/docs/current/pgtrgm.html) (official-docs) -- "The pg_trgm module provides functions and operators for determining the similarity of alphanumeric text based on trigram matching... This module is considered 'trusted', that is, it can be installed by non-superusers who have CREATE privilege on the current database."
- [PostgreSQL: Documentation: 17: F.33. pg_trgm — support for similarity of text using trigram matching](https://www.postgresql.org/docs/17/pgtrgm.html) (official-docs) -- "similarity(text, text) -> real ... show_limit() -> real (deprecated) ... pg_trgm.similarity_threshold (real) default 0.3"
- [PostgreSQL 16.15 release notes](https://www.postgresql.org/docs/release/16.15/) (official-docs) -- "Fix datatype error in contrib/pg_trgm's GiST picksplit function (Heikki Linnakangas). This mistake resulted in reading past the end of the buffer, typically causing bad split decisions; but a crash could ensue if you're very unlucky. (CVE-2026-14678)"


### Official documentation: PostgreSQL
*Find the OFFICIAL documentation for "PostgreSQL": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

The current stable PostgreSQL major version is 18 (released 2025-09-25, docs at 18.6), but prior stable lines 17/16/15 remain supported and are common pins for Docker-based self-hosted deployments like this one. For this build, PostgreSQL is run via the official Docker image, configured through environment variables and initdb-style options, with pg_trgm and pgvector enabled as extensions via CREATE EXTENSION, and pg_isready used for the Compose health check. Over the last 3 years the main pitfalls are the PG18 full-text-search/pg_trgm collation-provider behavior change (reindex needed on non-libc clusters), data checksums now defaulting to on, and the Docker image's PG18 data directory path change to /var/lib/postgresql/<version>/docker versus the older /var/lib/postgresql/data layout used in 17 and earlier.

**Key findings**
- Current stable major version: PostgreSQL 18 (docs version 18.6); supported branches are 15-18 per the pg_trgm docs page [as of docs 'current'].
- Official Docker image (hub.docker.com/_/postgres) supports tags including 19rc1, 18.6, 17.11, 16.15, 15.19, 14.24 in Debian and Alpine variants.
- POSTGRES_PASSWORD is required by the official image; POSTGRES_USER/POSTGRES_DB are optional and create a matching superuser/database; POSTGRES_HOST_AUTH_METHOD defaults to scram-sha-256 in PG14+.
- PG18 Docker image changed data volume layout to /var/lib/postgresql/<version>/docker; PG17 and earlier use /var/lib/postgresql/data -- this affects which path to mount as a volume in docker-compose.yml.
- initdb enables data checksums by default as of PG18 (new --no-data-checksums flag to opt out); default auth for local connections historically 'trust' unless overridden.
- pg_trgm is enabled with CREATE EXTENSION pg_trgm; it supports GIN and GiST indexes (gin_trgm_ops / gist_trgm_ops) and exposes similarity(), %, <-> operators used for fuzzy/typo-tolerant search alongside pgvector.
- PG18 full-text search / pg_trgm behavior change: full text search and pg_trgm now use the cluster's default collation provider (not always libc) to read config/dictionaries; clusters on non-libc providers (ICU, builtin) may see different trigram/matching behavior and should REINDEX affected indexes after upgrade.
- pg_isready exit codes: 0 = accepting connections, 1 = rejecting, 2 = no response, 3 = no attempt (bad args); it needs no credentials, making it suitable for an unauthenticated Compose healthcheck.
- Scripts in /docker-entrypoint-initdb.d/ only run on first container start when the data directory is empty -- relevant for applying CREATE EXTENSION vector/pg_trgm and initial schema on fresh deploys.

**Recommendations**
- Pin to a specific recent LTS-style minor (e.g. 16.x or 17.x) rather than tracking 'latest'/18 blindly, since pgvector HNSW and extension compatibility should be verified against the pinned version before relying on PG18's new defaults.
- If pinning to PG18, mount the volume at the versioned path (/var/lib/postgresql/18/docker) rather than the pre-18 /var/lib/postgresql/data path, or stay on 17.x to keep the old, simpler path used in most existing Compose examples.
- Use pg_isready (no auth required) as the Postgres healthcheck command in docker-compose.yml; gate dependent services (bot, re-embed job) on service_healthy.
- Enable both extensions explicitly in migration/init SQL: CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm; do not rely on image defaults.
- Never put POSTGRES_PASSWORD or other secrets directly in docker-compose.yml or the Dockerfile; use an .env file (gitignored) or the project's secrets provider port per acceptance criterion 7.
- If upgrading an existing cluster across major versions later, remember to REINDEX pg_trgm/full-text indexes post-upgrade on PG18 due to the collation-provider behavior change -- plan this into the RUNBOOK's restore/upgrade drill.

**current version:** PostgreSQL 18 (docs at 18.6); actively supported branches 15 through 18

**api surface**
- CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;
- initdb options: -D/--pgdata, -U/--username, -E/--encoding, --locale, -A/--auth, --no-data-checksums
- Docker image env vars: POSTGRES_PASSWORD, POSTGRES_USER, POSTGRES_DB, POSTGRES_INITDB_ARGS, POSTGRES_HOST_AUTH_METHOD
- /docker-entrypoint-initdb.d/*.sql|*.sh for first-run init (schema, extensions)
- pg_isready -h <host> -p <port> -U <user> -q for Compose healthcheck
- pg_trgm operators/functions: %, <->, similarity(), word_similarity() for fuzzy matching alongside pgvector similarity search

**pitfalls**
- PG18: full-text search and pg_trgm now honor the cluster's default collation provider instead of always libc; non-libc clusters need REINDEX on affected indexes after upgrade.
- PG18: data checksums enabled by default via initdb; pg_upgrade requires matching checksum settings between old and new clusters.
- PG18 Docker image volume path changed to /var/lib/postgresql/<version>/docker, differing from the /var/lib/postgresql/data path used on 17 and earlier -- a silent trap when copy-pasting older Compose files.
- PG18: COPY FROM no longer treats a bare '\.' as EOF in CSV files read server-side (psql STDIN behavior differs), which can break older \copy-based import scripts.
- MD5 password authentication is deprecated with warnings in recent PostgreSQL releases and scheduled for future removal -- use scram-sha-256 for any DB auth configured in this build.
- /docker-entrypoint-initdb.d/ scripts only execute when the data directory is empty on first container start, so re-running init SQL on an existing volume will silently no-op -- migrations must be applied separately (e.g. via the project's own apply_migrations.py), not relied on at container init.

*As of: PostgreSQL docs 'current' branch, PG 18.6 release notes (2025-09-25); pg_trgm docs page states supported versions 15-18 as of fetch date 2026-11-11*

**Sources**
- [PostgreSQL 18.0 Release Notes](https://www.postgresql.org/docs/current/release-18.html) (official-docs) -- "Change initdb default to enable data checksums (Greg Sabino Mullane)... Change full text search to use the default collation provider of the cluster to read configuration files and dictionaries, rather than always using libc"
- [initdb](https://www.postgresql.org/docs/current/app-initdb.html) (official-docs) -- "Must run as the database user (not root) - the user who will own the server process"
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html) (official-docs) -- "CREATE EXTENSION pg_trgm; ... CREATE INDEX trgm_idx ON test_trgm USING GIST (t gist_trgm_ops);"
- [postgres - Official Image | Docker Hub](https://hub.docker.com/_/postgres) (official-docs) -- "POSTGRES_PASSWORD ... It must not be empty or undefined ... Current versions include PostgreSQL 19rc1, 18.6, 17.11, 16.15, 15.19, and 14.24"
- [pg_isready](https://www.postgresql.org/docs/current/app-pg-isready.html) (official-docs) -- "Exit Codes: 0 Server is accepting connections normally ... No credentials needed for connection status check"


### Official documentation: Docker Compose
*Find the OFFICIAL documentation for "Docker Compose": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

Docker Compose (current major line v5, a Go-based successor to v2, invoked as `docker compose`) is the orchestration tool this build will use to start the FastAPI bot, local Postgres (pgvector + pg_trgm), and optional MinIO from a single compose.yaml, matching acceptance criterion 10. The Compose Specification (no numbered 'version' key needed) defines services, healthcheck, depends_on.condition, volumes and networks; `depends_on: condition: service_healthy` is the documented mechanism for making the bot wait on Postgres/MinIO health checks. Install via the `docker compose` CLI plugin (bundled with modern Docker Engine) rather than the legacy Python `docker-compose` v1 binary, which is now only kept for backward compatibility.

**Key findings**
- Current stable release is Docker Compose v5.7.0, released 2026-11-02, per the official GitHub releases page.
- Compose v5 (first released 2025-12-02 as v5.0.0) deliberately skipped version numbers 3 and 4 to avoid confusion with the legacy Compose file format versions '2.x'/'3.x'; it is functionally equivalent to v2 plus a new official Go SDK, per docs.docker.com/compose/intro/history/.
- Compose v2 (2020) is written in Go and invoked as `docker compose`; the old Python-based `docker-compose` (v1, hyphenated command) is legacy and only supported for backward compatibility, per docs.docker.com/compose/install/.
- The Compose Specification (merging legacy file format versions 2.x and 3.x) is the current/recommended compose.yaml schema, implemented by Compose CLI 1.27.0+, per docs.docker.com/reference/compose-file/.
- The top-level `version:` key in compose.yaml is obsolete: Compose always parses with the most recent schema regardless of this field, and using it now prints a warning, per docs.docker.com/reference/compose-file/version-and-name/.
- healthcheck supports test, interval, timeout, retries, start_period, and start_interval (the last added in Compose 2.20.2); depends_on supports condition: service_healthy to gate a service's startup on another service's healthcheck passing, per docs.docker.com/reference/compose-file/services/#healthcheck.
- Recent release notes (v5.5.0) warn that upgrading Compose can cause existing containers to be recreated on the first `compose up` after upgrade because image digests are re-evaluated with new logic, per github.com/docker/compose/releases.

**Recommendations**
- Use the `docker compose` CLI plugin (bundled with current Docker Engine on Linux) rather than the deprecated standalone `docker-compose` v1 binary, for long-term support on the school's servers.
- Write compose.yaml using the Compose Specification with no top-level `version:` key, since it is obsolete and only produces a warning.
- Define explicit `healthcheck` blocks for Postgres (e.g. pg_isready) and MinIO, and the bot's own HTTP health endpoint, then use `depends_on: <service>: condition: service_healthy` so the bot container only starts after Postgres (and MinIO, if used) report healthy -- this directly satisfies acceptance criterion 10.
- Pin or verify the Docker Engine/Compose version on the target school Linux servers supports the healthcheck keys used (start_interval needs Compose >= 2.20.2); do not assume a bare 'docker compose' install meets this without checking `docker compose version`.
- Treat Compose Go-SDK/library API changes noted in v5.5.0-5.7.0 release notes as irrelevant to this build, since the project only needs the CLI/YAML surface (`docker compose up`, `down`, `ps`, `logs`), not the library.

**current version:** Docker Compose v5.7.0 (released 2026-11-02); compose.yaml uses the Compose Specification file format (no numbered 'version' key required)

**api surface**
- docker compose up -d / docker compose down
- docker compose ps / docker compose logs -f
- compose.yaml: services, healthcheck (test, interval, timeout, retries, start_period, start_interval)
- depends_on: <service>: condition: service_healthy
- volumes (named volumes for Postgres data / MinIO data), networks

**pitfalls**
- Top-level `version:` key in compose.yaml is obsolete and triggers a warning; omit it and rely on the Compose Specification.
- Legacy standalone `docker-compose` (v1, hyphenated) is backward-compatibility-only; use the `docker compose` plugin instead.
- start_interval healthcheck key requires Compose >= 2.20.2; verify the target server's installed Compose version supports it before relying on it.
- Upgrading Compose versions can cause unrelated container recreation on the next `up` due to image digest re-evaluation logic changes (noted in v5.5.0).

*As of: 2026-11-11 (latest Compose release checked: v5.7.0, 2026-11-02)*

**Sources**
- [Docker Compose overview](https://docs.docker.com/compose/) (official-docs) -- "Compose works in all environments - production, staging, development, testing, as well as CI workflows."
- [Compose file reference](https://docs.docker.com/reference/compose-file/) (official-docs) -- "The Compose Specification is the latest and recommended version of the Compose file format."
- [Compose file - services (healthcheck)](https://docs.docker.com/reference/compose-file/services/#healthcheck) (official-docs) -- "start_interval: 5s ... (introduced in Docker Compose 2.20.2)"
- [Install Docker Compose](https://docs.docker.com/compose/install/) (official-docs) -- "The standalone Compose binary ... is not recommended and is only supported for backward compatibility purposes."
- [docker/compose Releases](https://github.com/docker/compose/releases) (repo) -- "v5.7.0 ... Existing containers may be recreated the first time you run compose up after upgrading, as image digests are re-evaluated using the new logic."
- [Compose file - Version and name top-level elements](https://docs.docker.com/reference/compose-file/version-and-name/) (official-docs) -- "The top-level version property is defined by the Compose Specification for backward compatibility. It is only informative."
- [History and development of Docker Compose](https://docs.docker.com/compose/intro/history/) (official-docs) -- "Compose v5 emerged in 2025 as functionally identical to Compose v2, but with a critical addition: the introduction of an official Go SDK."


### Official documentation: MinIO
*Find the OFFICIAL documentation for "MinIO": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

MinIO's open-source 'minio/minio' GitHub repo was archived on 2026-04-25 and is officially 'no longer maintained'; the last tagged release is RELEASE.2025-10-15T17-29-55Z. Since mid-2025 the Community Edition shipped source-only (no precompiled binaries), and all current official docs now live under the commercial 'AIStor' branding at docs.min.io/aistor/. For this build, the relevant surface is small: the Python SDK's presigned_get_object (max 7-day, min 1-second expiry, SigV4-signed, tamper-proof by construction) satisfies the ~15-minute signed-URL requirement, and the unauthenticated /minio/health/live and /minio/health/ready HTTP endpoints satisfy the Docker Compose health-check requirement. Because the project is EOL, the build should pin an exact last-good image tag rather than :latest and document a migration/alternative path in the RUNBOOK.

**Key findings**
- github.com/minio/minio was archived by its owner on 2026-04-25; README states 'THIS REPOSITORY IS NO LONGER MAINTAINED' and points users to 'AIStor Free' / 'AIStor Enterprise' instead [uncertain: exact archive-notice wording].
- Last published release tag on the repo's Releases page is RELEASE.2025-10-15T17-29-55Z (2025-10-16), a CVE/security fix for a privilege-escalation issue in service-account session policies.
- Since mid-2025 the Community Edition is distributed as source code only ('go install github.com/minio/minio@latest' or build the provided Dockerfile); MinIO Inc. stopped providing precompiled binaries and the admin UI in the Community tier.
- MinIO source has been AGPLv3-licensed since 2021 (changed from Apache-2.0); official README explicitly warns 'All usage of MinIO in your application stack requires validation against AGPLv3 obligations.'
- Current official docs for health checks live at docs.min.io/aistor/.../http-endpoints/ and list 4 unauthenticated GET endpoints: /minio/health/live (liveness), /minio/health/ready (readiness), /minio/health/cluster (write quorum), /minio/health/cluster/read (read quorum, accepts ?maintenance=true).
- Official AIStor container/compose docs use healthcheck test ["CMD","mc","ready","local"] with interval 5s, timeout 5s, retries 5; ports documented are 9000 (S3 API) and 9001 (web console); MINIO_ROOT_USER/MINIO_ROOT_PASSWORD env vars set root credentials.
- Python SDK `presigned_get_object(bucket_name, object_name, expires=timedelta(days=7), response_headers=None, request_date=None, version_id=None, extra_query_params=None)` defaults to 7-day expiry; all presigned URLs are documented with expiry bounded between 1 second and 7 days, and cannot be revoked before expiry.
- Official AIStor distributed docker-compose example pulls 'quay.io/minio/aistor/minio:latest' and requires a 'minio.license' file in the same directory, and is explicitly scoped to 'development, testing, and staging only — not production use' [uncertain: whether this no-production caveat also applies to a single-node non-AIStor deployment].

**Recommendations**
- Pin the Docker image to the last maintained tag, RELEASE.2025-10-15T17-29-55Z, rather than ':latest' — the upstream project is archived/EOL and there will be no further security patches under the MinIO community name.
- Use the Python minio SDK's presigned_get_object(bucket, key, expires=timedelta(minutes=15)) for the ObjectStore port's signed download URLs; its SigV4 signing already rejects tampered signatures and expired URLs, satisfying acceptance criterion #6 without custom crypto.
- Use a curl-based Docker Compose healthcheck against http://localhost:9000/minio/health/live (unauthenticated, documented endpoint) for the 'reports healthy' requirement rather than relying solely on 'mc ready local', which has had version-specific behavior issues reported by users.
- Document in the RUNBOOK that MinIO community edition is EOL (repo archived 2026-04-25, source-only distribution since mid-2025) and name a fallback (rebuild from the last tagged source, move to AIStor Free, or switch to another S3-compatible store) as a known risk for a school running this unsupported long-term.
- Flag the AGPLv3 license to the school/stakeholders given the backend is reachable over public HTTPS; confirm the build only consumes MinIO as an unmodified binary/service (not redistributing modified MinIO source) to avoid ambiguity around AGPL's network-use clause — get explicit sign-off rather than assuming it's a non-issue.

**current version:** RELEASE.2025-10-15T17-29-55Z (last tagged MinIO Community Edition release; repo archived 2026-04-25, successor branded 'AIStor')

**api surface**
- minio.Minio(endpoint, access_key, secret_key, secure=True) — client construction
- client.make_bucket(bucket_name), client.bucket_exists(bucket_name)
- client.put_object(bucket_name, object_name, data, length, ...)
- client.presigned_get_object(bucket_name, object_name, expires=timedelta(minutes=15)) — signed download URL for ObjectStore port
- GET /minio/health/live, GET /minio/health/ready — Docker Compose healthcheck targets
- MINIO_ROOT_USER / MINIO_ROOT_PASSWORD env vars; ports 9000 (S3 API), 9001 (console)

**pitfalls**
- minio/minio GitHub repo archived 2026-04-25 — no more upstream fixes under the open-source project name; plan for an EOL dependency.
- Community Edition distribution changed to source-only (no precompiled binaries, admin UI removed) partway through 2025 — pulling ':latest' may not behave as historical tutorials describe.
- License changed from Apache-2.0 to AGPLv3 in 2021 — relevant given this build's public HTTPS exposure; needs a compliance check, not an assumption.
- Official docs moved to the commercial 'AIStor' namespace (docs.min.io/aistor/...); AIStor-specific docker-compose examples target multi-node/licensed deployments, not a simple single-node school server — don't copy them verbatim without adapting for single-node use.
- Presigned URLs cannot be revoked before their expiry once issued — the ~15-minute window must be enforced at generation time, not via later revocation.

*As of: GitHub Releases page and repo README as read on 2026-11-11; last MinIO community release RELEASE.2025-10-15T17-29-55Z; repo archived 2026-04-25.*

**Sources**
- [minio/minio GitHub repository (README, status)](https://github.com/minio/minio) (repo) -- "THIS REPOSITORY IS NO LONGER MAINTAINED ... AIStor Free ... The MinIO community edition is now distributed as source code only."
- [minio/minio Releases](https://github.com/minio/minio/releases) (repo) -- "RELEASE.2025-10-15T17-29-55Z ... Archived by the owner on Apr 25, 2026. It is now read-only."
- [MinIO AIStor Python Client API Reference](https://docs.min.io/aistor/developers/sdk/python/api/) (official-docs) -- "presigned_get_object(bucket_name, object_name, expires=timedelta(days=7), response_headers=None, request_date=None, version_id=None, extra_query_params=None)"
- [Deploy Distributed MinIO AIStor on Docker Compose](https://docs.min.io/aistor/installation/container/distributed/) (official-docs) -- "test: ["CMD", "mc", "ready", "local"] ... this configuration is suitable for development, testing, and staging purposes only"
- [MinIO AIStor HTTP Endpoints Reference](https://docs.min.io/aistor/reference/aistor-server/http-endpoints/) (official-docs) -- "GET /minio/health/live — Liveness probe. 200 OK if the server process is running. GET /minio/health/ready — Readiness probe."
- [MinIO (Wikipedia)](https://en.wikipedia.org/wiki/MinIO) (other) -- "MinIO, Inc. halted active development in February 2026 ... 'it is not maintained anymore'"


### Official documentation: sentence-transformers
*Find the OFFICIAL documentation for "sentence-transformers": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

sentence-transformers is the official Python library (sbert.net, UKPLab/sentence-transformers on GitHub) for loading Hugging Face embedding models and computing dense vector embeddings; current stable release is v6.2.0, installed via `pip install -U sentence-transformers`, requiring Python 3.10+, PyTorch 2.2+ and transformers v5.x. For this build's CPU, 768-dimension requirement, the standard model choice is `sentence-transformers/all-mpnet-base-v2` (768-dim, CPU-capable, highest quality in the general-purpose family), loaded via `SentenceTransformer(model_name, device="cpu")` and queried with `.encode()`. The API surface needed (model load, encode, batch_size, normalize_embeddings, convert_to_numpy) is stable and documented, but recent major versions (v5.4+ and v6.0) renamed `encode(sentences=...)` to `encode(inputs=...)` and `get_sentence_embedding_dimension()` to `get_embedding_dimension()`, which this build should account for when pinning a version.

**Key findings**
- Current stable release is v6.2.0, confirmed on the official GitHub Releases page (tag v6.2.0, published '21 Oct') [uncertain on exact year — page did not render the year explicitly, but it is the 'latest' release as of this research date]
- Install via `pip install -U sentence-transformers`; official docs state requirement of Python 3.10+ and PyTorch (v6.0 raised the floor to PyTorch 2.2+, up from 1.11.0+) plus transformers v5.x
- Core API: `SentenceTransformer(model_name_or_path, device=..., cache_folder=..., trust_remote_code=...)` to load, then `.encode(inputs, batch_size=, normalize_embeddings=, convert_to_numpy=, convert_to_tensor=, device=)` to embed; `device='cpu'` is an explicit, documented option alongside 'cuda'/'mps'/'npu'
- `sentence-transformers/all-mpnet-base-v2` is the official docs' recommended 'best quality' general-purpose model trained on 1B+ pairs and runs on CPU; it produces 768-dimensional embeddings, matching this build's Vector(768) schema requirement
- `all-MiniLM-L6-v2` is the faster CPU alternative but outputs 384-dim vectors — NOT a drop-in for this build's fixed 768-dim schema
- v6.0.0 (major breaking release): requires transformers v5.x and torch 2.2+; custom/local module classes now require `trust_remote_code=True` even for local models; `similarity`/`similarity_pairwise` changed from properties to methods; `CrossEncoder.rank()` now returns plain Python floats
- v5.4+ renamed `encode(sentences=...)` → `encode(inputs=...)` and `get_sentence_embedding_dimension()` → `get_embedding_dimension()`; old module import paths from `sentence_transformers.models` still work but emit deprecation warnings
- v5.7.0: int8/uint8 quantized embedding outputs changed — out-of-calibration-range values now saturate at bounds instead of wrapping, which can silently change downstream similarity scores if quantization is ever adopted
- Model cache location is controlled by `cache_folder` param or `SENTENCE_TRANSFORMERS_HOME` env var — relevant for Docker image layering/offline caching in this build

**Recommendations**
- Pin `sentence-transformers` to a known-good version (e.g., 6.x) in requirements and lock the exact pin in the Dockerfile; do not float on latest, since v6.0 changed `encode()` and dimension-getter method names versus v5.x code examples found online
- Use `sentence-transformers/all-mpnet-base-v2` (768-dim) rather than `all-MiniLM-L6-v2` (384-dim) to satisfy the Vector(768)/HNSW schema requirement without a schema change
- Load the model with `device='cpu'` explicitly and bake the model weights into the Docker image (or pre-populate `SENTENCE_TRANSFORMERS_HOME`) so no network call happens at container start or during tests
- In the re-embed job and parity report, use `.encode(inputs, normalize_embeddings=True, convert_to_numpy=True, batch_size=...)` consistently for both chunk and title embeddings to match pgvector's expected input format
- Do not set `trust_remote_code=True` unless the chosen model repo requires it and has been reviewed — v6.0 enforces this flag even for local custom modules
- Avoid embedding quantization (int8/uint8) for this build unless re-validated against v5.7+'s changed saturation behavior, since the acceptance criteria require an old-vs-new parity report and quantization changes would be a second variable

**current version:** 6.2.0

**api surface**
- SentenceTransformer(model_name_or_path, device='cpu', cache_folder=..., trust_remote_code=False)
- model.encode(inputs, batch_size=..., normalize_embeddings=True, convert_to_numpy=True)
- model.get_embedding_dimension() (renamed from get_sentence_embedding_dimension in v5.4+)
- model.similarity(embeddings_a, embeddings_b) (method as of v6.0, not a property)
- SENTENCE_TRANSFORMERS_HOME env var / cache_folder param for offline model caching

**pitfalls**
- v6.0.0 raised minimum deps to transformers v5.x and torch 2.2+ — verify CPU-only torch wheel compatibility before pinning
- v5.4+ renamed encode(sentences=...) to encode(inputs=...) and get_sentence_embedding_dimension() to get_embedding_dimension(); old code samples copied from older tutorials will break or warn
- v6.0 enforces trust_remote_code=True for any custom module code, including local models, which can silently fail CI/tests if not set and the chosen model needs it
- all-MiniLM-L6-v2 (384-dim) is a commonly recommended 'fast' model but is incompatible with this build's fixed Vector(768) schema — must use a 768-dim model like all-mpnet-base-v2
- v5.7.0 changed int8/uint8 quantization saturation behavior, which would silently skew a before/after parity comparison if quantization is introduced alongside the migration
- Module import paths moved in v5.4+ (sentence_transformers.models → model-specific submodules); old paths still work but emit deprecation warnings that could pollute CI logs

*As of: v6.2.0, GitHub Releases page accessed 2026-11-11 (exact release date text showed '21 Oct' without a rendered year)*

**Sources**
- [Sentence Transformers (official site)](https://sbert.net/) (official-docs) -- "pip install -U sentence-transformers ... Python 3.10+ ... PyTorch 1.11.0+"
- [sentence-transformers GitHub Releases](https://github.com/UKPLab/sentence-transformers/releases) (repo) -- "v6.0.0 ... Requires transformers v5 and PyTorch 2.2+ (upgraded from v4.41.0 and PyTorch 1.11.0)"
- [sentence-transformers GitHub latest release](https://github.com/UKPLab/sentence-transformers/releases/latest) (repo) -- "The version tag is v6.2.0, released on 21 Oct 12:27."
- [Usage docs — SentenceTransformer](https://sbert.net/docs/sentence_transformer/usage/usage.html) (official-docs) -- "model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2") ... shape [3, 384]"
- [SentenceTransformer class reference](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) (official-docs) -- "device: Specifies computation hardware like "cuda", "cpu", "mps", or "npu""
- [Pretrained Models docs](https://sbert.net/docs/sentence_transformer/pretrained_models.html) (official-docs) -- "all-mpnet-base-v2 ... the best quality, trained on over 1 billion training pairs"
- [Migration Guide](https://sbert.net/docs/migration_guide.html) (official-docs) -- "get_sentence_embedding_dimension() → get_embedding_dimension(); encode(sentences=...) → encode(inputs=...)"


### Official documentation: ONNX Runtime
*Find the OFFICIAL documentation for "ONNX Runtime": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

ONNX Runtime (Microsoft) is the correct, actively maintained inference engine for running a local CPU embedder in this migration: current stable is 1.31.1 (Oct 26, 2026), installed via `pip install onnxruntime` for CPU-only inference, officially supports Python 3.11-3.14 (covers the build's Python 3.12 requirement), and exposes a small, stable Python API (InferenceSession, SessionOptions, get_available_providers, run()) sufficient to load an ONNX embedding model and produce 768-dim vectors with no GPU and no external API dependency. The last 3 years brought no breaking changes to the core CPU inference path used here; the only relevant deprecation is the unrelated ARM Compute Library execution provider.

**Key findings**
- Current stable release: onnxruntime 1.31.1, released 2026-10-26 (PyPI); 1.31.0 released 2026-10-09 (GitHub Releases) — both are the latest-of-record as of this research.
- PyPI package 'onnxruntime' (CPU build) requires Python >=3.11 and ships wheels for Python 3.11, 3.12, 3.13, 3.14 on Linux/Windows/macOS — Python 3.12 is fully supported.
- Official install for CPU-only (non-GPU, non-Arm-specific) is `pip install onnxruntime`; docs note the same package is recommended for Arm-based CPUs and macOS too.
- Core API: `onnxruntime.InferenceSession(path_or_bytes, sess_options=None, providers=None, provider_options=None)`, `.run(output_names, input_feed, run_options=None) -> list[ndarray]`, `onnxruntime.get_available_providers()`, and `SessionOptions` (graph_optimization_level, intra_op_num_threads, inter_op_num_threads, execution_mode, enable_profiling).
- On a machine with only CPU hardware, `providers=['CPUExecutionProvider']` is used explicitly or implicitly (CPUExecutionProvider is always the fallback/default when no accelerator is present).
- ONNX Runtime maintains broad backward opset compatibility: 'All versions of ONNX Runtime support ONNX opsets from ONNX v1.2.1+ (opset version 7 and higher)' — no action needed for model conversion compatibility.
- v1.31.0 breaking/notable change: GatherBlockQuantized now returns zero output slices for out-of-range indices (CPU/CUDA/WebGPU) instead of erroring — only relevant if using quantized Gather ops, not typical for a plain embedding model.
- v1.31.0 deprecation: the ARM Compute Library (ACL) execution provider is deprecated and will be removed in a future release; irrelevant to a standard CPUExecutionProvider deployment.
- v1.31.0 stabilized the previously-experimental model-package and EPContext data APIs (promoted to stable C/C++/Python/etc. APIs) — not needed for a simple embedding InferenceSession, but confirms the API surface this build will touch (InferenceSession/run) has been stable, not experimental, throughout.

**Recommendations**
- Pin `onnxruntime` (CPU package, not `onnxruntime-gpu`) in requirements, e.g. `onnxruntime>=1.31,<2`, and verify the Docker base image's glibc/Linux distro matches ONNX Runtime's supported platform matrix before building the image.
- Load the embedding model once at process startup as a module-level `InferenceSession(model_path, providers=['CPUExecutionProvider'])` and reuse it per request — do not recreate the session per call.
- Explicitly pass `providers=['CPUExecutionProvider']` rather than relying on default provider ordering, to guarantee no CUDA/other EP is probed on the school's no-GPU servers and to keep startup fast and deterministic.
- Do not use the ARM Compute Library execution provider (deprecated) even if deploying on ARM servers; stick with the default CPU provider.
- Since Python 3.12 is a fully supported, non-edge version, no special wheel-building or source compilation is needed — a plain `pip install onnxruntime` in the Dockerfile will fetch a prebuilt wheel.
- Treat GatherBlockQuantized's altered out-of-range behavior as a non-issue unless the chosen embedding model uses block-quantized Gather ops internally; verify by inspecting the exported ONNX graph if quantization is used.

**current version:** 1.31.1 (per PyPI, 2026-10-26); 1.31.0 (per GitHub Releases, 2026-10-09)

**api surface**
- onnxruntime.InferenceSession(path_or_bytes, sess_options=None, providers=None, provider_options=None)
- InferenceSession.run(output_names, input_feed, run_options=None) -> list[ndarray]
- onnxruntime.SessionOptions (intra_op_num_threads, inter_op_num_threads, graph_optimization_level, execution_mode)
- onnxruntime.get_available_providers() / get_all_providers()
- providers=['CPUExecutionProvider'] (explicit CPU-only execution for no-GPU school servers)

**pitfalls**
- Exact release-date source conflict: GitHub release page text itself showed 'October 9, 2024' for v1.31.0 while PyPI and web search both independently corroborate 2026 — this is a likely date-extraction artifact on the GitHub page render; treat the 2026 date as correct but flagged.
- ACL (ARM Compute Library) execution provider deprecated in v1.31.0, scheduled for removal — avoid depending on `--use_acl` builds.
- GatherBlockQuantized semantics changed in v1.31.0 (out-of-range indices now silently zero instead of erroring) — audit any quantized models for reliance on old error behavior.
- onnxruntime (CPU) package on PyPI requires Python >=3.11, dropping support for older Python 3.x versions — ensure Docker base image uses Python 3.12 as planned, not an older interpreter.
- Must install the plain `onnxruntime` package, not `onnxruntime-gpu`, to avoid pulling unnecessary CUDA dependencies on GPU-less school servers.

*As of: 2026-10-26 (onnxruntime 1.31.1 per PyPI; 1.31.0 per GitHub Releases, 2026-10-09)*

**Sources**
- [onnxruntime · PyPI](https://pypi.org/project/onnxruntime/) (official-docs) -- "Current Version: 1.31.1 ... Release Date: October 26, 2026 ... Python >=3.11"
- [Install ONNX Runtime | onnxruntime.ai](https://onnxruntime.ai/docs/get-started/with-python.html) (official-docs) -- "pip install onnxruntime ... Use the CPU package if you are running on Arm®-based CPUs and/or macOS."
- [API - Python API documentation](https://onnxruntime.ai/docs/api/python/api_summary.html) (official-docs) -- "class onnxruntime.InferenceSession(path_or_bytes, sess_options=None, providers=None, provider_options=None, **kwargs) ... onnxruntime.get_available_providers()"
- [ONNX Runtime compatibility](https://onnxruntime.ai/docs/reference/compatibility.html) (official-docs) -- "All versions of ONNX Runtime support ONNX opsets from ONNX v1.2.1+ (opset version 7 and higher)."
- [Release ONNX Runtime v1.31.0 · microsoft/onnxruntime](https://github.com/microsoft/onnxruntime/releases/tag/v1.31.0) (repo) -- "The ACL EP is deprecated and will be removed in a future release. ... GatherBlockQuantized ... produce zero output slices across CPU, CUDA, and WebGPU"
- [Releases · microsoft/onnxruntime](https://github.com/microsoft/onnxruntime/releases) (repo) -- "ONNX Runtime v1.31.1 ... Latest patch release; v1.31.0 ... stabilizes model-package and EPContext data APIs"


### Official documentation: Hugging Face Transformers
*Find the OFFICIAL documentation for "Hugging Face Transformers": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

Hugging Face Transformers is officially at v5.22.2 (confirmed Nov 2026), requiring Python 3.11+ and PyTorch 2.6+; v5 made PyTorch the sole backend, dropping TensorFlow/Flax support entirely. For this build's local CPU embedder, the relevant surface is AutoTokenizer/AutoModel.from_pretrained plus the feature-extraction pipeline, both of which support explicit device='cpu' placement and offline/local-cache loading via HF_HUB_OFFLINE=1 or local_files_only=True — exactly what's needed to keep unit tests network-free and run on no-GPU school servers. The main migration risk for a team coming from any v4-era code is the TF/Flax removal and the torch_dtype→dtype rename with a new 'auto' precision default, neither of which was documented at the time most existing embedding example code was written.

**Key findings**
- Current stable release is transformers 5.22.2, released 2026-11-06, per the official PyPI project page and the version-pinned docs URLs (/docs/transformers/v5.22.2/...).
- [removed by OSA: this line looked like an instruction aimed at an AI (remote-exec)]
- Transformers v5 sunsets TensorFlow and Flax support, making PyTorch the sole backend going forward (official v5 blog post, huggingface.co/blog/transformers-v5).
- v5 also removes the Fast/Slow tokenizer distinction, standardizing on the `tokenizers` backend; image processors now ship only torchvision-accelerated variants (same blog post).
- The official feature-extraction pipeline docs (main_classes/pipelines) show `device` (e.g. device='cpu' or device=-1 to force CPU) and `dtype` (default 'auto', meaning it loads in whatever precision the model checkpoint was saved in rather than defaulting to float32) as the relevant runtime parameters.
- Official installation docs describe offline/no-network operation: set HF_HUB_OFFLINE=1 or pass local_files_only=True to from_pretrained() to prevent any HTTP calls to the Hub once a model is cached — the documented mechanism for satisfying a 'no network calls in tests' requirement.
- Default cache location is ~/.cache/huggingface/hub (or C:\Users\<user>\.cache\huggingface\hub on Windows), configurable via HF_HUB_CACHE / HF_HOME env vars — relevant for baking a model into a Docker image layer.
- [uncertain] Community/secondary sources (not opened directly as primary docs) report that `torch_dtype=` in from_pretrained is deprecated in favor of `dtype=` as of transformers >=4.56/5.x; this specific rename was not independently confirmed by directly reading the from_pretrained parameter docs in this session due to page size, so it carries the uncertain marker even though the related 'dtype defaults to auto, not float32' behavior itself was confirmed directly from the official pipelines doc.

**Recommendations**
- [removed by OSA: this line looked like an instruction aimed at an AI (remote-exec)]
- Use AutoTokenizer + AutoModel.from_pretrained with explicit device='cpu' (and, if pooling embeddings yourself, explicit dtype=torch.float32) rather than relying on the pipeline's 'auto' dtype default, so precision is deterministic across runs for the before/after parity report.
- Pre-download the chosen 768-dim embedding model into the Docker image at build time, then set HF_HUB_OFFLINE=1 (or local_files_only=True) at runtime — this is the documented way to guarantee zero network calls during pytest and in production, satisfying acceptance criterion 2.
- Pin the transformers version exactly in requirements (e.g. transformers==5.22.2) rather than a loose range, given how recent and disruptive the v4→v5 TF/Flax removal and tokenizer changes are — avoids an unplanned major-version jump breaking the Docker build later.
- Avoid any torch_dtype= keyword if copying older example code from pre-v5 tutorials; use dtype= instead and verify against the installed version's own `from_pretrained.__doc__` rather than trusting older blog posts, since this rename is only secondarily confirmed here.
- Confirm the specific 768-dim embedding model checkpoint chosen for this build has been re-tested or re-uploaded compatible with transformers 5.x (not just an older 4.x-era checkpoint), since the config/model-loading internals changed significantly in v5.

**current version:** 5.22.2 (released 2026-11-06)

**api surface**
- from transformers import AutoTokenizer, AutoModel
- AutoTokenizer.from_pretrained(model_id, local_files_only=True)
- AutoModel.from_pretrained(model_id, dtype=torch.float32, local_files_only=True) — for custom mean-pooling to produce 768-dim sentence embeddings
- transformers.pipeline('feature-extraction', model=model_id, device='cpu')
- Environment variables HF_HUB_OFFLINE=1 / HF_HOME / HF_HUB_CACHE for offline, Docker-baked model caching

**pitfalls**
- v5 removes TensorFlow and Flax backend support entirely; any legacy code or tutorials assuming TF compatibility will fail on install/import.
- v5 removes the Fast/Slow tokenizer distinction in favor of the tokenizers backend only — code branching on tokenizer type should be removed.
- pipeline/from_pretrained dtype now defaults to 'auto' (whatever precision the checkpoint was saved in) rather than always float32 — pin dtype=torch.float32 explicitly for predictable CPU behavior.
- [uncertain] torch_dtype= kwarg is reportedly deprecated in favor of dtype= as of 4.56+/5.x per secondary sources — not independently confirmed from the primary from_pretrained docs in this session.
- Requires Python 3.11+ and PyTorch 2.6+; older pinned PyTorch versions in an existing Dockerfile may need bumping.
- Without HF_HUB_OFFLINE=1 or local_files_only=True, from_pretrained will attempt a Hub network call even when a model is cached (e.g. on branch/tag resolution), which would violate the 'no network calls in unit tests' acceptance criterion if left unset.

*As of: transformers v5.22.2, released 2026-11-06 (per PyPI and version-pinned docs URLs)*

**Sources**
- [Installation — Hugging Face Transformers docs](https://huggingface.co/docs/transformers/installation) (official-docs) -- "Transformers works with PyTorch. It has been tested on Python 3.11+ and PyTorch 2.6+."
- [transformers · PyPI](https://pypi.org/project/transformers/) (official-docs) -- "Current Stable Version: 5.22.2, released on November 6, 2026"
- [Transformers — index page](https://huggingface.co/docs/transformers/en/index) (official-docs) -- "Transformers acts as the model-definition framework for state-of-the-art machine learning models ... pivot across frameworks ... (v5.22.2 docs)"
- [Pipelines — main classes](https://huggingface.co/docs/transformers/main_classes/pipelines) (official-docs) -- "device (int, str, or torch.device, optional) ... Pass device="cpu" or device=-1 to force CPU execution. dtype ... defaults to 'auto' ... defaults to the dtype the model was saved in."
- [Transformers v5: Simple model definitions powering the AI ecosystem](https://huggingface.co/blog/transformers-v5) (article) -- "we're sunsetting our Flax/TensorFlow support in favor of focusing on PyTorch as the sole backend"


### Official documentation: Meta WhatsApp Cloud API
*Find the OFFICIAL documentation for "Meta WhatsApp Cloud API": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

This item covers the Meta WhatsApp Cloud API, which the build already uses for the WhatsApp channel and must keep working unchanged behind a thin adapter. Meta's primary documentation host (developers.facebook.com) was unreachable from this research environment due to a DNS resolution failure on every path tested, so verified facts here come from Meta's own mirror domain (developers.meta.com), which resolved for its homepage, blog index, and a resource page. Those confirm the API is actively maintained (current Graph API version v27.0, announced 2026-11-04) and that the Cloud API's core `/messages` endpoint remains the integration surface going forward (used for the new "Direct Send" feature). Deeper mechanics of the send/webhook endpoints (exact request/response shapes, signature verification) could not be independently opened in this environment and are flagged accordingly; they should be re-confirmed against developers.facebook.com directly before implementation.

**Key findings**
- Current Graph API version is v27.0, announced on Meta's developer blog dated 2026-11-04, described as including "new capabilities, deprecations, and breaking changes" (opened via developers.meta.com/blog/).
- Marketing messages sent via WhatsApp Cloud API are scheduled to sunset 2027-10-13; businesses must migrate marketing-template sends to the separate Marketing Messages API by then (opened via developers.meta.com/blog/). This does not affect this build's utility/retrieval-bot messaging.
- Meta added a "Direct Send" capability on Cloud API (announced 2026-06-16 per a Meta developer resource page) that still uses the existing Cloud API `/messages` endpoint plus one new field, removing the template-approval requirement for utility messages — confirms `/messages` remains the stable send endpoint (opened via developers.meta.com/resources/videos/whatsapp-direct-send-api/).
- [uncertain] The send endpoint is reported (by secondary, non-primary sources only — not opened directly) as `POST https://graph.facebook.com/{version}/{PHONE_NUMBER_ID}/messages` with a JSON body shaped `{"messaging_product":"whatsapp","to":...,"type":...}`.
- [uncertain] Webhook setup is reported (secondary sources only) to require a GET handshake where Meta sends `hub.mode=subscribe`, `hub.verify_token`, and `hub.challenge`, and the receiver must echo `hub.challenge` back after validating the token.
- [uncertain] Inbound webhook POSTs are reported (secondary sources only) to carry an `X-Hub-Signature-256` header, an HMAC-SHA256 digest of the raw request body keyed with the Meta App Secret, intended for timing-safe verification.
- [uncertain] Per secondary aggregator reporting, older Graph API versions are retired roughly every ~2 years (v15 removed 2024-11-20, v16 removed 2025-05-14), and the legacy On-Premises API was fully sunset 2025-10-23, leaving Cloud API as the only supported path.
- The primary documentation domain developers.facebook.com returned DNS resolution failures (ENOTFOUND) for every path attempted in this research environment, including the root domain and graph.facebook.com; only the Meta-owned mirror developers.meta.com was reachable, and only for a subset of pages (homepage, blog index, a video resource page) — most deep doc paths on that mirror also 404.

**Recommendations**
- Before implementing the WhatsApp adapter, re-verify the exact `/messages` send endpoint, webhook verification handshake, and `X-Hub-Signature-256` signing details directly against developers.facebook.com from a network that can reach it — this research could not open those pages itself.
- Keep the Graph API version pinned explicitly in config (e.g. as an env var) rather than relying on an implicit default, since Meta deprecates versions on a roughly 2-year cycle.
- Implement inbound webhook signature verification (HMAC-SHA256 over the raw body) in the thin WhatsApp adapter only, so handle_inbound and the retrieval callable stay free of WhatsApp-specific signing logic, consistent with acceptance criterion 4.
- Do not build against the deprecated Messaging Events API; use the standard Cloud API webhook model for receiving messages and status updates.
- No action needed regarding the Marketing Messages API sunset (2027-10-13) — this bot sends session/utility-style replies, not marketing templates — but note the date once in RUNBOOK as a future watch-item.

**current version:** Graph API v27.0 (as of 2026-11-04, per Meta's own developer blog)

**api surface**
- POST /{PHONE_NUMBER_ID}/messages — send outbound WhatsApp messages [uncertain: endpoint shape reported by secondary sources, not opened directly by this research]
- GET webhook callback endpoint — handshake verification via hub.mode/hub.verify_token/hub.challenge [uncertain: secondary-source only]
- POST webhook callback endpoint — receive inbound messages/delivery status; verify X-Hub-Signature-256 HMAC over raw body [uncertain: secondary-source only]
- Graph API version path segment (e.g. v27.0) embedded in all request URLs
- Bearer access token in Authorization header for authenticating outbound Graph API calls [uncertain: secondary-source only]

**pitfalls**
- [uncertain, secondary-source only] Graph API versions are retired on a roughly 2-year cadence (v15 retired 2024-11-20, v16 retired 2025-05-14) — pin a version and track Meta's deprecation calendar.
- [uncertain, secondary-source only] v21.0 reportedly changed one-tap/zero-tap authentication template button parameters (package_name/signature_hash moved into a supported_apps array) — irrelevant unless this bot ever adopts WhatsApp auth templates.
- [uncertain, secondary-source only] The Messaging Events API was deprecated around September 2024/2025 — do not build new integrations against it; use standard Cloud API webhooks instead.
- [uncertain, secondary-source only] The legacy On-Premises API was fully sunset 2025-10-23 — not relevant since this build already targets Cloud API, but confirms no on-prem fallback exists.
- Methodological pitfall for this research: developers.facebook.com (the primary official docs host) was fully unreachable (DNS failure) from this environment, so any endpoint/webhook mechanics not explicitly marked as opened above should be independently re-verified against the primary docs before implementation.

*As of: 2026-11-04 (Graph API v27.0, per Meta's developer blog on developers.meta.com)*

**Sources**
- [Meta for Developers (homepage navigation to WhatsApp Business Platform docs)](https://developers.meta.com/) (official-docs) -- "WhatsApp Business Platform ... documentation ... alongside other Meta platforms like Facebook Login, Instagram Platform, and Threads API."
- [Meta Developer News / Blog](https://developers.meta.com/blog/) (official-docs) -- "Graph API v27.0 and Marketing API v27.0 include new capabilities, deprecations, and breaking changes. ... Marketing messages on WhatsApp sent through the Cloud API will sunset on October 13, 2027."
- [WhatsApp Direct Send API (Meta developer resource)](https://developers.meta.com/resources/videos/whatsapp-direct-send-api/) (official-docs) -- "Direct Send ... eliminates the need to create and wait for template approval when sending utility messages ... using the existing Cloud API /messages endpoint, requiring only one additional field."


### Official documentation: Model Context Protocol (MCP)
*Find the OFFICIAL documentation for "Model Context Protocol (MCP)": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

The Model Context Protocol (MCP) is an open, JSON-RPC 2.0-based standard (maintained at modelcontextprotocol.io and github.com/modelcontextprotocol) for connecting AI applications to external tools/data. The spec has had four stable dated revisions in under two years (2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25), with the official docs site now also publishing a dated general-docs tree (2026-07-28) layered on top of the 2025-11-25 protocol spec. For this OSA build, the relevant surface is: the official Python SDK (`mcp` package, install via `pip install "mcp[cli]"`), the `@mcp.tool()` decorator pattern (FastMCP) to expose the single retrieval callable as one MCP tool, and the Streamable HTTP transport (not stdio) since the backend must be reachable over public HTTPS. The protocol has gone through real breaking changes (transport replaced, JSON-RPC batching added then removed, auth model substantially reworked) so the build should pin an explicit revision rather than track "latest."

**Key findings**
- Protocol revisions (dated, each with its own changelog page): 2024-11-05 (baseline), 2025-03-26, 2025-06-18, 2025-11-25 (current stable spec as of this research) [modelcontextprotocol.io/specification/*].
- 2025-03-26 replaced the original HTTP+SSE transport with 'Streamable HTTP' and added JSON-RPC batching and an OAuth 2.1-based authorization framework.
- 2025-06-18 then REMOVED JSON-RPC batching support entirely, classified MCP servers as OAuth Resource Servers, required clients to implement RFC 8707 Resource Indicators, added structured tool output, elicitation, resource links, and required the `MCP-Protocol-Version` HTTP header on requests after initialization.
- 2025-11-25 added OpenID Connect Discovery 1.0 support, icon metadata on tools/resources/prompts, incremental OAuth scope consent, tool-name guidance, reworked ElicitResult/EnumSchema, URL-mode elicitation, tool-calling via sampling, OAuth Client ID Metadata Documents, and experimental 'tasks' for durable/polled requests.
- Core primitives (stable across revisions): Resources, Tools, Prompts offered by servers; Sampling, Roots, Elicitation offered by clients; all over JSON-RPC 2.0 with stateful connections and capability negotiation [modelcontextprotocol.io/specification/2025-06-18].
- Official Python SDK install: `pip install "mcp[cli]"` (plain `mcp` for SDK-only, no CLI); SDK uses `@mcp.tool()` / `@mcp.resource()` decorators, deriving JSON Schema from type hints/docstrings, eliminating manual request parsing [github.com/modelcontextprotocol/python-sdk].
- Supported transports in the Python SDK: stdio (local subprocess), Streamable HTTP (the deployment/network transport), and legacy SSE — stdio is not viable for a publicly reachable HTTPS backend.
- PyPI shows `mcp` package at version 2.3.0 (released 2026-10-02), confirming active, fast-moving releases well within the last 3 years [pypi.org/project/mcp].

**Recommendations**
- Do not implement MCP wiring in this migration phase per the locked PRD (Copilot Studio/agent tool integration is explicitly a later run) — only keep the retrieval callable channel-neutral, dependency-free of WhatsApp types, and import-clean so an MCP tool wrapper can be bolted on later.
- When that later work happens, target the Streamable HTTP transport (not stdio, not the deprecated HTTP+SSE) since the backend is reachable over public HTTPS and must serve a remote agent.
- Pin an explicit protocol revision (e.g. 2025-06-18 or 2025-11-25) in any future MCP server config rather than tracking 'latest' — this spec has broken transport and batching compatibility twice in its history.
- If/when an MCP tool is added, wrap the existing single retrieval callable as exactly one `@mcp.tool()` — this maps directly onto the constraint 'one tool call per request (MCP or REST) for the future agent' and avoids exposing multiple fine-grained tools.
- Do not rely on JSON-RPC batching (removed in 2025-06-18) or on the 'experimental' tasks feature (introduced 2025-11-25) for anything production-critical.
- Any future MCP server must send/require the `MCP-Protocol-Version` header per spec (2025-06-18+) and treat the OAuth 2.1 / Resource Server authorization model as the default, since MCP's own security principles require explicit user consent before tool invocation and data exposure.

**current version:** Protocol spec: 2025-11-25 revision (latest dated changelog found on modelcontextprotocol.io); Python SDK package `mcp`: 2.3.0 (PyPI, 2026-10-02)

**api surface**
- pip install "mcp[cli]" (official Python SDK; plain `pip install mcp` if CLI tooling not needed)
- @mcp.tool() decorator to expose the existing retrieval callable as a single MCP tool (FastMCP-style, schema derived from type hints/docstring)
- Streamable HTTP transport for the MCP server (required for public-HTTPS reachability; stdio is local-subprocess only)
- JSON-RPC 2.0 base protocol methods: initialize/capability negotiation, tools/list, tools/call
- MCP-Protocol-Version HTTP header on requests after initialization (mandatory since 2025-06-18)
- OAuth 2.1 / Resource Server authorization flow if/when the MCP endpoint needs to be secured for the future agent

**pitfalls**
- Transport breaking change: original HTTP+SSE transport was replaced by Streamable HTTP in 2025-03-26 — building against the old SSE-only transport is a dead end.
- JSON-RPC batching was added in 2025-03-26 then fully removed again in 2025-06-18 — do not design the retrieval callable's MCP wrapper around batched calls.
- Authorization model changed substantially across revisions (OAuth 2.1 framework added 2025-03-26; servers reclassified as OAuth Resource Servers plus RFC 8707 Resource Indicators required for clients in 2025-06-18; OIDC Discovery and OAuth Client ID Metadata Documents added 2025-11-25) — don't hardcode an auth approach tied to one revision.
- MCP-Protocol-Version header became mandatory on HTTP transport starting 2025-06-18 — omitting it will break against spec-compliant servers/clients going forward.
- The 'tasks' feature (durable/polled requests) introduced in 2025-11-25 is explicitly marked experimental — avoid depending on it for production behavior.
- stdio transport is local-subprocess-only and cannot satisfy this build's 'reachable over public HTTPS' requirement; only Streamable HTTP fits.

*As of: 2025-11-25 is the latest dated protocol specification revision found on the official site; the official docs site itself is also publishing a 2026-07-28-dated general documentation tree built on that spec; Python SDK (`mcp`) package version 2.3.0 released 2026-10-02 per PyPI.*

**Sources**
- [Key Changes (2025-11-25 changelog) - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-11-25/changelog) (official-docs) -- "This document lists changes made to the Model Context Protocol (MCP) specification since the previous revision, 2025-06-18."
- [Introduction - Model Context Protocol](https://modelcontextprotocol.io/introduction) (official-docs) -- "MCP (Model Context Protocol) is an open-source standard for connecting AI applications to external systems."
- [Build an MCP server - Model Context Protocol](https://modelcontextprotocol.io/docs/2026-07-28/develop/build-server.md) (official-docs) -- "MCP servers can provide three main types of capabilities: Resources ... Tools ... Prompts"
- [Specification (2025-06-18) - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18) (official-docs) -- "The protocol uses JSON-RPC 2.0 messages to establish communication between: Hosts ... Clients ... Servers"
- [Key Changes (2025-06-18 changelog) - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/changelog) (official-docs) -- "Remove support for JSON-RPC batching (PR #416) ... Require negotiated protocol version to be specified via MCP-Protocol-Version header"
- [Key Changes (2025-03-26 changelog) - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-03-26/changelog) (official-docs) -- "Replaced the previous HTTP+SSE transport with a more flexible Streamable HTTP transport ... Added support for JSON-RPC batching"
- [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) (repo) -- "pip install "mcp[cli]" ... @mcp.tool() and @mcp.resource() decorators ... stdio ... Streamable HTTP ... SSE"
- [mcp · PyPI](https://pypi.org/project/mcp/) (official-docs) -- "Version: 2.3.0, Release Date: Oct 2, 2026"


### Official documentation: Alembic
*Find the OFFICIAL documentation for "Alembic": its current stable version, how it is installed or enabled, the API surface this build will use, and any breaking changes or pitfalls in the last 3 years.*

Alembic is the official SQLAlchemy migration tool; the current stable release is 1.20.1, which requires SQLAlchemy >= 2.0.0 and Python >= 3.10, matching this build's stack. Installation is via `pip install alembic` into the project's virtualenv/Docker image, with migration scripts driven by `alembic.ini` + `env.py` and the `op.*` directives. For this build, the relevant surface is `op.alter_column(..., new_column_name=...)` and `op.execute()` for the reversible gcs_* rename, paired with SQLAlchemy ORM `synonym()` (a SQLAlchemy, not Alembic, feature) so old env var/attribute names keep resolving during the transition. No breaking changes in the last 3 years block this use case, but version pinning matters because Alembic does not follow SemVer.

**Key findings**
- Current stable version is Alembic 1.20.1 per the official docs site (alembic.sqlalchemy.org), confirmed by direct fetch of the front matter page.
- Alembic 1.20.0 dropped support for SQLAlchemy versions older than 2.0.0, making 2.0.0+ the hard minimum -- aligns with this build's pinned SQLAlchemy 2.0.
- Alembic 1.17.0 raised the minimum Python version to 3.10; this build targets Python 3.12, so no compatibility gap.
- Alembic explicitly states it does NOT use SemVer -- the middle version digit marks a 'Significant Minor Release' that can include API changes/deprecations, so the docs recommend pinning to major.minor.
- `op.alter_column()` supports a `new_column_name` kwarg for plain column renames on backends (like Postgres) that support ALTER TABLE ... RENAME COLUMN directly, without needing SQLite's batch_alter_table workaround.
- `op.execute()` accepts raw SQL strings or SQLAlchemy Core constructs for custom migration logic (e.g., backfilling or dual-writing during the gcs_* rename), but the docs warn against parameterized statements in offline mode.
- Alembic 1.11.0 made most `op.*` operation parameters keyword-only (with a couple of legacy positional exceptions for `drop_index`/`drop_constraint`), relevant if copying older migration snippets from pre-2023 tutorials.
- Alembic has no native async API; for an async SQLAlchemy engine it runs migrations by wrapping the async engine's sync-style connection via `run_sync`, per the official docs summary -- relevant if the FastAPI app's engine is async.

**Recommendations**
- Pin Alembic to a specific major.minor (e.g. 1.20.x) in requirements, not just a floor, since Alembic does not use SemVer and minor releases can carry API changes.
- Implement the gcs_* rename as a single Alembic revision using `op.alter_column(table_name, 'gcs_bucket', new_column_name='object_store_bucket', ...)` (and equivalent for other renamed columns), with a symmetrical `downgrade()` that renames back -- this gives the reversible migration required by AC 5.
- Keep the SQLAlchemy-side compatibility shim as ORM `synonym()` attributes (a SQLAlchemy feature, not Alembic) mapping old attribute/env-var names to the new columns, so old env var names still resolve per AC 5 -- do not try to do this inside the Alembic migration itself.
- Since this project is on Postgres (not SQLite), plain `op.alter_column(new_column_name=...)` is sufficient; no need for `op.batch_alter_table()`, which exists mainly for SQLite's lack of native ALTER support.
- If the app's SQLAlchemy engine is async (per FastAPI), confirm the Alembic `env.py` uses the documented async-to-sync bridging pattern rather than hand-rolling connection handling, to avoid event-loop pitfalls.
- Avoid copying `op.*` call signatures from Alembic tutorials predating 1.11.0, since many parameters are now keyword-only.

**current version:** 1.20.1

**api surface**
- op.alter_column(table_name, column_name, new_column_name=..., existing_type=..., ...) -- for the reversible gcs_* column rename
- op.rename_table(old_table_name, new_table_name, schema=None) -- if any table-level renames are needed
- op.execute(sqltext) -- for custom SQL during migration (e.g. data backfill alongside rename)
- alembic.ini + env.py -- standard project configuration and migration environment wiring
- command.upgrade() / command.downgrade() -- programmatic or CLI-driven application of migrations
- --autogenerate revision generation -- to diff ORM metadata against the live schema when adding new columns

**pitfalls**
- Alembic does not use SemVer; minor version bumps (e.g. 1.19 -> 1.20) can include API/deprecation changes, so pin major.minor rather than using a loose floor.
- Alembic 1.20.0 requires SQLAlchemy >= 2.0.0 -- confirm no transitive dependency pulls in SQLAlchemy 1.4 in the Docker image.
- Alembic 1.17.0 requires Python >= 3.10 -- not an issue for this build's Python 3.12 target, but worth noting if base images are older.
- Most op.* parameters became keyword-only starting at 1.11.0; older migration examples using positional args may fail on current Alembic.
- Alembic has no first-class async API; async SQLAlchemy engines must be bridged to sync execution inside env.py, which is an easy source of event-loop bugs if copied incorrectly.

*As of: Alembic 1.20.1 (current stable per alembic.sqlalchemy.org, checked 2026-11-11)*

**Sources**
- [Front Matter - Alembic's documentation! - SQLAlchemy](https://alembic.sqlalchemy.org/en/latest/front.html) (official-docs) -- "Support for SQLAlchemy older than 2.0.0 was dropped ... Alembic does not use SemVer"
- [Changelog — Alembic 1.20.1 documentation](https://alembic.sqlalchemy.org/en/latest/changelog.html) (official-docs) -- "Alembic 1.20.0 dropped support for SQLAlchemy 1.4, requiring version 2.0.0 minimum"
- [Operation Reference — Alembic 1.20.1 documentation](https://alembic.sqlalchemy.org/en/latest/ops.html) (official-docs) -- "alter_column(table_name, column_name, *, ... new_column_name=None, ...)"


### Before/after top-k retrieval parity methodology
*How to build a fixed-query-set top-k parity check across different embeddings (overlap/rank metrics) and what a reasonable pass threshold looks like.*

Build a fixed set of real historical queries (frozen before cutover), run them through the old Vertex embeddings and the new local CPU embedder against the same chunk corpus, and compare the resulting top-k lists per query using set-overlap (Jaccard@k) and rank-order agreement (Kendall's tau/Spearman), since no relevance labels exist for this corpus to compute Recall@k/nDCG directly. Standard pgvector/ANN recall@k thresholds (0.95+) apply to approximate-vs-exact search within one embedding space and do not transfer to a cross-model swap, where lower natural overlap is expected even when both models are 'good'; treat a practical overlap bar (e.g., most of the top-10 shared) plus manual review of the lowest-overlap and best-match-changed queries as the pass criterion, and record it in the parity report required by acceptance criterion 9. Do not reuse old similarity-score cutoffs with the new embedder, since score distributions differ across models.

**Key findings**
- pgvector/ANN recall@k is computed as |approx_topk ∩ exact_topk| / k, with exact ground truth from a brute-force ORDER BY embedding <=> query LIMIT k scan; production targets commonly cited around 0.91-0.97, with 0.95+ preferred (dev.to pgvector article).
- Standard shadow-scoring practice for embedding-model migration: embed the same fixed queries with both old and new models in parallel and compare resulting top-k sets/scores before any production cutover (hackernoon article on embedding model deprecation).
- Similarity-score cutoffs do not transfer across embedding models -- a threshold tuned for one model (e.g. ada-002) may be too strict or too loose for another -- so any score-based gating must be recalibrated against the new model's own score distribution (hackernoon article).
- The MTEB framework fixes datasets/metrics (nDCG@10 as primary, with Recall@k, MRR, MAP as supplements) so scores from different embedding models are directly comparable; one reported case treated a 0.09-point nDCG@10 gap (0.546 vs 0.638) between two models as 'substantially competitive' rather than failing, illustrating that practitioners judge parity relatively, not against one universal numeric cutoff (arXiv:2607.23507).
- A dedicated vector-search-quality paper frames 'search quality difference' purely as recall loss from ANN approximation against exact nearest neighbors (reporting 11-93% recall improvements and 8-47% more queries meeting target after their fix) -- but this is an exact-vs-approximate comparison within one embedding space, not a cross-model methodology, so it is only indirectly applicable here (arXiv:2608.25185 abstract).
- Jaccard index for two top-k sets is |X∩Y|/|X∪Y| (0 = no overlap, 1 = identical sets), and Kendall's tau measures ordinal agreement via (concordant - discordant pairs) normalized to [-1,1], with 1 = perfect agreement; these are commonly used together to capture both 'same items retrieved' and 'same order' when comparing two ranked result lists [uncertain] (from search-tool synthesis; I was not able to render the full text of the primary arXiv papers that define this to confirm firsthand).
- The academic papers surfaced as leads for this item (Sentence-T5, RALM robustness, POJK regulatory retrieval benchmark, actinide electronic structure, TwinBERT) are either unrelated to parity methodology (actinide chemistry) or address embedding quality/robustness in general rather than before/after cross-model top-k parity measurement specifically -- none were directly useful for this item's methodology question.

**Recommendations**
- Freeze a fixed query set of real/representative historical bot queries (tens to a couple hundred) before cutover; reuse this exact set for every parity run and for the re-embed job's recorded comparison (acceptance criterion 9).
- For each query, compute top-k (match the bot's production k) under the old Vertex embeddings (snapshotted) and the new local CPU embedder over the same chunk/title corpus, and store both ranked lists plus scores in the parity report artifact.
- Use Jaccard/overlap@k as the primary per-query metric and mean overlap across the fixed set as the aggregate pass/fail signal, supplemented by Kendall's tau or Spearman correlation on the ordering of shared items -- these require no relevance labels, unlike Recall@k/nDCG/MAP.
- Do not import the 0.95 ANN recall@k bar used for approximate-vs-exact HNSW tuning as the bar for this cross-model comparison; that threshold measures approximation error within one embedding space. Pick and document an explicit, lower bar instead (e.g. most of the top-10 shared) and treat it as a starting heuristic to be revised after reviewing actual results, not a hard industry standard.
- Specifically flag and manually review any query where the single top-ranked ('best match') chunk differs between old and new embeddings -- for a past-paper lookup bot, losing the single best answer matters more than reordering within the rest of the top-k.
- Do not carry over any existing cosine-similarity cutoffs/gating logic unchanged; recompute them against the new local embedder's own score distribution before relying on them.
- Since this corpus has no human relevance judgments, don't attempt to compute true Recall@k/nDCG/MAP for the parity report; rely on overlap + rank-correlation + targeted manual spot-check of the lowest-overlap queries as the acceptance evidence instead.

*As of: November 2026; underlying sources dated 2021-2026, dev.to/hackernoon articles undated but current as retrieved, arXiv:2607.23507 (2026), arXiv:2608.25185 (2026)*

**Sources**
- [pgvector in Production: Index Types, Recall, and Tradeoffs](https://dev.to/veduis/pgvector-in-production-index-types-recall-and-tradeoffs-16k) (article) -- "run a brute-force ORDER BY embedding <=> query LIMIT 10 (which bypasses the index) as ground truth... If the true 10 nearest documents are A through J and your index returns 8 of them, recall@10 is 0.8."
- [Your Embedding Model Will Deprecate. Here's What to Do.](https://hackernoon.com/your-embedding-model-will-deprecate-heres-what-to-do) (article) -- "embed live queries with both models in parallel, serve results from the old index, and log what the new model would have returned... A threshold of 0.85 that worked well with ada-002 may be too aggressive or too permissive with text-embedding-3-small."
- [Choosing a Text Embedding Model: A Practical Benchmarking and Decision Framework](https://arxiv.org/html/2607.23507v1) (paper) -- "fixes the datasets, task categories, and evaluation metrics used for each type of task, so that a score obtained by one model is directly comparable to another... mE5-L scored within 0.09 nDCG points of T3EM (0.546 vs. 0.638)"
- [Analyzing and Reducing Search Quality Differences in Vector Similarity Search](https://arxiv.org/pdf/2608.25185) (paper) -- "Modern database services scalably search over large data collections via Approximate Nearest Neighbor Search, which improves search performance at the cost of search quality, measured by recall."


### pgvector HNSW re-embedding without schema change
*How to re-embed existing rows into an unchanged Vector(768) column with an HNSW index and keep pg_trgm hybrid search working.*

A re-embed script should leave the Vector(768) column type and HNSW index definition untouched, but must avoid writing new vectors row-by-row into a live HNSW graph because pgvector explicitly documents that building an HNSW index after bulk data load is much faster than inserting into an existing one. The safe pattern is: DROP the HNSW index, bulk UPDATE all rows with the new local-model embeddings, then CREATE INDEX ... USING hnsw again with maintenance_work_mem sized for the graph. pg_trgm's GIN/GiST trigram indexes live on separate text columns with a separate access method, so they are unaffected by this and keep working for hybrid search throughout. REINDEX INDEX CONCURRENTLY is an alternative if a drop/rebuild window is unacceptable, but it is slower overall and not an atomic single-step swap.

**Key findings**
- pgvector's official README (GitHub, master, opened 2026-11-11) states: "it's faster to create an index after loading your initial data" -- the documented bulk-load pattern is load/update data first, then build the HNSW index, not insert/update into a pre-existing index.
- Same README: set maintenance_work_mem large enough to hold the graph (example given: SET maintenance_work_mem = '8GB'); if exceeded, Postgres emits NOTICE: hnsw graph no longer fits into maintenance_work_mem after N tuples and falls back to a much slower build path.
- PostgreSQL official docs (postgresql.org/docs/current/sql-reindex.html, current version, opened 2026-11-11): REINDEX INDEX CONCURRENTLY does not take locks that block concurrent inserts/updates/deletes, but is NOT a single atomic swap -- it runs as a documented multi-step, multi-transaction sequence ending in pg_index.indisvalid flips and a cache invalidation; it cannot run inside a transaction block and takes longer overall than a blocking rebuild.
- pgvector/pgvector GitHub issue #810 (opened and read, maintainer-confirmed): HNSW insert/update throughput collapses with non-default parameters -- using m=64/ef_construction=128 instead of defaults m=16/ef_construction=64 took 378s vs 19s for 10,000 insertions in the maintainer's reproduction; tables with multiple vector-indexed columns also lose HOT-update eligibility, forcing every index to be maintained on each row update.
- PostgreSQL official docs (postgresql.org/docs/current/pgtrgm.html, opened 2026-11-11): pg_trgm provides its own GiST (gist_trgm_ops) and GIN (gin_trgm_ops) operator classes on text columns, entirely separate from vector index access methods like HNSW on other columns -- both can exist on the same table independently and neither rebuild affects the other.
- [uncertain] No official pgvector documentation explicitly covers a bulk-UPDATE/re-embed workflow for existing rows; the README's drop-index/load/rebuild guidance is written for initial bulk INSERT/COPY loads, so applying the same drop-and-rebuild pattern to a mass UPDATE of pre-existing rows is a reasonable extrapolation, not an explicitly documented procedure.

**Recommendations**
- In the re-embed job: DROP the existing HNSW index on the embedding column (schema/column type Vector(768) stays unchanged), run the bulk UPDATE of chunk and title embeddings from the new local CPU model, then CREATE INDEX ... USING hnsw again -- do not update rows against a live HNSW index.
- Set maintenance_work_mem for the session running CREATE INDEX to comfortably fit the HNSW graph for the current row count, and watch Postgres logs for the 'graph no longer fits' NOTICE as a signal to raise it.
- Keep HNSW build parameters at pgvector defaults (m=16, ef_construction=64) unless a specific benchmark justifies otherwise -- issue #810 shows higher values can cause order-of-magnitude slowdowns on write-heavy operations like a full re-embed.
- Do not touch or rebuild the pg_trgm GIN/GiST index during the re-embed; it indexes separate text columns via a separate access method and keeps serving the pg_trgm half of hybrid search throughout the embedding swap.
- Run the drop-index/bulk-update/rebuild sequence in a maintenance window rather than REINDEX INDEX CONCURRENTLY, since this is a one-time offline migration script (Phase 6 scripts are not executed live per the PRD) and the concurrent variant is slower and more operationally complex for no benefit here.
- After rebuilding, run the required parity report (old vs new top-k on the fixed query set) to confirm the index rebuild plus new embeddings did not regress retrieval quality before treating the re-embed as complete.

*As of: pgvector README (GitHub master branch) and PostgreSQL current-version docs (sql-reindex.html, pgtrgm.html) as fetched 2026-11-11; pgvector issue #810 reflects HNSW behavior since its introduction in pgvector v0.5.0.*

**Sources**
- [pgvector/pgvector README.md](https://github.com/pgvector/pgvector/blob/master/README.md) (repo) -- "Like other index types, it's faster to create an index after loading your initial data... NOTICE: hnsw graph no longer fits into maintenance_work_mem after 100000 tuples"
- [PostgreSQL: Documentation: REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html) (official-docs) -- "PostgreSQL will rebuild the index without taking any locks that prevent concurrent inserts, updates, or deletes on the table... Each step is run in a separate transaction."
- [Inserting into a pgvector table with an HNSW index is very slow, And update more slow #810](https://github.com/pgvector/pgvector/issues/810) (repo) -- "The high value of m is the primary reason this is slow. Using the default m of 16 and ef_construction of 64 will speed it up significantly."
- [PostgreSQL: Documentation: pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html) (official-docs) -- "The pg_trgm module provides GiST and GIN index operator classes that allow you to create an index over a text column for the purpose of very fast similarity searches."


### HMAC-signed expiring download URLs
*Patterns for backend-issued short-lived HMAC-signed URLs (~15 min) with tamper and expiry rejection, over filesystem and MinIO/S3 storage.*

For this build, the cleanest pattern is a custom HMAC-SHA256 signed URL (not raw S3/MinIO presigned URLs) issued by the ObjectStore port, because the backend must work identically over local filesystem and MinIO/S3, and MinIO/S3 presigned URLs only cover S3-protocol objects, not plain disk files. The standard shape is: sign a payload of (object key/path, expiry timestamp) with HMAC-SHA256 and a server-held secret, append the expiry and signature as query params, and on each download request recompute the HMAC over the same canonical string and reject on mismatch (tamper) or on expiry timestamp in the past. Python's itsdangerous.URLSafeTimedSerializer implements exactly this pattern (HMAC-based TimestampSigner, loads(token, max_age=900) raising SignatureExpired vs BadSignature) and is commonly used for exactly this purpose in FastAPI download-link endpoints. If/when the MinIO backend is used directly, MinIO's own presigned_get_object/get_presigned_url already produce AWS SigV4 (HMAC-SHA256) signed URLs with configurable expiry (1 second to 7 days, default 7 days) and built-in tamper/expiry rejection, so the ObjectStore adapter can either wrap those natively for MinIO/S3 or apply its own HMAC layer uniformly across both backends for one consistent 15-minute contract.

**Key findings**
- itsdangerous.TimestampSigner/URLSafeTimedSerializer uses HMAC (HMACAlgorithm) with hashlib.sha1 as the default digest method, per the itsdangerous signer.py source; digest_method and algorithm are both overridable (e.g. to sha256).
- itsdangerous loads(token, max_age=N) raises SignatureExpired when signature age exceeds max_age (docs example: 'Signature age 15 > 5 seconds') and raises BadSignature when the signature/content is tampered with; both are distinct exception types that should be caught separately per itsdangerous's timed-signing docs.
- A documented FastAPI pattern (mephisto.cc) signs a payload (e.g. recipient/user identifier) with URLSafeTimedSerializer, embeds the token in the download URL path, and on request calls loads(token, max_age=600) to enforce a 10-minute expiry while returning FileResponse only on success -- directly analogous to a 15-minute filesystem download link.
- boto3 S3 generate_presigned_url signs with AWS Signature Version 4; ExpiresIn is in seconds, commonly defaulting to 3600 (1 hour) with AWS enforcing presigned URLs cannot exceed 7 days, and the effective expiry is the minimum of the signing credentials' expiry and the requested ExpiresIn, per AWS's boto3 presigned-URL guide.
- AWS's presigned-URL mechanism embeds X-Amz-Algorithm, X-Amz-Credential, X-Amz-Date, and X-Amz-Signature in the URL; any change to bucket, key, method, or query parameters invalidates the SigV4 signature and the request is rejected -- confirmed on docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html.
- MinIO's Python SDK (presigned_get_object, get_presigned_url) signs with AWS4-HMAC-SHA256 (SigV4), takes `expires` as a datetime.timedelta between 1 second and 7 days (default 7 days), and binds expiry into the canonical request via X-Amz-Expires so the duration is cryptographically part of the signature -- confirmed from minio-py's signer.py source and the official Python Client API reference.
- Because MinIO/S3 presigned URLs are protocol-specific to object storage, they cannot be issued for a local filesystem path; any filesystem-backed ObjectStore implementation must implement its own HMAC-signed URL scheme (e.g. itsdangerous-style) to meet the uniform 15-minute signed-URL contract required across both backends.

**Recommendations**
- Implement the ObjectStore port's signed-URL contract as a backend-agnostic HMAC-SHA256 signer (e.g. itsdangerous URLSafeTimedSerializer with digest_method=hashlib.sha256, or a hand-rolled HMAC over 'object_key|expiry_ts') so filesystem and MinIO/S3 backends behave identically to callers.
- Set max_age/expiry to ~900 seconds (15 minutes) explicitly per the PRD; do not rely on itsdangerous's SHA-1 default without upgrading digest_method to SHA-256 for a stronger tamper guarantee.
- Catch SignatureExpired and BadSignature (or their HMAC-recompute equivalents) as distinct error paths and return 403/410 rather than a generic 404, so expired vs tampered links are distinguishable in logs for ops/runbook purposes.
- If a MinIO backend is used, consider delegating directly to MinIO's native presigned_get_object with expires=timedelta(minutes=15) for that backend, but keep the filesystem backend's custom HMAC signer behaviorally equivalent (same expiry window, same rejection semantics) so the port abstraction holds.
- Never embed the raw storage path or secret key material in the token payload beyond what's needed to resolve the object; sign only an opaque object identifier plus expiry, and keep the HMAC secret in the Secrets port, not hardcoded, consistent with acceptance criterion 7.
- Add unit tests (no network calls, acceptance criterion 2) that directly exercise the signer: valid token within window, expired token past ~15 min, and a tampered token (flipped byte / modified expiry) to assert rejection -- this maps directly to acceptance criterion 6.

*As of: boto3/AWS S3 presigned URL docs and MinIO Python SDK API reference as fetched 2026-11-11; itsdangerous docs are for the 2.2.x 'stable' release line as fetched 2026-11-11; dated web articles referenced were published 2026*

**Sources**
- [Presigned URLs - Boto3 documentation (redirected to docs.aws.amazon.com)](https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html) (official-docs) -- "Any modification to the URL (bucket name, object key, parameters) invalidates the signature ... AWS limits presigned URLs to a maximum of 7 days (604,800 seconds)"
- [Python Client API Reference - MinIO](https://docs.min.io/aistor/developers/sdk/python/api/) (official-docs) -- "presigned_get_object(bucket_name, object_name, expires=timedelta(days=7), ...)"
- [minio-py signer.py (GitHub source)](https://github.com/minio/minio-py/blob/master/minio/signer.py) (repo) -- "X-Amz-Algorithm=AWS4-HMAC-SHA256 ... X-Amz-Expires={expires}"
- [URL Safe Serialization — ItsDangerous Documentation (2.2.x)](https://itsdangerous.palletsprojects.com/en/stable/url_safe/) (official-docs) -- "Works like TimedSerializer but dumps and loads into a URL safe string"
- [Timed Signature Verification — ItsDangerous Documentation](https://itsdangerous.palletsprojects.com/en/stable/timed/) (official-docs) -- "raises SignatureExpired ... Signature age 15 > 5 seconds"
- [itsdangerous signer.py (GitHub source)](https://github.com/pallets/itsdangerous/blob/main/src/itsdangerous/__init__.py) (repo) -- "The default is hashlib.sha1, but can be changed to any hashlib compatible object ... if algorithm is None: algorithm = HMACAlgorithm(self.digest_method)"
- [Fastapi simply implements temporary download links | mephisto.cc](https://mephisto.cc/en/tech/temporary-download/) (article) -- "s.loads(token, max_age=60 * 10) ... SignatureExpired ... BadSignature"


### ObjectStore abstraction over filesystem and MinIO
*How to design one ObjectStore interface backing both local filesystem and MinIO (S3 API) for put/get/signed-url in Python.*

Define a single ObjectStore protocol with put(key, data) -> None, get(key) -> bytes/stream, and signed_url(key, expires_in, method='GET') -> str, then implement it twice: a LocalFileSystemObjectStore that writes under a root directory and signs URLs with HMAC-SHA256 over path+expiry+method (verified by a FastAPI route), and a MinioObjectStore (or boto3 S3 client pointed at the MinIO endpoint via endpoint_url) that calls the native presigned_get_object/presigned_put_object methods. Both backends are selected behind the existing provider-setting port, so GCS stays available as a third implementation without changing call sites. MinIO's Python SDK and boto3 both cap presigned URLs at a 7-day SigV4 maximum with no built-in equivalent for plain filesystem storage, so the local backend needs its own expiry-enforcing signer to produce comparable ~15-minute, tamper-rejecting URLs for acceptance criterion 6.

**Key findings**
- AWS S3 presigned URLs created via SDK/CLI (SigV4) support expiry up to 7 days (604800s); console UI caps at 12 hours; boto3 generate_presigned_url defaults to 3600s via ExpiresIn.
- S3 checks presigned URL expiry at request time, not at download start, and a SignatureDoesNotMatch error is returned for any tampered or re-signed query string parameter.
- If temporary/STS credentials were used to sign, the URL expires when those credentials expire even if ExpiresIn specifies longer -- relevant if the ObjectStore ever uses role-based creds instead of static keys.
- minio-py presigned_get_object, presigned_put_object, and the generic get_presigned_url all default expires to timedelta(days=7); the fetched SDK reference page did not state an enforced maximum, so MinIO-side enforcement of the 7-day SigV4 cap is [uncertain].
- boto3's generate_presigned_url works unmodified against MinIO by passing endpoint_url to the S3 client, so a single boto3-based implementation can serve both AWS S3 and MinIO without a MinIO-specific SDK.
- obstore (Rust-backed Python lib) exposes one interface (LocalStore, S3Store, GCSStore, AzureStore, MemoryStore) with uniform put/get/copy/delete/list/rename plus a sign() function, confirming the cross-backend interface pattern is an established design, though its LocalStore signing behavior was not independently verified from the fetched page.
- A documented FastAPI pattern for local-filesystem signed URLs: encode path+expiry as an int Unix timestamp query param, compute HMAC-SHA256 over a canonical string (e.g. 'v1\n{file_id}\n{exp}') with a server-held secret, and verify with hmac.compare_digest to prevent timing attacks and reject tampering; expiry is checked with a simple int(time.time()) > expires comparison.

**Recommendations**
- Define the ObjectStore port as a small Python Protocol (put, get, delete, signed_url) with signed_url returning a plain https URL string so callers never branch on backend type.
- Implement the MinIO backend with boto3's S3 client (endpoint_url=minio_url, addressing_style if needed) rather than minio-py, so the same code path also works unmodified against real S3/GCS-interop later; use generate_presigned_url(ClientMethod='get_object', ExpiresIn=~900) to hit the ~15-minute target in acceptance criterion 6.
- Implement the filesystem backend's signed_url with HMAC-SHA256 over a canonical string containing object key, expiry, and (recommended) HTTP method, verified via hmac.compare_digest in a dedicated FastAPI download route that 403s on bad signature and 410/403 on expiry -- do not invent a filesystem-native signing scheme.
- Keep expiry comparison server-side and based on wall-clock Unix timestamp in both backends so '~15 minutes' and 'rejected after expiry' behave identically regardless of provider, satisfying the before/after parity requirement.
- Do not rely on STS/temporary credentials for the MinIO/S3 backend unless the expiry contract is re-verified, since those presigned URLs expire early when the underlying credential session ends, independent of ExpiresIn.
- Treat MinIO's enforcement of the SigV4 7-day cap as unverified; since the target expiry (~15 min) is far below that cap, this gap doesn't block the build, but don't assume MinIO silently extends expiry beyond 7 days if that assumption is ever needed elsewhere.

*As of: 2026-11 (AWS S3 docs undated page, retrieved 2026-11-11; MinIO Python SDK reference page, retrieved 2026-11-11)*

**Sources**
- [Download and upload objects with presigned URLs - Amazon Simple Storage Service](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html) (official-docs) -- "If you use the AWS CLI or AWS SDKs, the expiration time can be set as high as 7 days... Amazon S3 checks the expiration date and time of a signed URL at the time of the HTTP request."
- [MinIO Python Client API Reference](https://docs.min.io/aistor/developers/sdk/python/api/) (official-docs) -- "presigned_get_object(bucket_name, object_name, expires=timedelta(days=7), ...)"
- [Getting Started - obstore](https://developmentseed.org/obstore/latest/getting-started/) (official-docs) -- "All operations for interacting with a store are exported as top-level functions (not methods on the store object)."
- [Build A Signed Download URL Generator In FastAPI](https://web.learnmodernpython.com/build-a-signed-download-url-generator-in-fastapi/) (article) -- "Create an HMAC object using SHA256... if int(time.time()) > expires: return False... uses hashlib.compare_digest() rather than simple equality checks"


### Reversible column rename via SQLAlchemy synonyms
*How to rename a DB column (gcs_* -> object_key) with a reversible migration while keeping old attribute access via synonyms and old env names working.*

For a SQLAlchemy 2.0 Declarative model, rename the physical column with a reversible Alembic migration using `op.alter_column(table, 'gcs_key', new_column_name='object_key')` (and the mirrored rename in `downgrade()`), then update the ORM model so the new name (`object_key`) is the real `mapped_column` and add `gcs_key = synonym('object_key')` so old code/tests reading `.gcs_key` keep working. `synonym()` works out-of-the-box with Declarative/`mapped_column` for this simple aliasing case; the `map_column=True` flag some tutorials mention is only for classical mappings against an explicit `Table` object and is unnecessary here. For env vars, keep both old and new names resolving by setting `validation_alias=AliasChoices('OBJECT_STORE_KEY', 'GCS_KEY')` (new name first) on the pydantic-settings field, so either env var populates the same setting.

**Key findings**
- SQLAlchemy 2.0 `synonym(name, *, map_column=None, descriptor=None, ...)` creates an attribute that mirrors another mapped attribute; for plain Declarative classes you just write `old_attr = synonym('new_attr')` after defining `new_attr` as the real `mapped_column`.
- `map_column=True` is documented as applying 'for classical mappings and mappings against an existing Table object only' — it is not the mechanism needed for a `Mapped`/`mapped_column` Declarative model.
- Official SQLAlchemy example for Declarative: `job_status = mapped_column(String(50)); status = synonym('job_status')` — confirms the simple rename-with-alias pattern works directly on Declarative Base classes.
- Alembic's `alter_column()` takes an explicit `new_column_name` kwarg specifically for rename operations; autogenerate does NOT detect renames on its own (it sees a drop+add and would lose data), so the rename migration must be written/edited by hand.
- Alembic docs do not mandate `existing_type` for a pure rename on PostgreSQL (it's required on MySQL to avoid losing the default, and for SQLAlchemy 'schema' types like Boolean/Enum); supplying it anyway is harmless and safer across backends.
- A rename migration is trivially reversible: `downgrade()` just calls `alter_column` again with the old/new names swapped.
- pydantic-settings `AliasChoices('new_env_name', 'old_env_name')` passed to `validation_alias` lets a field be populated by either env var name; 'the first environment variable that is found will be used', so order choices to prefer the new name but still fall back to the old one.
- `alias=` (vs `validation_alias=`) affects both validation and serialization; for a one-directional backward-compat read (old env var still works, but new docs/compose files use the new name) `validation_alias` alone is the right tool.

**Recommendations**
- Write the Alembic migration as `op.alter_column('objects', 'gcs_key', new_column_name='object_key', existing_type=sa.String())` in `upgrade()`, and the exact inverse in `downgrade()` — this satisfies the 'reversible' acceptance criterion directly.
- In the ORM model, make `object_key` the real `mapped_column` and add `gcs_key = synonym('object_key')` (and similarly for any other `gcs_*` attributes) so existing code/tests that still reference `.gcs_key` need zero changes.
- Do not use `map_column=True` — it's for classical/Table-based mappings; plain `synonym('object_key')` is sufficient and is the pattern shown in SQLAlchemy's own Declarative docs.
- For every renamed env var, declare `validation_alias=AliasChoices('OBJECT_STORE_KEY', 'GCS_KEY')` (new name first) on the pydantic-settings field so the pre-existing GCS-named env vars in deployment configs keep resolving without edits, satisfying the acceptance criterion that old env variable names still resolve.
- Grep the codebase/tests for raw SQL or `.c.gcs_key`/`text()` references to the physical column name after the Alembic rename — the ORM synonym fixes Python attribute access but not raw SQL strings, which must be updated to `object_key`.
- Keep the rename migration and the synonym addition in the same PR/commit so the reversible-migration and backward-compatible-attribute requirements are verifiably tied together.

*As of: SQLAlchemy 2.0 docs and Alembic latest docs as fetched 2026-11-11; pydantic-settings docs page fetched 2026-11-11 did not display an explicit version number for the AliasChoices example [uncertain].*

**Sources**
- [Changing Attribute Behavior — SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/orm/mapped_attributes.html) (official-docs) -- "For classical mappings and mappings against an existing Table object only. if True, the synonym() construct will locate the Column object..."
- [Changing Attribute Behavior — SQLAlchemy 2.0 Documentation (synonyms section)](https://docs.sqlalchemy.org/en/20/orm/mapped_attributes.html#synonyms) (official-docs) -- "class MyClass(Base): __tablename__ = "my_table"; id = mapped_column(Integer, primary_key=True); job_status = mapped_column(String(50)); status = synonym("job_status")"
- [Alembic Operation Reference — alter_column](https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.alter_column) (official-docs) -- "Optional; specify a string name here to indicate the new name within a column rename operation."
- [Pydantic Settings Management](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/) (official-docs) -- "The AliasChoices class allows you to have multiple environment variable names for a single field. The first environment variable that is found will be used."


### Docker Compose Postgres+pgvector deploy and backup
*Compose setup for Postgres with pgvector/pg_trgm, health checks, nightly pg_dump backup and restore drill, and HTTPS reverse proxy guidance.*

Use the official pgvector/pgvector Docker image (adds pgvector to the stock postgres image) as the Compose db service, enable both `vector` and `pg_trgm` via CREATE EXTENSION (both are standard/trusted contrib extensions, no superuser needed for pg_trgm), and set shm_size for parallel HNSW index builds. Health-check the db with pg_isready forced over TCP (-h 127.0.0.1) rather than the default socket probe, because the official Postgres image listens only on a Unix socket during initdb and a socket-based pg_isready can report healthy before the real TCP listener exists, releasing dependents into ECONNREFUSED. For backups, run a scheduled pg_dump (custom format, -Fc) from a sidecar/cron job or host cron into mounted/object storage, and periodically prove restorability by loading the newest dump into a throwaway Postgres container rather than trusting dump success alone. For HTTPS, front the bot container with a reverse proxy (e.g. Caddy) that terminates TLS automatically via Let's Encrypt and forwards to the app's internal port.

**Key findings**
- pgvector ships prebuilt Docker images pgvector/pgvector:pgXX (Postgres 13-18, e.g. pg18-trixie/pg18-bookworm) that layer the extension onto the official postgres image; enable with `CREATE EXTENSION vector;` (pgvector GitHub README, build example references pgvector v0.8.7).
- pgvector README recommends sizing Docker shared memory (e.g. --shm-size or shm_size in compose) to at least the configured maintenance_work_mem when doing parallel HNSW index builds, to avoid build errors.
- pg_trgm is a 'trusted' contrib extension per PostgreSQL docs (checked against the Postgres 18 docs page): any DB user with CREATE privilege can run `CREATE EXTENSION pg_trgm;` without superuser; typical indexes use GIST/GIN with gist_trgm_ops/gin_trgm_ops.
- Official postgres Docker image docs (docker-library/docs) state the data volume must be mounted at /var/lib/postgresql/data for Postgres 17 and earlier (mounting at the parent /var/lib/postgresql will not persist data across recreation); Postgres 18+ moved PGDATA under a version-specific path and the mount point changed to /var/lib/postgresql.
- docker-library/postgres PR #440 documents that the official image sets listen_addresses='' during initdb so the server is reachable only via a Unix socket at that stage, specifically to stop healthchecks from passing on a not-yet-ready server; the final server does listen on TCP.
- Multiple 2025-era GitHub fix PRs (e.g. docker-library/postgres#440 and several app-repo compose fixes found via search) converge on the same remedy: run pg_isready with an explicit host flag, e.g. `pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"`, so the healthcheck only passes once the real TCP listener is accepting connections; a bare `pg_isready` (which defaults to the socket) can report ready during the init-only socket phase.
- A commonly cited compose healthcheck pattern is `test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]` with `start_period` set (e.g. 10s) to tolerate normal first-boot init time without flapping to unhealthy [uncertain].
- Standard single-database backup/restore commands: `pg_dump -U <user> -Fc <db> > backup.dump` for a custom-format dump, and `pg_restore --clean --if-exists -U <user> -d <db> backup.dump` (or plain-SQL `pg_dump ... > backup.sql` / `psql ... < backup.sql`) to restore.
- docker-postgres-cron-backup (mentos1386/docker-postgres-cron-backup, GitHub) is a sidecar image that runs scheduled pg_dump jobs via cron inside Compose, configured through POSTGRES_HOST/PORT/USER/PASS (or PASS_FILE for Docker secrets), CRON_TIME (default Sundays 03:00 UTC, adjustable to nightly), MAX_BACKUPS for retention, and ships a restore.sh for restoring a chosen backup back into Postgres.
- A widely-recommended restore-drill pattern (multiple 2025-2026 blog posts, e.g. dev.to restore-drill articles) is to spin up a disposable Postgres container of the same major version, restore the latest backup into it, and run validation queries/errors-fatal checks, scheduled (e.g. monthly or nightly) via cron/CI rather than assuming a successful dump implies a restorable backup.
- Caddy's documented quick-start reverse-proxy setup automatically serves HTTPS once it is given a real hostname: a two-line Caddyfile (`example.com` / `reverse_proxy :9000`) is enough for Caddy to obtain a publicly-trusted certificate via its automatic TLS; for `localhost`/`.localhost` it issues a self-signed cert instead.

**Recommendations**
- Base the db service on pgvector/pgvector:pgXX-bookworm (pin an explicit Postgres major matching the current schema) rather than the bare postgres image, so the vector extension binary ships with the image; still run `CREATE EXTENSION vector;` and `CREATE EXTENSION pg_trgm;` as init SQL or migration, since the extension objects themselves are not auto-created.
- Write the db healthcheck as `pg_isready -h 127.0.0.1 -U <user> -d <db>` with a start_period of 10-30s, not a bare `pg_isready`, to avoid the documented false-healthy window during initdb's socket-only phase; gate `depends_on: condition: service_healthy` on this check for the bot and (if used) MinIO services.
- Set `shm_size` (e.g. 256m-1g) on the Postgres service in compose if maintenance_work_mem is raised for HNSW builds, per pgvector's own Docker guidance.
- Run nightly pg_dump in custom format (-Fc) to a bind-mounted or MinIO-backed backup path via either host cron or a small cron sidecar (docker-postgres-cron-backup is a usable off-the-shelf option); keep a bounded retention count and avoid plaintext credentials in the compose file (use env_file/secrets).
- Treat 'backup exists' as insufficient: implement a restore drill that loads the most recent dump into a throwaway Postgres container (same major version, with pgvector/pg_trgm extensions installed) and run a sanity query (e.g. row counts, a known embedding row) before considering the backup verified; document this drill in RUNBOOK and schedule it periodically rather than only on-demand.
- Put a reverse proxy (Caddy is the simplest for automatic Let's Encrypt HTTPS; nginx+certbot is an alternative if more config control is needed) in its own compose service in front of the bot container, forwarding only the app port and terminating TLS there; do not expose Postgres or MinIO ports publicly.
- Document exact startup order and expected healthy states (db -> optional MinIO -> bot -> proxy) in README/RUNBOOK so `docker compose up` is reproducible on the school's Linux server without GCP-specific assumptions.

*As of: 2026-11 (pgvector README referencing v0.8.7 and pg18 image tags; PostgreSQL 18 docs for pg_trgm; docker-library/postgres PR #440 fix for init-time healthcheck false positives; Caddy current docs quick-start)*

**Sources**
- [pgvector/pgvector GitHub README](https://github.com/pgvector/pgvector) (repo) -- "This image adds pgvector to the postgres image... docker pull pgvector/pgvector:pg18-trixie"
- [mentos1386/docker-postgres-cron-backup](https://github.com/mentos1386/docker-postgres-cron-backup) (repo) -- "Docker image to backup all your databases periodically... CRON_TIME ... MAX_BACKUPS ... restore.sh"
- [docker-library/docs postgres README (via Docker Hub)](https://hub.docker.com/_/postgres) (official-docs) -- "Mount the data volume at /var/lib/postgresql/data and not at /var/lib/postgresql because mounts at the latter path WILL NOT PERSIST database data when the container is re-created."
- [docker-library/postgres PR #440](https://github.com/docker-library/postgres/pull/440) (repo) -- "If the list is empty, the server does not listen on any IP interface at all, in which case only Unix-domain sockets can be used to connect to it."
- [pg_isready healthcheck TCP-vs-socket fix PRs (search aggregate)](https://github.com/docker-library/postgres/pull/440) (repo) -- "Passing -h 127.0.0.1 forces a TCP probe, which tracks the real listener in every phase"
- [PostgreSQL 18 Documentation: pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html) (official-docs) -- "This module is considered "trusted", that is, it can be installed by non-superusers who have CREATE privilege on the current database."
- [Caddy reverse proxy quick start](https://caddyserver.com/docs/quick-starts/reverse-proxy) (official-docs) -- "Caddy will serve your proxy over HTTPS automatically and by default if it knows the hostname (domain name)."


### Channel-neutral handler and MCP/REST tool endpoint
*How to structure a channel-neutral InboundMessage/handle_inbound core and an authed single-call retrieval endpoint callable later by Copilot Studio (MCP or REST).*

Build a pure, channel-agnostic core: an InboundMessage/OutboundMessage pydantic model plus a handle_inbound(message) function and a retrieve(query, top_k) callable that import no WhatsApp or Teams types; WhatsApp becomes a thin FastAPI webhook adapter that translates Meta/Twilio payloads into InboundMessage and translates replies back. For Copilot Studio, expose the same retrieval callable twice from one FastAPI app: as a normal authed REST route, and as an MCP tool mounted on the app (via FastMCP's from_fastapi/http_app mount or the fastapi_mcp library), secured with FastAPI Depends()-based API-key auth so it matches Copilot Studio's built-in 'API key' MCP auth option. Copilot Studio only speaks the Streamable HTTP MCP transport (SSE support was dropped after August 2025), making one POST per tool call to /mcp -- consistent with the one-tool-call-per-request requirement. A future Teams adapter can be added later as another thin adapter producing the same InboundMessage, with zero changes to handle_inbound or the retrieval callable.

**Key findings**
- FastMCP supports generating an MCP server from an existing FastAPI app via FastMCP.from_fastapi(app=app) (new in FastMCP 2.0.0), using the app's OpenAPI spec (v3.0.0+) to build tools.
- FastMCP supports mounting an MCP server INTO a FastAPI app (new in FastMCP 2.3.1): mcp_app = mcp.http_app(path='/mcp'); app = FastAPI(lifespan=mcp_app.lifespan); app.mount('/analytics', mcp_app) -- the FastAPI app's lifespan must wrap the MCP app's lifespan to initialize the session manager.
- fastapi_mcp (tadata-org/fastapi_mcp on GitHub) mounts as a native ASGI extension of FastAPI (no extra HTTP hop) via FastApiMCP(app).mount(), exposing the server at /mcp, and lets you secure MCP endpoints with the same FastAPI Depends() auth used for REST routes.
- Microsoft Learn (updated 2026-11-02): Copilot Studio currently supports only the MCP 'Streamable' transport; SSE transport is deprecated and Copilot Studio stopped supporting SSE for MCP after August 2025.
- Copilot Studio's MCP onboarding wizard offers three auth types for an existing MCP server: None, API key (header or query), and OAuth 2.0 (dynamic discovery, dynamic, or manual) -- API key via header is the simplest fit for a single authed FastAPI-hosted tool.
- When Copilot Studio connects to an MCP server, it generates a Power Platform custom connector with a single OpenAPI action (e.g. operationId InvokeMCP/InvokeServer) tagged x-ms-agentic-protocol: mcp-streamable-1.0, which issues one Streamable-HTTP POST to the server's /mcp path per tool list/call -- matching a 'one tool call per request' design.
- fastapi_mcp documentation states it preserves FastAPI request/response schemas and Swagger descriptions when converting routes to MCP tools, so a single well-typed retrieval endpoint (query, top_k, filters in; ranked results out) converts cleanly into one MCP tool without extra glue code.

**Recommendations**
- Define InboundMessage/OutboundMessage as pydantic models (channel enum, sender_id, text, attachments, metadata) in a channel-neutral module; handle_inbound(msg: InboundMessage) -> OutboundMessage must not import whatsapp_* or teams_* types.
- Extract the retrieval logic into a single pure callable, e.g. retrieve(query: str, top_k: int, filters) -> list[Result], with no FastAPI Request/Response or WhatsApp types in its signature so it is directly reusable by handle_inbound and by the MCP/REST tool.
- Keep WhatsApp integration as a thin adapter: a FastAPI webhook route that parses the Meta/Twilio payload into InboundMessage, calls handle_inbound, and formats the OutboundMessage back into the WhatsApp-specific reply shape; this is the only place WhatsApp-specific types may appear.
- Expose retrieval twice from the same FastAPI app for the future Copilot Studio agent: a plain authed REST endpoint, and an MCP tool mounted at /mcp using FastMCP.from_fastapi or fastapi_mcp's FastApiMCP(app).mount(), reusing the same FastAPI Depends()-based auth for both.
- Secure the MCP/REST tool with a simple header API key (not OAuth) initially, since Copilot Studio's wizard supports API-key auth out of the box and it is the lowest-friction match for a single internal tool; add OAuth later only if multi-tenant access control is required.
- Ensure the MCP mount uses Streamable HTTP (FastMCP's default http_app transport) since Copilot Studio no longer accepts SSE for MCP connections (deprecated after August 2025).
- Design the retrieval tool as one coarse-grained call (query in, ranked results out) rather than several fine-grained endpoints, so Copilot Studio's 'one tool call per request' constraint and simpler LLM tool-selection both hold.
- When adding a future Teams channel, mirror the WhatsApp adapter pattern exactly (webhook in, InboundMessage out, OutboundMessage in, Teams payload out) and add zero new logic to handle_inbound or retrieve.

*As of: 2026-11-11; FastMCP docs reflect features added through v2.3.1 (fetched gofastmcp.com, undated version notes only); Microsoft Learn MCP page dated updated 2026-11-02 (ms.date 2026-10-30); fastapi_mcp GitHub README fetched live, no explicit version tag observed on the page*

**Sources**
- [FastAPI 🤝 FastMCP - FastMCP](https://gofastmcp.com/docs/integrations/fastapi) (official-docs) -- "New in version 2.0.0 ... New in version 2.3.1 ... mcp_app = mcp.http_app(path='/mcp'); app = FastAPI(lifespan=mcp_app.lifespan); app.mount('/analytics', mcp_app)"
- [Connect your agent to an existing Model Context Protocol (MCP) server - Microsoft Copilot Studio](https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent) (official-docs) -- "Currently, Copilot Studio supports the Streamable transport type ... Given that SSE transport is deprecated, Copilot Studio no longer supports SSE for MCP after August 2025."
- [GitHub - tadata-org/fastapi_mcp: Expose your FastAPI endpoints as Model Context Protocol (MCP) tools, with Auth!](https://github.com/tadata-org/fastapi_mcp) (repo) -- "FastAPI-MCP operates as a native extension of FastAPI ... secure your MCP endpoints using familiar FastAPI Depends() for authentication and authorization."

## Documentation sources

- [FastAPI (official docs homepage)](https://fastapi.tiangolo.com/)
- [FastAPI Release Notes](https://fastapi.tiangolo.com/release-notes/)
- [fastapi · PyPI](https://pypi.org/project/fastapi/)
- [FastAPI Tutorial - Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [FastAPI Advanced - Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [SQLAlchemy 2.0 Documentation (en/20 index)](https://docs.sqlalchemy.org/en/20/)
- [What's New in SQLAlchemy 2.0? — SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/changelog/whatsnew_20.html)
- [SQLAlchemy 2.0 - Major Migration Guide — SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html)
- [Changing Attribute Behavior — SQLAlchemy 2.0 Documentation (mapped_attributes)](https://docs.sqlalchemy.org/en/20/orm/mapped_attributes.html)
- [ORM Querying Guide: Using SELECT statements — SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html)
- [Download - SQLAlchemy](https://www.sqlalchemy.org/download.html)
- [SQLAlchemy ORM Mapping API](https://docs.sqlalchemy.org/en/20/orm/mapping_api.html)
- [Settings Management — Pydantic documentation](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/)
- [pydantic-settings docs/index.md (GitHub, main branch)](https://github.com/pydantic/pydantic-settings/blob/main/docs/index.md)
- [pydantic-settings · PyPI](https://pypi.org/project/pydantic-settings/)
- [pgvector/pgvector GitHub README](https://github.com/pgvector/pgvector)
- [pgvector CHANGELOG.md](https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md)
- [pgvector/pgvector Docker Hub page](https://hub.docker.com/r/pgvector/pgvector)
- [PostgreSQL: Documentation: current (18): F.35. pg_trgm — support for similarity of text using trigram matching](https://www.postgresql.org/docs/current/pgtrgm.html)
- [PostgreSQL: Documentation: 17: F.33. pg_trgm — support for similarity of text using trigram matching](https://www.postgresql.org/docs/17/pgtrgm.html)
- [PostgreSQL 16.15 release notes](https://www.postgresql.org/docs/release/16.15/)
- [PostgreSQL 18.0 Release Notes](https://www.postgresql.org/docs/current/release-18.html)
- [initdb](https://www.postgresql.org/docs/current/app-initdb.html)
- [postgres - Official Image | Docker Hub](https://hub.docker.com/_/postgres)
- [pg_isready](https://www.postgresql.org/docs/current/app-pg-isready.html)
- [Docker Compose overview](https://docs.docker.com/compose/)
- [Compose file reference](https://docs.docker.com/reference/compose-file/)
- [Compose file - services (healthcheck)](https://docs.docker.com/reference/compose-file/services/#healthcheck)
- [Install Docker Compose](https://docs.docker.com/compose/install/)
- [Compose file - Version and name top-level elements](https://docs.docker.com/reference/compose-file/version-and-name/)
- [History and development of Docker Compose](https://docs.docker.com/compose/intro/history/)
- [MinIO AIStor Python Client API Reference](https://docs.min.io/aistor/developers/sdk/python/api/)
- [Deploy Distributed MinIO AIStor on Docker Compose](https://docs.min.io/aistor/installation/container/distributed/)
- [MinIO AIStor HTTP Endpoints Reference](https://docs.min.io/aistor/reference/aistor-server/http-endpoints/)
- [Sentence Transformers (official site)](https://sbert.net/)
- [Usage docs — SentenceTransformer](https://sbert.net/docs/sentence_transformer/usage/usage.html)
- [SentenceTransformer class reference](https://sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html)
- [Pretrained Models docs](https://sbert.net/docs/sentence_transformer/pretrained_models.html)
- [Migration Guide](https://sbert.net/docs/migration_guide.html)
- [onnxruntime · PyPI](https://pypi.org/project/onnxruntime/)
- [Install ONNX Runtime | onnxruntime.ai](https://onnxruntime.ai/docs/get-started/with-python.html)
- [API - Python API documentation](https://onnxruntime.ai/docs/api/python/api_summary.html)
- [ONNX Runtime compatibility](https://onnxruntime.ai/docs/reference/compatibility.html)
- [Installation — Hugging Face Transformers docs](https://huggingface.co/docs/transformers/installation)
- [transformers · PyPI](https://pypi.org/project/transformers/)
- [Transformers — index page](https://huggingface.co/docs/transformers/en/index)
- [Pipelines — main classes](https://huggingface.co/docs/transformers/main_classes/pipelines)
- [Meta for Developers (homepage navigation to WhatsApp Business Platform docs)](https://developers.meta.com/)
- [Meta Developer News / Blog](https://developers.meta.com/blog/)
- [WhatsApp Direct Send API (Meta developer resource)](https://developers.meta.com/resources/videos/whatsapp-direct-send-api/)
- [Key Changes (2025-11-25 changelog) - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-11-25/changelog)
- [Introduction - Model Context Protocol](https://modelcontextprotocol.io/introduction)
- [Build an MCP server - Model Context Protocol](https://modelcontextprotocol.io/docs/2026-07-28/develop/build-server.md)
- [Specification (2025-06-18) - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18)
- [Key Changes (2025-06-18 changelog) - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/changelog)
- [Key Changes (2025-03-26 changelog) - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-03-26/changelog)
- [mcp · PyPI](https://pypi.org/project/mcp/)
- [Front Matter - Alembic's documentation! - SQLAlchemy](https://alembic.sqlalchemy.org/en/latest/front.html)
- [Changelog — Alembic 1.20.1 documentation](https://alembic.sqlalchemy.org/en/latest/changelog.html)
- [Operation Reference — Alembic 1.20.1 documentation](https://alembic.sqlalchemy.org/en/latest/ops.html)
- [PostgreSQL: Documentation: REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html)
- [Presigned URLs - Boto3 documentation (redirected to docs.aws.amazon.com)](https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html)
- [URL Safe Serialization — ItsDangerous Documentation (2.2.x)](https://itsdangerous.palletsprojects.com/en/stable/url_safe/)
- [Timed Signature Verification — ItsDangerous Documentation](https://itsdangerous.palletsprojects.com/en/stable/timed/)
- [Download and upload objects with presigned URLs - Amazon Simple Storage Service](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [Getting Started - obstore](https://developmentseed.org/obstore/latest/getting-started/)
- [Changing Attribute Behavior — SQLAlchemy 2.0 Documentation (synonyms section)](https://docs.sqlalchemy.org/en/20/orm/mapped_attributes.html#synonyms)
- [Alembic Operation Reference — alter_column](https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.alter_column)
- [Caddy reverse proxy quick start](https://caddyserver.com/docs/quick-starts/reverse-proxy)
- [FastAPI 🤝 FastMCP - FastMCP](https://gofastmcp.com/docs/integrations/fastapi)
- [Connect your agent to an existing Model Context Protocol (MCP) server - Microsoft Copilot Studio](https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent)

## Academic literature

- **Sentence-T5: Scalable Sentence Encoders from Pre-trained Text-to-Text Models** (2022), cited 645x -- [link](https://doi.org/10.18653/v1/2022.findings-acl.146) / [PDF](https://aclanthology.org/2022.findings-acl.146.pdf) _(via openalex)_
- **Toward Robust RALMs: Revealing the Impact of Imperfect Retrieval on Retrieval-Augmented Language Models** (2024), cited 10x -- [link](https://doi.org/10.1162/tacl_a_00724) / [PDF](https://doi.org/10.1162/tacl_a_00724) _(via openalex)_
- **Benchmarking Embedding Models for POJK Regulatory Retrieval in Indonesian Insurance Documents** (2026), cited 0x -- [link](https://doi.org/10.63158/journalisi.v8i5.1781) / [PDF](https://journal-isi.org/index.php/isi/article/download/1781/1055) _(via openalex)_
- **Electronic structure study of YNbTiO$_6$ vs. CaNb$_2$O$_6$ with U, Pu and minor actinide substitutions using compound-tunable embedding potential method** (2023) -- [link](https://arxiv.org/abs/2310.20595) / [PDF](https://arxiv.org/pdf/2310.20595v1) _(via arxiv)_
- **TwinBERT: Distilling Knowledge to Twin-Structured BERT Models for Efficient Retrieval** (2020) -- [link](https://arxiv.org/abs/2002.06275) / [PDF](https://arxiv.org/pdf/2002.06275v1) _(via arxiv)_

## Prior art

_No public repositories matched._

_No public repositories matched the prior-art queries._

## Open uncertainties

- Official documentation: FastAPI: `key_findings`
- Official documentation: FastAPI: `pitfalls`
- Official documentation: pydantic-settings: `key_findings`
- Official documentation: pydantic-settings: `pitfalls`
- Official documentation: pgvector: `recommendations`
- Official documentation: MinIO: `key_findings`
- Official documentation: MinIO: `api_surface`
- Official documentation: sentence-transformers: `as_of`
- Official documentation: ONNX Runtime: `current_version`
- Official documentation: ONNX Runtime: `as_of`
- Official documentation: Hugging Face Transformers: `key_findings`
- Official documentation: Hugging Face Transformers: `pitfalls`
- Official documentation: Meta WhatsApp Cloud API: `key_findings`
- Official documentation: Meta WhatsApp Cloud API: `api_surface`
- Official documentation: Meta WhatsApp Cloud API: `pitfalls`
- Before/after top-k retrieval parity methodology: `key_findings`
- pgvector HNSW re-embedding without schema change: `key_findings`
- ObjectStore abstraction over filesystem and MinIO: `key_findings`
- Reversible column rename via SQLAlchemy synonyms: `as_of`
- Docker Compose Postgres+pgvector deploy and backup: `key_findings`

## Not researched

- local-cpu-embedder-768: Required field "key_findings" is missing. Required field "recommendations" is missing. Required field "as_of" is missing. Required field "sources" is missing. The "uncertain" array is required (use [] when nothing is uncertain).

## Independent check

Researched by claude-code; checked by claude-code (claude-code (opus) reviewed work written by claude-code (sonnet): the same model family but a different capability class.). Verdict: **issues**.

I opened the primary sources behind the report's key version, API, date, and behavior claims and every one I checked is supported by its citation — including the surprising-looking Docker Compose v5 claim, which the cited history/releases pages do corroborate in this (2026) environment. Two planted AI-directed instructions ('remote-exec') were caught and redacted by OSA in the Transformers section, so no live injected instruction survives in the report; the redaction markers are the only trace. Remaining weak spots are honestly self-flagged [uncertain]: the Meta WhatsApp section (primary docs.facebook.com unreachable, several endpoint/webhook details are secondary-source only) and minor release-date discrepancies, none of which the build depends on structurally. OSA also removed 2 planted instruction(s) from the sources before the reviewer saw them.

Claims NOT confirmed (treat as uncertain downstream):
- [unverifiable] Meta WhatsApp Cloud API current Graph API version is v27.0 and /messages remains the send endpoint; webhook signature/handshake mechanics -- Report honestly flags developers.facebook.com as unreachable and marks endpoint/webhook/signature details [uncertain, secondary-source only]; I did not independently open these. Build should re-verify before implementation, as the report itself recommends (https://developers.meta.com/blog/)

### Planted instructions found in sources (removed before use)

2 line(s) of source text were aimed at an AI rather than at a reader. They were cut out before any model used the material, and nothing in this report relies on them.

- remote-exec in research result (model output derived from web pages) (research:docs-hugging-face-transformers)
- remote-exec in research result (model output derived from web pages) (research:docs-hugging-face-transformers)
