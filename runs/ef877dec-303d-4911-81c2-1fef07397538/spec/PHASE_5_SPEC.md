# Phase 5 — Deployment: Dockerfile + Docker Compose (bot, Postgres pgvector/pg_trgm, optional MinIO), health checks, logging, nightly backup + restore drill, README + RUNBOOK, HTTPS reverse-proxy guidance

## Goal
Make the migrated bot **self-startable in one command on a no-GPU school Linux server** with no GCP credentials present. Ship a reproducible container image that **bakes the local CPU embedding model into the image** (offline boot, no network fetch at container start), a `docker compose up` stack of **bot + Postgres (pgvector + pg_trgm) + optional MinIO** where **every service reports healthy via its own health check**, structured logging, a **nightly `pg_dump` backup job** writing to a mounted volume, a **tested restore-from-backup drill**, and a **README + RUNBOOK** for school IT covering startup, backup, restore drill, and **public HTTPS reverse-proxy** setup (Caddy/nginx). The container must boot healthy under `provider="local"` without reaching GCP: the one residual GCP boot path (the `lifespan` `storage.Client(...)` construction and the Vertex-only `_warmup`) must be **provider-gated** so a credential-free local run starts and serves. No behaviour regression on the WhatsApp or `/tool/retrieve` path; the `Vector(768)` + HNSW + `pg_trgm` schema is unchanged; GCP production (`ummah`) is never touched. Satisfies AC 10, 11.

