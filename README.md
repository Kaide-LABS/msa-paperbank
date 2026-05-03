# MSA Paperbank

A single-course (MTH102) WhatsApp bot that sends past exam papers to students. It receives WhatsApp messages, identifies the intent and paper details, and returns a PDF via WhatsApp Cloud API.

## Quick Start
1. Clone this repo: `git clone <repo-url> && cd msa-paperbank`
2. Install dependencies: `pip install -r requirements.txt`
3. Set up `.env` (use `.env.example` as a template).
4. Run migrations via `psql`: `\i migrations/001_init.sql`, `\i migrations/002_phase2.sql`, `\i migrations/003_phase3.sql`
5. Deploy: `make deploy`

## Daily Ops
- Check bot health: `make smoke`
- Check logs: `make logs`
- List live papers: `python -m admin.list`
- See usage stats: `python -m admin.stats`

## Adding a Paper
See `RUNBOOK.md` Section 2.

## Secrets
All secrets live in GCP Secret Manager (`WA_ACCESS_TOKEN`, `WA_APP_SECRET`, `WA_VERIFY_TOKEN`, `DB_PASSWORD`, `ADMIN_BEARER_TOKEN`). You need the `roles/secretmanager.secretAccessor` IAM role to manage them.

## License
Sadaqah Jariyah project.