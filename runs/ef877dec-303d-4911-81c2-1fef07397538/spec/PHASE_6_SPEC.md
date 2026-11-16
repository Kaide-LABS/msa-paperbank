# Phase 6 — Cutover tooling (scripted, NOT executed) + sign-off-gated GCP teardown: dump/copy/restore/re-embed/parity/side-by-side/webhook-move/restore-drill, then delete all GCP code, deps and scripts

## Goal
Finish the migration. Ship the **complete cutover runbook and tooling** for moving the bot off GCP onto the self-hosted stack — **authored, guarded, tested for well-formedness, and NOT executed against production** — and then the **final, sign-off-gated teardown** that removes every GCP code path, dependency and script from the repository so that **no `google.cloud`, `google-genai`, `vertexai`, or `cloud-sql-connector` import remains** (AC 12). The cutover tooling covers, in order: **dump Cloud SQL** (read-only export from `ummah`), **copy the GCS bucket** to the self-hosted object store, **restore** into the Compose Postgres, **re-embed** (Phase 4's `reembed_all`), **parity check** old-vs-new (Phase 4's harness), **side-by-side** run of the old GCP deploy against the new local deploy, **move the WhatsApp webhook**, and the **restore-from-backup drill** (Phase 5's `scripts/restore.sh`). Every script defaults to a **dry run**, refuses to touch prod without an explicit written-sign-off flag plus a committed sign-off record, and is **never run in this phase**. GCP production (`ummah`) stays **running and reversible** throughout (AC 13); nothing here mutates prod. The teardown of the *repository's GCP code* is a reversible git change that does not touch the live GCP *project*. No behaviour regression on the WhatsApp or `/tool/retrieve` path under `provider="local"`; the `Vector(768)` + HNSW + `pg_trgm` schema is unchanged. Satisfies AC 12, 13.

## Scope
In: a `cutover/` tooling set + a `CUTOVER.md` operator runbook sequencing the eight cutover steps, each script **read-only against prod** (export/rsync) or **writing only to the self-hosted stack**, **dry-run by default**, and gated behind an explicit `--confirm` flag **and** a committed sign-off marker so it cannot run accidentally; reuse of the already-shipped provider-neutral pieces (`app/reembed.py`, `app/parity.py`, `scripts/restore.sh`) rather than re-implementing them; a `side_by_side` comparison harness that queries two running HTTP endpoints (old GCP deploy, new local deploy) over `/tool/retrieve` and reports top-k agreement (depends on no in-process GCP code, so it survives the teardown); a WhatsApp webhook-move checklist; the **sign-off-gated teardown**: flip the `provider` default from `gcp` to `local` in `app/config.py`, delete `app/providers/gcp/`, delete the now-dead Vertex/GCS modules and imports in the live app tree (`app/embeddings.py`, the Vertex client in `app/llm.py`, the Vertex path in `app/ocr.py`, the top-level `from google.cloud import storage` + `app.state.gcs` in `app/main.py`), remove the `gcp` branches from `app/providers/__init__.py`, and drop the GCP packages from `requirements.txt`; re-point or remove the tests that referenced the deleted GCP paths **without weakening any surviving behavioural assertion**; a repo-wide **import-hygiene gate** proving the four named families are gone. Out: executing any cutover step against prod, deleting or modifying the GCP *project/infrastructure* (`ummah` Cloud SQL, bucket, Secret Manager), any Azure work (never), topic-level search / question-index work (separate later run), and any new retrieval behaviour. The schema (`Vector(768)`, HNSW, `pg_trgm`) is unchanged.

Teardown rule used throughout: the cutover scripts are **operator tools that are authored and tested but NEVER executed in this phase**; prod reads are **read-only**; every prod-touching action is **dry-run by default** and requires an explicit `--confirm` flag plus a committed written-sign-off marker (`docs/SIGNOFF.md` present and non-empty). The **code** teardown removes GCP from the *repository* (reversible via git history) and leaves the GCP *production project* untouched and reversible; the two are distinct and only the first happens in-repo this phase. Secrets are never committed; `.env.example` stays placeholder-only; the Phase 3 source-hygiene test continues to hold.

## Part A (first agent)

### Files
- `cutover/01_dump_cloudsql.sh` (new) — read-only export of the prod Cloud SQL database to a local archive (`gcloud sql export sql` to a staging bucket, or `pg_dump` over the Cloud SQL connector in read-only), written to a mounted staging dir. Dry-run by default (prints the exact command and exits 0 without running it); real execution requires `--confirm` **and** a present `docs/SIGNOFF.md`. Never writes to prod; never deletes anything.
- `cutover/02_copy_bucket.sh` (new) — `gsutil rsync` (or equivalent) from the prod GCS bucket to the self-hosted object-store root (`OBJECT_STORE_DIR`) / MinIO. Read-only on the source; same dry-run + `--confirm` + sign-off guard.
- `cutover/03_restore_selfhosted.sh` (new) — restore the dumped archive into the Compose Postgres (`pg_restore` into the **self-hosted** `paperbank` DB, never a Cloud SQL host — reuse the host guard from `scripts/restore.sh`). Writes only to the self-hosted stack.
- `cutover/04_reembed.sh` (new) — thin wrapper invoking the already-shipped `python -m app.reembed` (`reembed_all`) against the self-hosted DB so the restored Vertex vectors are replaced by local-CPU 768-dim vectors in the unchanged `Vector(768)` column. No schema change; no network beyond the local model.
- `cutover/05_parity.sh` (new) — thin wrapper invoking the already-shipped parity harness (`app/parity.py` / `run_parity`) over the fixed query set, writing an updated cutover parity report; references `docs/parity_report.md`'s threshold as the pass gate.
- `cutover/06_side_by_side.py` (new) — queries two **HTTP** endpoints (old GCP deploy URL, new local deploy URL) over `/tool/retrieve` for the fixed query set and reports per-query top-k agreement + a summary; parameterised by env/flags, no secret literals, no in-process GCP import (so it still runs after Part B's teardown).
- `cutover/07_webhook_move.md` (new) — the WhatsApp webhook-move checklist (Meta App dashboard callback-URL swap from the GCP deploy to the new HTTPS reverse proxy, verify-token reuse, `/webhook` GET challenge, rollback step). Documentation only; executes nothing.
- `CUTOVER.md` (new) — the operator runbook sequencing steps 01–07 + the Phase 5 restore drill (`scripts/restore.sh`) as step 08, each with its guard, its reversibility/rollback note, and an explicit "**run only after written sign-off; GCP prod stays running until verified**" banner.
- `docs/SIGNOFF.md` (new) — a **placeholder** sign-off record (unsigned by default) that the scripts check for and that the owner fills in; its presence+content is the gate the cutover and teardown read. Contains no secret.
- `tests/test_cutover_tooling.py` (new).

### Interfaces and behaviour
- **Dry-run by default, prod-safe:** every prod-touching script (`01`, `02`) prints the exact command it *would* run and exits 0 **without running it** unless `--confirm` is passed **and** `docs/SIGNOFF.md` exists and is non-empty; absent either, it refuses to touch prod. All prod access is read-only (export/rsync); none mutates or deletes `ummah`.
- **Self-hosted writes only:** `03`/`04`/`05` write exclusively to the self-hosted stack and reuse the Phase 5 Cloud-SQL-host guard so they cannot target a `*cloudsql*`/`*google*` host.
- **Reuse, don't re-implement:** `04`/`05` call the Phase 4 `reembed_all` / `run_parity` entrypoints; `08` calls Phase 5's `scripts/restore.sh`. No duplicated migration, re-embed, or parity logic.
- **Teardown-survivable side-by-side:** `06_side_by_side.py` compares two HTTP services and imports no `app.providers.gcp` / `google.*` symbol, so it keeps working after Part B deletes the in-repo GCP code.
- **No secrets, no execution:** no script embeds a DB password, Cloud SQL string, GCP project id, or token (env/flags only); nothing is executed against prod in this phase; the Phase 3 forbidden-literal hygiene test continues to pass over the new files.

### Tests (`tests/test_cutover_tooling.py`)
- Every `cutover/*.sh` exists and is syntactically valid (`sh -n`), defaults to dry-run (asserts the script refuses real execution without `--confirm`/sign-off — string/structural assertion over the guard), reads credentials from the environment (no hardcoded secret — assert the Phase 3 forbidden-literal set is absent), and the prod-touching scripts carry the read-only + sign-off guard.
- `cutover/06_side_by_side.py` parses/imports cleanly and imports **no** `google.*` / `app.providers.gcp.*` symbol (AST or import-level assertion); it exposes a callable that, given two fake endpoints, returns per-query agreement (pure, no network).
- `CUTOVER.md` and `cutover/07_webhook_move.md` exist, are non-empty, and mention the required steps (dump, copy, restore, re-embed, parity, side-by-side, webhook move, restore drill) and the "run only after sign-off" banner — presence assertions over the text.
- No test invokes `gcloud`, `gsutil`, `pg_dump`/`pg_restore`, Docker, or any network; all checks are static/structural (AC 2).

## Part B (second agent)

### Files
- `app/config.py` (edit) — flip the `provider` **default** from `"gcp"` to `"local"` so a credential-free checkout boots self-hosted by default; keep the field so `provider="gcp"` is still a *settable* legacy value only until its adapters are deleted below (after deletion, selecting `gcp` raises the factory's `ValueError`, which is the intended post-teardown behaviour).
- `app/providers/__init__.py` (edit) — remove the `name == "gcp"` branch from each of `get_object_store`/`get_embedder`/`get_engine_provider`/`get_secrets_provider`; the default/unknown path raises `ValueError` as today. No lazy `app.providers.gcp.*` import remains.
- `app/providers/gcp/` (delete) — remove the whole package (`storage.py`, `embedder.py`, `engine.py`, `secrets.py`, `__init__.py`).
- `app/main.py` (edit) — remove `from google.cloud import storage` and the `app.state.gcs = storage.Client(...)` line entirely (the provider-gate added in Phase 5 collapses to "never construct it"); `app.state.gcs` is no longer set. No behaviour change on the live `provider="local"` path (which already left it `None`).
- `app/embeddings.py`, `app/llm.py`, `app/ocr.py` (delete or de-Vertex) — remove the Vertex/`google-genai` client code. Live retrieval already routes through `app.state.embedder` (Phase 4); any remaining import of these modules on the live path must be cut or re-pointed at the provider seam. If a module is wholly Vertex (e.g. `app/embeddings.py`), delete it and remove its import sites; if it mixes live-still-used logic with Vertex, excise only the Vertex client.
- `requirements.txt` (edit) — remove `google-genai`, `google-cloud-storage`, `cloud-sql-python-connector`, `google-cloud-secret-manager` and any `vertexai` pin; drop the Google ingest/auth packages (`google-api-python-client`, `google-auth`, `google-auth-httplib2`) together with the GCP-only ingest scripts they serve (see below). Keep everything the self-hosted stack needs (`sentence-transformers`, `pg8000`, `pgvector`, FastAPI, etc.).
- GCP-only ingest/admin/review scripts (delete or de-Vertex) — `cloud_ingest/` (GCP ingest, frozen/out-of-scope), `scripts/drive_import.py`, `scripts/upload_test_batch.py`, and the Vertex/GCS references in `admin/upload.py`, `admin/health.py`, `review/main.py`, `apply_migrations.py`: remove the GCP imports so the four named families are gone repo-wide. `apply_migrations.py` is git-ignored but must not import a deleted package; de-Vertex it in place.
- `scripts/restore_drill.sh` (delete) — the GCP-era Cloud SQL restore drill, superseded by Phase 5's `scripts/restore.sh`.
- Tests touching deleted GCP paths (edit) — re-point or remove `tests/*` references to `app.embeddings.embed_query`, `app.providers.gcp.*`, `google.cloud.storage.Client`, etc. (notably `tests/test_deploy_compose.py`'s `app.embeddings` patch), **without weakening any surviving behavioural assertion**; delete only assertions whose subject no longer exists.
- `tests/test_no_gcp_imports.py` (new).
- `README.md` / `RUNBOOK.md` (edit) — remove the last GCP-era operational references (if any remain) and point the cutover procedure at `CUTOVER.md`.

### Interfaces and behaviour
- **Zero GCP imports:** after teardown, a repo-wide search finds no `google.cloud`, `google-genai`/`google.genai`, `vertexai`, or `cloud-sql-connector`/`cloud_sql` import in any tracked `.py` file (AC 12). `requirements.txt` no longer lists those packages.
- **Local path unchanged:** under `provider="local"` the app boots healthy, `/healthz` returns `{"ok": True}`, and WhatsApp + `/tool/retrieve` retrieval behave exactly as after Phase 5 (the live path never depended on the deleted GCP code). Selecting the removed `provider="gcp"` now raises `ValueError` from the factory — the intended post-teardown outcome.
- **Prod untouched & reversible:** deleting repo code changes nothing in the GCP *project*; `ummah` Cloud SQL/bucket/Secret Manager remain running and the deletion is reversible via git history (AC 13).
- **Schema unchanged:** no migration is added or altered; `Vector(768)`/HNSW/`pg_trgm` are exactly as Phase 5 leaves them.
- **No secrets:** no deleted/edited file leaves a plaintext DB password, Cloud SQL string, or GCP project id behind; the Phase 3 hygiene test still passes.

### Tests (`tests/test_no_gcp_imports.py`)
- A repo-wide scan over tracked `.py` files (excluding the `runs/`, `.osa/`, and `msa-paperbank/` stale-mirror trees and the `cutover/` docs) asserts **zero** matches for the four named import families (`import google.cloud`/`from google.cloud`, `google.genai`/`google-genai`, `vertexai`, `cloud_sql`/`cloud-sql-connector`) — the mechanical AC 12 gate.
- `requirements.txt` contains none of `google-genai`, `google-cloud-storage`, `cloud-sql-python-connector`, `google-cloud-secret-manager`, `vertexai`.
- The app imports and boots under `provider="local"` with the GCP package deleted: `TestClient` `/healthz` returns 200, no `google.*` import is triggered (reuse the Phase 5 credential-free boot test, re-pointed off the deleted `app.embeddings` patch).
- `get_object_store`/`get_embedder`/`get_engine_provider` raise `ValueError` for `provider="gcp"` (the branch is gone), and succeed for `provider="local"`.
- No network, no Docker; all static or `TestClient` with injected fakes (AC 2).

## Acceptance-criteria mapping
- **AC 12 — no `google.cloud`, `google-genai`, `vertexai`, `cloud-sql-connector` imports remain:** Part B deletes `app/providers/gcp/`, the Vertex/GCS modules and import sites, and the GCP packages from `requirements.txt`; the factory loses its `gcp` branches. Check: `tests/test_no_gcp_imports.py` scans every tracked `.py` and `requirements.txt` for the four families and finds none.
- **AC 13 — cutover/teardown scripts exist but are not executed; GCP prod running and reversible:** Part A authors the full `cutover/` set + `CUTOVER.md`, every prod-touching step dry-run-by-default and sign-off-gated, none executed this phase; the in-repo code teardown is git-reversible and touches no GCP infrastructure. Check: `tests/test_cutover_tooling.py` asserts the scripts exist, are valid, are guarded, and run nothing; the diff executes no cutover step.
- **AC 7 (carried) — no secrets in sources:** every new/edited file carries placeholders/env references only; `docs/SIGNOFF.md` and `.env.example` hold no secret. Check: forbidden-literal assertions in the new tests + the existing `tests/test_secrets_engine_auth.py`.
- **AC 8 (carried) — schema unchanged:** no migration added/altered; `reembed.sh` runs the existing no-DDL `reembed_all`. Check: no schema DDL in this phase's diff.
- **AC 2 (carried) — no network in unit tests:** every new test is static/structural or `TestClient` with injected fakes; no `gcloud`/`gsutil`/`pg_*`/Docker/network. Check: suite runs with no outbound network.
- **AC 1 (carried) — existing pytest passes:** removing the never-live GCP code is behaviour-preserving on the `provider="local"` path; GCP-referencing tests are re-pointed without weakening assertions. Check: `pytest` passes in the project's Python 3.12 environment.

## Documentation sources
- Cloud SQL export/import (read-only `gcloud sql export sql`): https://cloud.google.com/sql/docs/postgres/import-export/import-export-sql
- `gsutil rsync` / bucket copy semantics: https://cloud.google.com/storage/docs/gsutil/commands/rsync
- PostgreSQL `pg_dump`/`pg_restore`: https://www.postgresql.org/docs/current/app-pgrestore.html
- Meta WhatsApp Cloud API — webhook configuration and verification: https://developers.facebook.com/docs/graph-api/webhooks/getting-started
- Python `ast` module (import-hygiene scanning without executing code): https://docs.python.org/3/library/ast.html

## Out of scope for this phase
- **Executing** any cutover step against prod (dump, bucket copy, restore, re-embed, parity, side-by-side, webhook move) — authored and tested only; run on the operator's timeline after written sign-off.
- Deleting or modifying the GCP **project/infrastructure** (`ummah` Cloud SQL, GCS bucket, Secret Manager, IAM) — never done in-repo; prod stays running and reversible.
- Any Azure work (never); local LLMs/GPUs; the daily model cost-cap breaker; study companion; Teams push notifications; the Copilot Studio agent itself.
- Topic-level search and question-index work (separate later run).
- Any retrieval-behaviour change, new migration, or schema alteration.

## Spec assumptions

Gaps found while writing this spec were resolved as follows (nobody was asked):

- **"GCP teardown" splits into two distinct actions.** AC 12 ("no GCP imports remain in the codebase") requires deleting GCP **code** from the repository — a reversible git change touching no live infrastructure — so it is performed this phase. AC 13's / the PRD's "teardown … not executed, prod reversible" refers to tearing down the GCP **production project** and to **executing** the operational cutover — neither is done here. The repo teardown is gated on a committed written-sign-off marker (`docs/SIGNOFF.md`) to honour "gated on written sign-off," and remains fully reversible via git.
- **Cutover scripts are self-contained and teardown-survivable.** They drive `gcloud`/`gsutil`/`pg_*` and the already-shipped provider-neutral `reembed_all`/`run_parity`/`scripts/restore.sh`, and the side-by-side harness compares two **HTTP** deployments — none imports `app/providers/gcp/`, so Part B's deletion does not break them and the ordering paradox (needs-GCP-to-compare vs delete-GCP) dissolves.
- **Dry-run-by-default + `--confirm` + sign-off marker** is the guard on every prod-touching script, so an accidental run is inert and nothing reaches `ummah` without a deliberate signed action. Prod access is read-only (export/rsync).
- **The `provider` default flips to `"local"`** so the post-teardown repo boots self-hosted with no GCP code; `provider="gcp"` becomes an unselectable legacy value whose factory branch is gone (raises `ValueError`).
- **GCP ingest/auth deps and their scripts go together.** `google-api-python-client`/`google-auth*` serve only the frozen, out-of-scope GCP ingest scripts (`cloud_ingest/`, `scripts/drive_import.py`); the PRD's "delete all GCP code, dependencies and scripts" covers them, so they are removed as a unit. If any is load-bearing for a still-live path, de-Vertex in place instead and flag it.
- **The authoritative tree is the root-level codebase**; the stale `msa-paperbank/` mirror is not edited and is excluded from the import-hygiene scan.

## Implications

Second-order consequences found by an independent review of this spec. This section only adds to the spec; the locked PRD is unchanged.

### Additional acceptance criteria

E1. The cutover scripts must be **inert by default**: with no `--confirm` and no `docs/SIGNOFF.md`, each prod-touching script prints its intended command and exits 0 without running it, so CI/accidental invocation reaches no GCP service. A test asserts the dry-run refusal. _(AC 13 / safety.)_

E2. The import-hygiene gate must scan **only runtime/tracked sources**, excluding `runs/`, `.osa/`, the `msa-paperbank/` mirror, and documentation, so historical/untrusted trees don't mask or falsely trip AC 12. The scan parses rather than imports (no side effects). _(AC 12 / correctness.)_

E3. GCP-referencing tests must be **re-pointed, not weakened**: deleting `app/providers/gcp/` and the Vertex modules breaks tests that patched them (e.g. `tests/test_deploy_compose.py` patches `app.embeddings.embed_query`); each must be re-pointed at the surviving seam or removed only where its subject is gone, with every surviving behavioural assertion intact. _(AC 1 / test-integrity.)_

E4. The teardown must leave the **live path byte-for-byte equivalent** under `provider="local"`: retrieval already routes through `app.state.embedder`/`app.state.store`, so removing the never-constructed `app.state.gcs` and the Vertex modules changes no served response. A credential-free `TestClient` boot + a retrieval smoke assertion guard this. _(AC 1 / correctness.)_

E5. No deployment/cutover artifact may carry a **committed secret**: the new `cutover/` scripts, `CUTOVER.md`, and `docs/SIGNOFF.md` hold placeholders/env references only; the Phase 3 forbidden-literal hygiene test must still pass over them. _(AC 7 / safety.)_

### Carried-over cleanup (fix opportunistically)

- **MinIO health check likely never passes (correctness — flagged in Phase 5 review):** `docker-compose.yml`'s `minio` service uses `mc ready local`, but the stock `minio/minio` image has no pre-configured `mc` alias named `local`, so the profile-gated service may report unhealthy. If the Compose file is touched, switch to the HTTP liveness probe (`curl -f http://127.0.0.1:9000/minio/health/live`). _(optional; MinIO is off by default.)_
- **`cutover/03`/restore reuse of `scripts/restore.sh`'s redundant `createdb --if-exists` (cosmetic):** `scripts/restore.sh:18` passes `--if-exists` to `createdb`, which has no such flag; it is swallowed by `|| true` and made moot by the following drop/create. Drop the redundant line if the restore path is touched. _(cosmetic; harmless.)_
- **README content loss (docs — optional):** the Phase 5 README rewrite dropped the Privacy and opt-out (`STOP TRACKING`) summary; if `README.md` is edited, restore a brief privacy/opt-out note so operators retain it. _(non-blocking.)_

### Noted, no action

- Full AC 1/AC 12 verification ("full suite green", "no GCP imports") is only fully reproducible in the project's real **Python 3.12** environment: the sandbox runs Python 3.14 where `conftest.py`'s partial `reportlab` mock makes any test transitively importing `app.pdfgen` fail at collection. The Phase 5 touched-surface tests (20) pass here; confirm the full suite green under 3.12 after teardown. _(environmental; not a code defect.)_
- `apply_migrations.py` and `infra_bootstrap.sh` remain git-ignored: their on-disk edits (de-Vertex) are secret-free but do not appear in the reviewable diff. Pre-existing repo condition. _(context.)_
- Operational cutover (actually dumping prod, copying the bucket, moving the webhook) happens on the school/owner timeline **after** written sign-off, using this phase's tooling; it is out of scope for the dispatched build and is never executed here. _(process.)_
