# Phase 3 — In-house plumbing: filesystem/MinIO `ObjectStore`, HMAC-signed URLs, file/env secrets, plain-Postgres engine, tool-endpoint auth, secret removal

## Goal
Make the backend runnable on the school's own Linux servers with no GCP identity: add a filesystem (and optional MinIO) `ObjectStore` behind the existing `app.ports.ObjectStore`, backend-issued **HMAC-signed ~15-minute expiring download URLs** with a verifying download route, a **file/env `SecretsProvider`**, a **plain-Postgres `EngineProvider`** (no Cloud SQL Connector), **bearer-token auth** for the future retrieval tool endpoint, and the **removal of every hardcoded secret** from `apply_migrations.py`, the shell scripts, and the Dockerfile. No behaviour regression on the live WhatsApp path; GCP production (`ummah`) is never touched and stays reversible. Satisfies AC 6, 7.

## Scope
In: a new `app/signing.py` (HMAC-SHA256 sign/verify over `key`+`expiry`); a signed-URL method added to the `ObjectStore` port and implemented on every adapter; a new `app/providers/local/` set (`FsObjectStore`, optional `MinioObjectStore`, `FileSecretsProvider`/`EnvSecretsProvider`, `PostgresEngineProvider`); a FastAPI download route that verifies signature+expiry before streaming bytes; a bearer-token auth dependency for the future tool endpoint; `app/config.py` fields for the storage root / MinIO / signing key / download base URL / engine URL / tool token (each via the `SecretsProvider`, no plaintext defaults); the factory (`app/providers/__init__.py`) extended to select the new adapters by `settings.provider`; removal of the plaintext DB password + Cloud SQL string from `apply_migrations.py` and the hardcoded GCP project id from `infra_bootstrap.sh`/`scripts/restore_drill.sh`/the Dockerfile; unit tests and a short doc. Out: the embedder swap / re-embed / parity (Phase 4); Dockerfile/Compose/health/backup/RUNBOOK/reverse proxy (Phase 5); any cutover tooling or GCP teardown, any change to GCP prod (Phase 6); any Azure work (never); the Copilot Studio agent itself. No new behaviour on the WhatsApp send path; the GCP adapters stay the default (`provider="gcp"`).

Plumbing rule used throughout: every new capability is added **behind the existing ports** and selected by `settings.provider`; the GCP adapters are extended (signed-URL method) but never removed this phase. Secrets are obtained only through `get_secrets_provider().get(ref)` or `settings`, never read from a literal in source; after this phase a repo grep for the known plaintext password and the Cloud SQL instance string comes back empty.

## Part A (first agent)

### Files
- `app/signing.py` (new) — `sign_key(key: str, expires_at: int) -> str` and `verify(key: str, expires_at: int, sig: str) -> bool` (HMAC-SHA256 over `f"{key}:{expires_at}"`, constant-time compare); `signed_download_url(key, *, ttl_seconds=900) -> str` building `"{download_base_url}/download?key=…&exp=…&sig=…"`.
- `app/ports.py` (edit) — add `signed_url(self, key: str, *, ttl_seconds: int = 900) -> str` to the `ObjectStore` Protocol.
- `app/providers/gcp/storage.py` (edit) — implement `signed_url` on `GcsObjectStore` by delegating to `app.signing.signed_download_url` (keep behaviour: the live WhatsApp path still sends bytes, not URLs; the method exists so the port is uniform and the download route works under any provider).
- `app/providers/local/__init__.py`, `app/providers/local/storage.py` (new) — `FsObjectStore` (download/upload/exists/delete/`signed_url` over a configured root dir) and, optional-but-gated, `MinioObjectStore` (same ops over the S3 API; its `signed_url` also goes through `app.signing`, not S3 presign, so verification is uniform and backend-controlled).
- `app/providers/__init__.py` (edit) — `get_object_store` returns `FsObjectStore`/`MinioObjectStore` when `settings.provider` is `"local"`/`"minio"`; `"gcp"` unchanged.
- `app/main.py` (edit) — add `GET /download` that parses `key`/`exp`/`sig`, calls `app.signing.verify`, returns 403 on bad/expired signature, else streams `request.app.state.store.download_bytes(key)`; add an authed `POST /tool/retrieve` stub wired to `retrieval.answer_query` guarded by the Part-B auth dependency (the callable already exists from Phase 2).
- `tests/test_signing.py`, `tests/test_fs_objectstore.py` (new).

