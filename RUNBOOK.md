# Operations runbook

These procedures are for self-hosted deployment only. Never run them against GCP production.

## Start, stop, upgrade

Copy `.env.example` to `.env`, fill it in, then run `docker compose up -d`. Use `docker compose --profile minio up -d` for MinIO. The app waits for a healthy database and applies numbered migrations with `apply_migrations.py`. Keep the `pgdata` and `backups` volumes during upgrades. Use `docker compose down` to stop.

## Nightly backup

The `backup` companion runs `scripts/backup.sh` every 24 hours. It creates timestamped custom-format `pg_dump` archives in the mounted `backups` volume and prunes files older than `RETENTION_DAYS` (default 14). Inspect with `docker compose logs backup`. It fails closed for GCP/Cloud SQL and exits non-zero on dump failure.

## Restore drill

Run on a maintenance host, never production: choose an archive under `/backups`, set `BACKUP_FILE` and `RESTORE_DATABASE=paperbank_restore_drill`, then run `docker compose run --rm backup sh /scripts/restore.sh`. The script rejects production names, restores into the named non-prod database, and finishes with row-count queries for `papers` and `paper_chunks`. Record the counts and drill date.

## Logs and health

Use `docker compose ps`, `docker compose logs --since=30m app`, and `curl http://localhost:8080/healthz`. Logs use `LOG_LEVEL` (normally `INFO`).

## Public HTTPS reverse proxy

Only the proxy is public. It terminates TLS and forwards to `127.0.0.1:8080`. Public routes are `/healthz`, `/tool/retrieve`, and `/webhook` (WhatsApp uses `/webhook`). Caddy configuration is `bot.example.org { reverse_proxy 127.0.0.1:8080 }`. For nginx, configure a TLS `server` for `bot.example.org`, certificate and key paths, and `proxy_pass http://127.0.0.1:8080` with `Host` and `X-Forwarded-Proto` headers. Never proxy Postgres or MinIO, and never point this runbook at GCP production.
