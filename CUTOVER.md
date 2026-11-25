# Cutover runbook — GCP → self-hosted

> ## ⚠️ Run only after written sign-off; GCP prod stays running until verified.
>
> Every prod-touching step below is **dry-run by default** and refuses to touch
> production unless you pass `--confirm` **and** `docs/SIGNOFF.md` carries a
> `## Status: GRANTED` line. Nothing in this runbook is executed by the migration
> build — these are operator tools run on the school's timeline. All prod access is
> **read-only** (export/rsync); the GCP production project is never mutated or deleted and
> stays running and reversible throughout. If any step fails verification, **stop and
> roll back** — the old GCP deploy keeps serving.

## Before you start
1. The self-hosted stack is up (`docker compose up -d`) and `GET /healthz` returns
   `{"ok": true}` — see `RUNBOOK.md`.
2. `docs/SIGNOFF.md` has been edited to `## Status: GRANTED` and committed.
3. Credentials/identifiers are set in the environment only (never committed). See each
   script's header for the exact variables.

## Steps (run in order)

| # | Step | Script | Guard | Prod impact | Rollback |
|---|------|--------|-------|-------------|----------|
| 01 | **Dump Cloud SQL** | `cutover/01_dump_cloudsql.sh` | dry-run + `--confirm` + sign-off | read-only export | none (prod untouched) |
| 02 | **Copy the bucket** | `cutover/02_copy_bucket.sh` | dry-run + `--confirm` + sign-off | read-only rsync | none (prod untouched) |
| 03 | **Restore** into self-hosted Postgres | `cutover/03_restore_selfhosted.sh` | dry-run + `--confirm` + host/DB guard | none (writes self-hosted only) | drop the restored self-hosted DB and re-run |
| 04 | **Re-embed** with the local CPU model | `cutover/04_reembed.sh` | dry-run + `--confirm` | none (self-hosted DB only) | restore from backup (step 08) and re-run |
| 05 | **Parity check** old-vs-new top-k | `cutover/05_parity.sh` | dry-run + `--confirm` | none (read-only) | n/a (measurement only; gate on `docs/parity_report.md`) |
| 06 | **Side-by-side** old vs new `/tool/retrieve` | `cutover/06_side_by_side.py` | HTTP only | none | n/a (comparison only) |
| 07 | **Move the WhatsApp webhook** | `cutover/07_webhook_move.md` | manual checklist | Meta dashboard swap | re-point callback URL back to GCP deploy |
| 08 | **Restore-from-backup drill** | `scripts/restore.sh` | non-prod DB + host guard | none (self-hosted drill DB) | n/a (drill) |

### 01 — Dump Cloud SQL (read-only export)
Exports the prod database to a staging bucket and downloads it locally. Read-only;
prod is never written. Dry-run prints the exact `gcloud sql export` command.

### 02 — Copy the bucket (read-only rsync)
Mirrors the prod GCS bucket into `OBJECT_STORE_DIR`. No `-d`, so nothing on the source
is ever deleted.

### 03 — Restore into the self-hosted Postgres
`pg_restore` into the Compose Postgres. Reuses the Cloud-SQL-host guard: it refuses a
`*cloudsql*`/`*google*` host and a prod DB name, so it can only write self-hosted.

### 04 — Re-embed with the local CPU model
Wraps `python -m app.reembed` (`reembed_all`): replaces the restored Vertex vectors
with local 768-dim vectors in the unchanged `Vector(768)` column. No schema change.

### 05 — Parity check (old vs new top-k)
Wraps the `app.parity` harness over `data/parity_queries.json`. Pass gate: the
thresholds recorded in `docs/parity_report.md` (mean Jaccard@10 ≥ 0.70, mean rank
correlation ≥ 0.60).

### 06 — Side-by-side
Queries the old GCP deploy and the new local deploy over `/tool/retrieve` for the
fixed query set and reports top-k agreement. HTTP only — it survives the in-repo GCP
teardown.

### 07 — Move the WhatsApp webhook
Follow `cutover/07_webhook_move.md`: swap the Meta callback URL to the new HTTPS
reverse proxy, reuse the verify token, confirm the `GET /webhook` challenge, verify a
live query, and roll back by re-pointing the callback URL if needed.

### 08 — Restore-from-backup drill (restore drill)
Run `scripts/restore.sh` against a non-prod drill DB to prove the nightly backups
restore cleanly. See `RUNBOOK.md`.

## After verification
Once steps 01–08 and the webhook move are verified and the school has run on the
self-hosted stack long enough to be confident, the owner may separately decide to tear
down the GCP **project**. That infrastructure teardown is **out of scope for
this repository** and is never performed by these scripts — the in-repo GCP *code*
removal is a distinct, git-reversible change.