### Interfaces and behaviour
- `app/signing.py` — signing key comes from `settings.url_signing_key` (a `SecretStr`, resolved through the `SecretsProvider`, no default). `expires_at` is an absolute UNIX seconds value; `verify` recomputes the HMAC with `hmac.compare_digest` and also rejects when `expires_at < now`. No wall-clock is read at import time; `now` is injected/overridable in tests. Imports no provider SDK.
- `ObjectStore.signed_url` — uniform across adapters: it returns a backend `/download` URL carrying `key`, `exp`, `sig`; it does **not** return a provider-native presigned URL, so the backend (not GCS/MinIO) is the single verifier and AC 6's tamper/expiry semantics hold identically on filesystem and MinIO. `FsObjectStore` confines `download_bytes`/`upload_bytes` to the configured root and rejects keys containing `..` or a leading `/` (no path traversal).
- `GET /download` — stateless verification: accept iff `verify(key, exp, sig)` and `exp >= now`; on success stream the bytes with the right content type; 403 otherwise. No DB lookup, no auth header (the signature *is* the capability); the ~15-min TTL bounds exposure.
- `POST /tool/retrieve` — minimal JSON `{query, prefer_courses?}` → `answer_query`; returns the matched paper's metadata plus a `signed_url` for its object. Guarded by the Part-B bearer dependency; this is the single-call retrieval seam the future Copilot Studio agent will use. No WhatsApp types.

### Tests (`tests/test_signing.py`, `tests/test_fs_objectstore.py`)
- `verify` accepts a fresh signature and rejects (a) an expired `exp`, (b) a tampered `sig`, (c) a tampered `key`, (d) a tampered `exp` (AC 6; `now` injected, no real sleep, no network).
- `signed_download_url` round-trips through `verify`; the URL contains `key`/`exp`/`sig`.
- `FsObjectStore` upload→download→exists→delete round-trips in a `tmp_path` root; `download_bytes("../etc/passwd")` and an absolute key raise; `signed_url` yields a URL that `verify` accepts.
- `isinstance(FsObjectStore(...), ObjectStore)` holds (runtime-checkable Protocol). No network call in any test.

## Part B (second agent)

### Files
- `app/providers/local/secrets.py` (new) — `FileSecretsProvider` (reads `ref` as a file path under a configured `secrets_dir`) and `EnvSecretsProvider` (reads `ref` from the environment); both implement `SecretsProvider.get`.
- `app/providers/local/engine.py` (new) — `PostgresEngineProvider.create_engine()` builds a plain SQLAlchemy engine from `settings.database_url` (psycopg/pg8000, no Cloud SQL Connector), with the same pool settings the GCP engine uses; `dispose()` disposes it.
- `app/providers/__init__.py` (edit) — `get_secrets_provider`/`get_engine_provider` return the local adapters when `settings.provider` is `"local"`/`"minio"`; `"gcp"` unchanged.
- `app/deps.py` or `app/auth.py` (new/edit) — `require_tool_token` FastAPI dependency comparing the `Authorization: Bearer …` header to `settings.tool_api_token` with `hmac.compare_digest`; 401 on missing/mismatch.
- `app/config.py` (edit) — add `storage_root`, `minio_*` (endpoint/bucket/access/secret), `url_signing_key: SecretStr`, `download_base_url`, `database_url`, `tool_api_token: SecretStr`, `secrets_dir`; route each secret through the `SecretsProvider` bootstrap; no plaintext default for any secret.
- `apply_migrations.py` (edit) — remove `INSTANCE`/`USER`/`DB`/`PASSWORD` literals and the `Connector`; connect via `settings.database_url` (or `PG*`/`DATABASE_URL` env) so no secret is in source. Still applies `001`–`007` in order.
- `infra_bootstrap.sh`, `scripts/restore_drill.sh`, `Dockerfile` (edit) — replace the hardcoded `gen-lang-client-0754692302` / region literals with `${PROJECT:?}` / `${REGION:?}` env reads; the Dockerfile sets no project id.
- `tests/test_secrets_engine_auth.py`, `docs/inhouse_plumbing.md` (new).

