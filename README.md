# MSA Paperbank

Self-hosted past-paper bot using a local CPU embedder, PostgreSQL/pgvector, and optional MinIO. It needs no GCP credentials or internet at container start.

## Start

Prerequisites: Docker Engine with Compose v2 and persistent Linux storage. Copy `.env.example` to `.env`, fill it in, then run `docker compose up -d`. Add `--profile minio` to enable MinIO. Check `http://localhost:8080/healthz`. Postgres data is in `pgdata`; nightly archives are in `backups`; migrations run after the database health check. Use `docker compose logs -f app` for logs.

Expose the bot only through HTTPS and keep `.env` private. Run the restore drill against a non-production database; see [RUNBOOK.md](RUNBOOK.md).