## Scope
In: a production-oriented `Dockerfile` (multi-stage, Python 3.12-slim, pre-downloading the `sentence-transformers` model into the image's HF cache so first encode is offline) with a healthy non-GCP boot; a `docker-compose.yml` defining `db` (official `pgvector/pgvector` image, `CREATE EXTENSION vector` + `pg_trgm` on init, `pg_isready` health check, `shm_size` for HNSW builds, named volume), `app` (the bot image, `/healthz` health check, `depends_on: db healthy`, migrations applied at start via the existing `apply_migrations.py`), and an **optional** `minio` service gated behind a Compose **profile**; a `.env.example` for Compose (provider, `DATABASE_URL`, object-store root/MinIO, tokens — placeholders only, never real secrets); provider-gating the residual GCP boot path in `app/main.py` (`storage.Client` only under `provider=="gcp"`; `_warmup` embeds through `app.state.embedder`, not the Vertex-only `app.embeddings.embed_query`); a nightly backup job (`scripts/backup.sh` + a Compose `backup` companion service or documented host cron) writing timestamped `pg_dump` archives to a mounted volume, with a `scripts/restore.sh` restore path; expansion of the existing `README.md` and `RUNBOOK.md` to cover startup, nightly backup, the restore drill, and HTTPS reverse-proxy (Caddy and nginx) guidance; smoke/validation tests (Compose file parses and wires the services/health checks; backup/restore scripts are well-formed and prod-safe; the bot image boots under `provider=local` without GCP). Out: any cutover tooling, data migration, GCP teardown, webhook move, or modification of GCP prod (Phase 6); removing the GCP embedder/adapters or the `google.cloud`/`google-genai` imports (Phase 6 final, sign-off-gated); any Azure work (never); topic-level search / question-index work (separate later run). The schema (`Vector(768)`, HNSW, `pg_trgm`) is unchanged; the GCP adapters remain selectable under `provider="gcp"`.

Deployment rule used throughout: the stack is **provider-neutral and offline-capable** — `docker compose up` must bring the bot to `healthy` under `provider="local"` on a host with **no GCP credentials and no outbound internet at container start**. The embedding model is **baked into the image** (not fetched at boot) and loaded lazily at `lifespan`/first use. Secrets are read from the environment / a git-ignored `.env`, never committed; `.env.example` carries placeholders only. The backup job and restore drill are **operator tools** — scripted, tested for well-formedness, and documented, but never pointed at GCP prod.

## Part A (first agent)

### Files
- `Dockerfile` (edit) — multi-stage. A builder stage installs `requirements.txt` and, with the venv/wheels present, **pre-downloads the model** (`python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-mpnet-base-v2')"`) into a cache directory; the final `python:3.12-slim` stage copies the installed packages, the `app`/`admin`/`migrations` trees, and the populated model cache (set `HF_HOME`/`SENTENCE_TRANSFORMERS_HOME` and `HF_HUB_OFFLINE=1` so no fetch happens at run time). Keep the existing gunicorn/uvicorn entrypoint and `EXPOSE 8080`. The image must run as a non-root user and contain **no secret** and no GCP credential.
- `app/main.py` (edit) — provider-gate the residual GCP boot path so a local run boots healthy without GCP creds: construct `app.state.gcs = storage.Client(...)` **only when `settings.provider == "gcp"`** (otherwise leave it unset/`None`), and change `_warmup` to force the cold path through the **active** embedder (`app.state.embedder.embed_query("warmup")` / the title index) instead of importing `app.embeddings.embed_query` directly. Warmup stays non-fatal and daemon-threaded; `/healthz` stays immediate. No behaviour change under `provider=="gcp"`.
- `docker-compose.yml` (new) — services: `db` (`pgvector/pgvector:pg16` or pinned equivalent, env `POSTGRES_*` from `.env`, an init SQL that runs `CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;`, `healthcheck` using `pg_isready -h 127.0.0.1`, `shm_size: 1g`, named volume `pgdata`); `app` (`build: .`, env from `.env` with `provider=local`, `depends_on: {db: {condition: service_healthy}}`, applies migrations `001`–`007` via `apply_migrations.py` at start, `healthcheck` hitting `/healthz`, port map `8080`); `minio` (**optional**, behind `profiles: ["minio"]`, console+API ports, health check, named volume). No service embeds a secret literal.
- `.env.example` (new) — Compose/runtime variables with **placeholder** values only: `PROVIDER=local`, `DATABASE_URL=postgresql+pg8000://…`, `POSTGRES_*`, object-store root (`OBJECT_STORE_DIR`) and/or MinIO endpoint/keys, `TOOL_API_TOKEN`, `SIGNING_SECRET`, WhatsApp verify/token placeholders. A comment states that the real `.env` is git-ignored and never committed.
- `tests/test_deploy_compose.py` (new).

### Interfaces and behaviour
- **Healthy local boot (no GCP):** with `provider="local"` and no GCP credentials, importing/booting the app constructs no `storage.Client` and makes no Vertex call; `/healthz` returns `{"ok": True}` immediately; the embedder is the lazily-loaded `LocalCpuEmbedder`. Under `provider="gcp"` the previous boot (GCS client + Vertex warmup) is unchanged.
- **Offline model:** the baked model cache + `HF_HUB_OFFLINE=1` means first `embed_query`/`embed_documents` loads from local disk with no network; nothing in the image pulls weights at container start.
- **Compose wiring:** `db` becomes healthy (pgvector + pg_trgm extensions created) before `app` starts; `app` applies migrations `001`–`007` (no schema change — the `Vector(768)`/HNSW/`pg_trgm` definitions are exactly as migrations leave them) and becomes healthy on `/healthz`; `minio` is present only when the `minio` profile is enabled.
- **No secrets:** the image, `docker-compose.yml`, and `.env.example` contain no plaintext DB password, Cloud SQL string, GCP project id, or API token — only placeholders and env references (the Phase 3 source-hygiene test continues to hold).

### Tests (`tests/test_deploy_compose.py`)
- The app boots under `provider="local"` with **no** GCP credentials available: patch/spy `google.cloud.storage.Client` and assert it is **not** constructed during `lifespan`, and that `/healthz` returns 200 via `TestClient` (network-free; the local embedder stays an injected/lazy fake so no model loads).
- `_warmup` under `provider="local"` routes through `app.state.embedder` and never imports/calls `app.embeddings.embed_query` (patch the Vertex path and assert it is untouched).
- `docker-compose.yml` parses as valid YAML and declares the three services with: `db` using a pgvector image and a `pg_isready` health check, `app` depending on `db` service-healthy and exposing a `/healthz` health check, and `minio` gated behind a `profiles` entry (string assertions over the parsed structure — no Docker daemon needed).
- `.env.example` exists, is non-empty, and contains **no** forbidden literal (reuse the Phase 3 forbidden-literal set: GCP project id, Cloud SQL instance string, `DB_PASSWORD=secret`).

## Part B (second agent)

### Files
- `scripts/backup.sh` (new) — a nightly `pg_dump` backup: reads connection parameters from the environment (never hardcoded), writes a **timestamped** compressed archive to a mounted backup directory (`/backups` volume), prunes archives older than a retention window, and exits non-zero on failure so a scheduler can alert. It must refuse to run against a GCP/Cloud SQL host (guard on the host/`provider`), and must not download or execute fetched code.
- `scripts/restore.sh` (new) — the restore-drill companion: restores a chosen archive into a **named, non-prod** database/volume and runs a minimal verification query (row counts on `papers`/`paper_chunks`), so the RUNBOOK drill is executable. It must never target prod.
- `docker-compose.yml` (edit) — add the nightly backup as a companion `backup` service (or document an equivalent host `cron`) that mounts the `pgdata`-adjacent `backups` volume and runs `scripts/backup.sh` on a schedule; no secret literals.
- `README.md` (edit) — expand to cover: what the stack is, prerequisites, `cp .env.example .env` and fill-in, `docker compose up` (and `--profile minio`), where data/backups live, and how to reach the bot. Must not instruct running any fetched code and must not edit the PRD.
- `RUNBOOK.md` (edit) — operator procedures: start/stop/upgrade, applying migrations, the **nightly backup** (what runs, where archives land, retention), the **restore-from-backup drill** (step-by-step using `scripts/restore.sh` against a non-prod target, with the verification step), log locations/levels, and **public HTTPS reverse-proxy** setup for **both Caddy and nginx** (TLS termination in front of the FastAPI backend on `:8080`, the single public route the future Teams/Copilot agent calls, and the `/webhook` path WhatsApp uses). State explicitly that none of this is ever run against GCP prod.
- `tests/test_backup_restore.py` (new).
- **Carried-over Phase 4 test-coverage cleanup** (fix opportunistically while adding deployment tests): `tests/test_reembed.py` (edit) and `tests/test_parity.py` (edit) — see Implications.

### Interfaces and behaviour
- `scripts/backup.sh` / `scripts/restore.sh` — POSIX-sh, parameterised entirely by environment, idempotent in the sense that re-running backup produces a new timestamped archive and never mutates the source DB; restore targets only an explicitly-named non-prod database. Both fail closed (non-zero) on missing parameters and both carry a prod-safety guard.
- Backups land on a **mounted volume**, not inside the image, and contain no committed secret. Retention pruning is bounded and logged.
- The RUNBOOK restore drill is a real, followable procedure that ends in a verification query, satisfying AC 11's "restore-from-backup drill".
- Reverse-proxy guidance gives working Caddy and nginx fragments terminating TLS and proxying to the bot, with the public HTTPS surface limited to the health/tool/webhook routes.

### Tests (`tests/test_backup_restore.py`)
- `scripts/backup.sh` and `scripts/restore.sh` exist, are syntactically valid shell (`sh -n`), contain the prod-safety guard, read credentials from the environment (no hardcoded secret — assert the forbidden-literal set is absent), and reference the mounted backup path.
- `README.md` and `RUNBOOK.md` exist and mention the required topics (startup, nightly backup, restore drill, HTTPS reverse proxy / Caddy + nginx) — presence assertions over the file text.
- No test invokes Docker, `pg_dump`, or any network; all are static/structural checks (AC 2).

### Tests (carried-over Phase 4 cleanup)
- `tests/test_reembed.py` (add) — `reembed_all` against an **in-memory sqlite session seeded** with `paper_chunks`/`pending_paper_chunks` rows and a fake embedder updates **every** row's `embedding` to the fake's vectors, leaves `text`/`id`/other columns untouched, and is **idempotent** on a second run (identical input → identical vectors); the default path issues **no DDL** (AC 9 / E2/E3). No network.
- `tests/test_parity.py` (add) — `run_parity` over a tiny seeded corpus with two fake embedders yields per-query `jaccard`/`rank_correlation` and set means in range `[0,1]`/`[-1,1]`; add the partial-overlap and reversed-order assertions for `rank_correlation` if not already covered. No network, no GCP.

## Acceptance-criteria mapping
- **AC 10 — `docker compose up` starts bot + Postgres (pgvector, pg_trgm) + optional MinIO, each healthy:** `docker-compose.yml` wires `db` (pgvector image, extensions created on init, `pg_isready` health check) → `app` (migrations applied, `/healthz` health check) with `minio` behind a profile; the image boots healthy under `provider="local"` without GCP creds. Check: `tests/test_deploy_compose.py` asserts the parsed service/health/profile wiring and a credential-free `TestClient` boot with no `storage.Client` constructed.
- **AC 11 — README and RUNBOOK cover startup, nightly backup, restore drill, HTTPS reverse proxy:** `README.md`/`RUNBOOK.md` are expanded; `scripts/backup.sh`/`scripts/restore.sh` make the backup + restore drill executable. Check: `tests/test_backup_restore.py` asserts the scripts' validity/guards and the docs' topic coverage.
- **AC 7 (carried) — no secrets in sources:** the Dockerfile, Compose file, `.env.example`, and backup scripts carry placeholders/env references only; the Phase 3 forbidden-literal hygiene test continues to pass. Check: forbidden-literal assertions in the new tests + the existing `tests/test_secrets_engine_auth.py`.
- **AC 8 (carried) — schema unchanged:** the Compose `db` init creates the `vector`/`pg_trgm` extensions and `apply_migrations.py` applies `001`–`007` unchanged; no new migration alters `Vector(768)`/HNSW/`pg_trgm`. Check: no schema DDL in this phase's diff; reembed default path issues no DDL (carried test).
- **AC 2 (carried) — no network in unit tests:** every new test is static/structural or uses `TestClient` with patched clients and injected fakes; the model is never loaded and no container is launched. Check: suite runs with no outbound network.
- **AC 1 (carried) — existing pytest passes:** provider-gating the GCP boot path is behaviour-preserving under `provider=="gcp"`; no call-site or schema change on the live path. Check: `pytest` passes in the project's Python 3.12 environment.

## Documentation sources
- Docker Compose — service definitions, `depends_on` conditions, `healthcheck`, `profiles`: https://docs.docker.com/compose/
- `pgvector/pgvector` image + `CREATE EXTENSION vector`, HNSW build memory (`shm_size`): https://github.com/pgvector/pgvector
- PostgreSQL — `pg_isready`, `pg_dump`/`pg_restore`, `pg_trgm`: https://www.postgresql.org/docs/
- MinIO — container deployment and health endpoints: https://min.io/docs/minio/container/index.html
- Hugging Face Transformers / sentence-transformers — offline model caching (`HF_HOME`, `HF_HUB_OFFLINE`, `SENTENCE_TRANSFORMERS_HOME`): https://huggingface.co/docs/transformers/installation#offline-mode
- Caddy (automatic HTTPS) and nginx (TLS termination / reverse proxy): https://caddyserver.com/docs/ , https://nginx.org/en/docs/http/configuring_https_servers.html

## Out of scope for this phase
- Any cutover tooling, Cloud SQL dump, bucket copy, webhook move, side-by-side run, GCP teardown, or modification of GCP prod (`ummah`) — Phase 6; nothing here is executed against prod.
- Removing the GCP embedder/adapters or the `google.cloud` / `google-genai` / `vertexai` / `cloud-sql-connector` imports — Phase 6 final, sign-off-gated delete. This phase only **gates** the residual GCS/Vertex boot path behind `provider=="gcp"`; it does not delete it.
- Any Azure work (never); local LLMs/GPUs; the daily model cost-cap breaker; study companion; Teams push notifications; the Copilot Studio agent itself.
- Topic-level search and question-index work (separate later run).

## Spec assumptions

Gaps found while writing this spec were resolved as follows (nobody was asked):

- **The embedding model is baked into the image** (builder stage pre-downloads it, final stage copies the cache, `HF_HUB_OFFLINE=1`) rather than mounted or fetched at boot, because the school server may have no outbound internet and AC 10 requires a healthy start. A volume-mounted pre-download is a documented alternative in the RUNBOOK.
- **The container must boot under `provider="local"` without GCP credentials**, so the `lifespan` `storage.Client(...)` and the Vertex-only `_warmup` are provider-gated this phase. This is the "not-yet-rerouted paths" the Phase 1 comment flagged; it is a boot-correctness fix for AC 10, not the Phase 6 teardown. Under `provider=="gcp"` boot is unchanged.
- **Migrations are the existing numbered SQL files** (`001`–`007`) applied by `apply_migrations.py`; the Compose `app` service runs them at start. There is no Alembic. No new migration is added this phase (schema unchanged).
- **The optional MinIO service is Compose-profile-gated** (`--profile minio`), defaulting off, matching "optional MinIO" and the filesystem-default object store from Phase 3.
- **The nightly backup is a `pg_dump` companion (or host cron) writing to a mounted `backups` volume** with bounded retention; the restore drill restores into a named non-prod database and verifies with row counts. Neither ever targets prod.
- **Existing `Dockerfile`/`README.md`/`RUNBOOK.md` are expanded, not replaced**; the authoritative tree is the root-level codebase (the nested `msa-paperbank/` mirror is not edited).

## Implications

Second-order consequences found by an independent review of this spec. This section only adds to the spec; the locked PRD is unchanged.

### Additional acceptance criteria

E1. The bot must reach **healthy without any GCP credential**: under `provider="local"` the `lifespan` constructs no `storage.Client` and the warmup makes no Vertex call, so a credential-free `docker compose up` starts and `/healthz` passes. A test asserts `storage.Client` is not constructed on a local boot. _(AC 10 / correctness.)_

E2. The model load must be **offline at run time**: the image bakes the model into its cache and sets `HF_HUB_OFFLINE=1`, so no container start fetches weights. The lazy first-encode path still loads from the baked cache, never the network. _(AC 10 / offline constraint.)_

E3. Deployment artifacts must contain **no committed secret**: the Dockerfile, `docker-compose.yml`, `.env.example`, and backup scripts hold placeholders/env references only; the Phase 3 forbidden-literal hygiene test must still pass over the new files. _(AC 7 / safety.)_

E4. The schema stays **unchanged at deploy**: the Compose `db` init only creates the `vector`/`pg_trgm` extensions and applies migrations `001`–`007` as-is; no step alters the `Vector(768)` column, the HNSW `vector_cosine_ops` index, or `pg_trgm`. _(AC 8 / correctness.)_

E5. The backup/restore tooling must be **prod-safe and verifiable**: both scripts fail closed on missing parameters, guard against a GCP/Cloud SQL host, and the restore drill ends in a verification query against a non-prod target. _(AC 11 / safety.)_

### Carried-over Phase 4 cleanup (fix opportunistically while adding deployment tests)

- **`reembed_all` has no end-to-end test (test-coverage — add):** Phase 4's `tests/test_reembed.py` exercises only the private `_update_batch` against a fake session; the spec's Part B test ("`reembed_all` … updates seeded rows … and is idempotent on a second run") was not written, so the job's batching, multi-table coverage, idempotency, and no-DDL-on-the-default-path properties have no regression guard. Add a seeded in-memory sqlite test for `reembed_all` as specified above. _(carried AC-9 / E3 verification gap.)_
- **`run_parity` has no end-to-end test (test-coverage — add):** Phase 4's `tests/test_parity.py` covers only the pure `jaccard_at_k`/`rank_correlation` functions and the query-set file; the spec's Part B test ("`run_parity` over a tiny seeded corpus with two fake embedders yields per-query metrics and means in range") was not written. Add it so the harness that `docs/parity_report.md` is rendered from is itself guarded. _(carried AC-9 verification gap.)_
- **`run_parity` top-k may contain duplicate `paper_id`s (correctness — minor, optional):** `app/parity.py:_ids` selects `Paper.id` joined to `PaperChunk` ordered by `cosine_distance`, so a paper with several near chunks can appear multiple times in the top-k list before de-duplication; the Jaccard set-overlap absorbs this but the rank-correlation positions can be distorted. If the parity harness is touched, de-duplicate `paper_id` preserving first-seen order before computing metrics, and note it in `docs/parity_report.md`. _(operator-only harness; non-blocking.)_

### Noted, no action

- AC 1/AC 10 full verification ("full suite green", "compose healthy") is only reproducible in the project's real **Python 3.12** environment and on a Docker host: the sandbox runs Python 3.14 where `conftest.py`'s partial `reportlab` mock makes any test transitively importing `app.pdfgen` fail at collection, and no Docker daemon is present. The Phase 4 touched-surface tests (18) pass here; confirm the full suite green under 3.12 and the stack healthy on the operator's Docker host. _(environmental; not a Phase 5 code defect.)_
- `apply_migrations.py` and `infra_bootstrap.sh` remain git-ignored (`.gitignore:8–9`): their on-disk content is secret-free but their edits are not version-controlled and do not appear in the reviewable diff. Pre-existing repo condition. _(context.)_
- Baking `all-mpnet-base-v2` (and its `torch` CPU dependency) into the image enlarges it (hundreds of MB). This is the intended mechanism for an offline, no-GPU school server and is loaded once at lifespan; image size is an accepted trade for offline boot. _(data.)_