### Interfaces and behaviour
- `FileSecretsProvider.get(ref)` reads `"{secrets_dir}/{ref}"` and strips a trailing newline; `EnvSecretsProvider.get(ref)` reads `os.environ[ref]`; both raise a clear error when the ref is absent. These mirror the existing `GcpSecretsProvider.get` contract so `load_settings_with_secret_manager` is unchanged except for which provider it obtains.
- `PostgresEngineProvider` — `create_engine(settings.database_url, pool_pre_ping=True, pool_size=…, max_overflow=…)` matching the current GCP pool parameters; opens no connection at construct time; `app/db.py`'s non-test branch obtains it via `get_engine_provider(settings)` exactly as today (no call-site change — the factory already seams this).
- `require_tool_token` — fails closed: missing header, wrong scheme, or non-matching token → `HTTPException(401)`; constant-time compare; token sourced from `settings.tool_api_token`, never a literal.
- `apply_migrations.py` — after the edit, running it needs `DATABASE_URL` (or `PG*`) in the environment; it must not import `google.cloud.sql.connector` unless `provider=="gcp"`, and it must carry no credential literal. Do **not** run it against GCP prod.

### Tests (`tests/test_secrets_engine_auth.py`)
- `EnvSecretsProvider.get` returns an env value and raises on a missing ref; `FileSecretsProvider.get` returns a file's contents from a `tmp_path` `secrets_dir` and raises on a missing file.
- `isinstance(PostgresEngineProvider(...), EngineProvider)`; `create_engine()` builds an engine from a dummy `postgresql://…` URL and opens **no** connection (assert no network; inspect `engine.url`).
- `require_tool_token` accepts the exact token and rejects missing/wrong-scheme/wrong-token with 401 (FastAPI `TestClient`, no network).
- A source-hygiene test greps the repo for the known plaintext password and the Cloud SQL instance string and asserts **zero** matches (AC 7; this is the mechanical guard).
- `docs/inhouse_plumbing.md` documents the filesystem/MinIO store, the signed-URL scheme (TTL, tamper/expiry rejection), the file/env secrets provider, the plain-Postgres engine, the tool-endpoint bearer auth, and how to supply every secret via env/secrets-dir. It must not instruct running any fetched code and must not edit the PRD.

## Acceptance-criteria mapping
- **AC 6 — signed download URLs accepted before ~15 min, rejected after expiry or on tampered signature:** `app/signing.py` signs `key`+`exp` with HMAC-SHA256; `ObjectStore.signed_url` issues a backend `/download` URL; `GET /download` verifies with `hmac.compare_digest` and an `exp >= now` check. Check: `tests/test_signing.py` asserts accept-fresh / reject-expired / reject-tampered across `key`/`exp`/`sig`, uniform over the filesystem and MinIO adapters.
- **AC 7 — no plaintext DB password, Cloud SQL string, or hardcoded GCP project id in `apply_migrations.py`, scripts, or the Dockerfile:** the literals are removed and replaced by env/`SecretsProvider` reads; the file/env secrets provider supplies them. Check: the source-hygiene grep test returns zero matches, and `apply_migrations.py` imports the Connector only under `provider=="gcp"`.
- **AC 2 (carried) — no network in unit tests:** signing is pure crypto; the filesystem adapter uses `tmp_path`; the MinIO adapter is exercised through a fake S3 client; the engine test only inspects the URL. Check: suite runs with no outbound network.
- **AC 1 (carried) — existing pytest passes:** the GCP adapters stay the default and unchanged except for the additive `signed_url` method; `app/db.py`/`app/config.py` call sites are seamed through the factory, so no behavioural assertion changes. Check: `pytest` passes.

