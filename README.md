# MSA Paperbank

Self-hosted past-paper bot for PAU students, using a local CPU embedder, PostgreSQL/pgvector, and optional MinIO. It needs no GCP credentials or internet at container start.

## How students use it

Students use it in **Microsoft Teams**, not WhatsApp. A Teams agent built in Microsoft Copilot Studio takes the student's request and calls this service's `POST /tool/retrieve` endpoint (bearer-token protected). The service replies with the matching paper's course, year and semester and a signed `GET /download` link that works for about 15 minutes and serves the PDF.

A sample tool definition (Swagger 2.0) and a test plan for the Copilot Studio setup are in [spike/copilot-studio/](spike/copilot-studio/). The older WhatsApp channel is no longer how students reach the bot, though its webhook code is still in the repository.

## Start

Prerequisites: Docker Engine with Compose v2 and persistent Linux storage. Copy `.env.example` to `.env`, fill it in, then run `docker compose up -d`. Add `--profile minio` to enable MinIO. Check `http://localhost:8080/healthz`. Postgres data is in `pgdata`; nightly archives are in `backups`; migrations run after the database health check. Use `docker compose logs -f app` for logs.

Expose the bot only through HTTPS and keep `.env` private. Run the restore drill against a non-production database; see [RUNBOOK.md](RUNBOOK.md).

## Privacy and opt-out

The bot stores only what it needs to answer past-paper queries. On the legacy WhatsApp channel, users may stop being tracked at any time by sending `STOP TRACKING`, after which their stored interaction data is cleared.

## Cutover

To move an existing GCP deployment onto this self-hosted stack, follow [CUTOVER.md](CUTOVER.md). Every cutover step is dry-run by default and runs only after written sign-off; GCP production stays running and reversible until then.