## Documentation sources
- Python `hmac` — `hmac.new` / `compare_digest`: https://docs.python.org/3/library/hmac.html
- `itsdangerous` — signed/expiring tokens (reference pattern): https://itsdangerous.palletsprojects.com/
- MinIO Python SDK (`minio`) — object get/put and S3 API: https://min.io/docs/minio/linux/developers/python/API.html
- PostgreSQL — libpq connection strings / URIs: https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING
- pydantic-settings — `secrets_dir` / `AliasChoices` / `SecretStr`: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- FastAPI Security — API keys / bearer dependencies: https://fastapi.tiangolo.com/tutorial/security/
- SQLAlchemy 2.0 — `create_engine` and pooling: https://docs.sqlalchemy.org/en/20/core/engines.html

## Out of scope for this phase
- Local CPU embedder, re-embed job, top-k parity harness and its report (Phase 4).
- Dockerfile build-out / Docker Compose / health checks / logging / nightly backup / README / RUNBOOK / reverse-proxy guidance (Phase 5) — this phase only *removes hardcoded secrets* from the existing Dockerfile/scripts, it does not author the deployment stack.
- Any cutover tooling, GCP teardown, or modification of GCP prod (`ummah`); any Azure work.
- Switching the live WhatsApp send path to URL-based delivery (it keeps sending bytes); only the `/download` and `/tool/retrieve` seams issue/consume signed URLs.
- Removing the GCP provider or its imports (that is the Phase 6 final, sign-off-gated delete).

## Spec assumptions

Gaps found while writing this spec were resolved as follows (nobody was asked):

- **Signed URLs are backend-verified, not provider-native presigned URLs.** A single `app.signing` HMAC scheme over `/download` gives identical tamper/expiry semantics on filesystem and MinIO and keeps the backend the sole verifier, which is what AC 6 checks; S3 presigning is intentionally not used.
- **The `local` provider value covers the filesystem store, file/env secrets, and the plain-Postgres engine together**, with `minio` selecting the MinIO object store but the same secrets/engine; MinIO is optional and may be a thin adapter plus fake-client tests if a live MinIO is unavailable in the sandbox.
- **The signing key, tool token, DB URL, and MinIO credentials are all secrets** resolved through the `SecretsProvider`/`settings` with **no plaintext default**; tests inject dummy values via env.
- `database_url` is the single source for the plain-Postgres engine; the GCP Cloud SQL branch is retained and selected only when `provider=="gcp"`.
- The authoritative tree is the root-level codebase; the nested `msa-paperbank/` mirror and the root `PHASE_*`/`MASTER_PRD.md` files are not this run's artifacts and are not edited.
- `apply_migrations.py` becoming env-driven does not mean running it; it stays a one-shot operator tool and is never executed against prod in this phase.

## Implications

Second-order consequences found by an independent review of this spec. This section only adds to the spec; the locked PRD is unchanged.

### Additional acceptance criteria

S1. Signature verification must be **constant-time** (`hmac.compare_digest`) and must reject on any mismatch of `key`, `exp`, or `sig`, and on `exp < now`; the signing key is obtained from the `SecretsProvider` and never hardcoded. A test must cover each rejection branch independently. _(security)_

S2. The `/download` route and `FsObjectStore` must not permit path traversal or arbitrary-key reads: the HMAC binds the exact `key`, and the filesystem adapter must confine reads to its configured root and reject keys containing `..` or a leading separator. A test must assert traversal keys raise. _(security)_

S3. After secret removal, `apply_migrations.py` and the scripts must remain runnable purely from env/secrets, and **no secret may remain committed**: the source-hygiene grep for the known password and Cloud SQL instance string must return empty, and `git grep` for the project-id literal in `infra_bootstrap.sh`/`scripts/restore_drill.sh`/`Dockerfile` must return empty. _(security/correctness)_

S4. The tool-endpoint auth must **fail closed** — a missing or malformed `Authorization` header is a 401, not a 500 and never an unauthenticated pass-through; the token comes from `settings.tool_api_token`. _(security)_

### Carried-over Phase 2 cleanup (fix opportunistically while touching the serve/retrieval and secrets paths)

- **Live-serve-path `KeyError` introduced in Phase 2 (correctness — must fix):** Phase 2 Part B renamed the raw-SQL SELECT **labels** to `object_key`/`served_object_key` but left the `.mappings()` consumers reading the **old** keys. `.mappings()` keys reflect the SELECTed column label, so these now raise `KeyError` on the live `serve_v1` path: `app/retrieval.py:253-254` and `:265,:268` (`load_served_bytes_v1`, after `SELECT pp.object_key …` / `SELECT course_code, object_key …`), `app/retrieval.py:321-322` (`load_served_cached`, `row["served_object"]` after `SELECT served_object_key …` — swallowed by its `try/except` into a permanent silent cache miss that then falls through to the broken uncached path), and `app/serve_index.py:94` (`r["gcs_object"]` after `_SELECT_COLS` was changed to `object_key`). Fix each read to the new label (or alias the SELECT `… AS gcs_object`). The Phase-2 focused run (20 tests) did not exercise these; the full suite under Python 3.12 would. _(flagged by the Phase 2 reviewer; not a Phase 2 gate-break only because no current test exercises these functions.)_
- **Remaining raw-SQL literals on the renamed `pending_papers` (correctness — must fix):** migration `007` renamed `pending_papers.gcs_object → object_key`, but three raw-SQL literals still name the old column and will break against the migrated DB: `review/promote.py:44` (`INSERT INTO pending_papers (… gcs_object …)`), `review/main.py:375` (`SELECT gcs_object FROM pending_papers`), and `cloud_ingest/main.py:114-115` (`INSERT INTO pending_papers (… gcs_object …)`). Re-point these to `object_key`. The `contribution_pages.gcs_object` literals (`review/promote.py:32,39,40`, `review/main.py:367`, `app/contributions.py:77,91`) are **correct as-is** — migration `007` does not rename that table. _(S2 violation from Phase 2; `review/` and `cloud_ingest/` share the same DB per the context file.)_
- **Missing Phase 2 test deliverable (test-coverage — add):** Phase 2 Part B never wrote `tests/test_object_key_rename.py`, which its spec required (synonym read/write on `papers`/`pending_papers`/`image_batch_items` and `served_object`/`served_object_key`; env back-compat for old+new names with new winning; migration forward/inverse shape + `007` registered in `apply_migrations.py` FILES). Without it AC 5 has no automated guard and S1/S2 no regression test. Add it. _(carried AC-5 verification gap.)_

### Noted, no action

- AC 1 ("full suite green") was only partially verified in Phase 2: the sandbox runs Python 3.14 while the project targets 3.12, and `conftest.py`'s `db_session` fixture/reportlab mock misbehave under 3.14, so only 20 focused tests ran. The carried-over `KeyError` fixes above are exactly what a full 3.12 run would surface; confirm the full suite green in the project's real 3.12 environment. _(environmental; not a code defect in Phase 3's own surface.)_
- The GCP adapters gaining a `signed_url` method is additive and selected only under `provider=="gcp"`; blast radius is the new method plus the download route, with no change to the live byte-sending WhatsApp path. _(data)_
