# PHASE 3 — Technical Spec (Execution Blueprint)

**Source of truth:** `PRD.md` (canonical, narrow V1 scope). `MASTER_PRD.md` is reference-only.
**Audience:** the execution agent that will write the code. Do not deviate without amending this file first.
**Predecessors:** `PHASE_1_SPEC.md`, `PHASE_2_SPEC.md`. Both are merged and approved.

---

## 0. Phase 3 mission (one sentence)

Make the system *operable by Ibrahim alone* and *launchable*: add paper retirement, read-only admin inspection commands, deploy and rollback automation, structured ops monitoring, secrets wiring through Secret Manager, a token-rotation runbook, and an end-to-end smoke test. **No new product features. No Drive importer. No `users` table. No curation review CLI.** MTH102-only still locked.

---

## 1. Scope (locked)

**In Phase 3:**

1. **`is_retired` soft-delete on papers.** Additive migration `migrations/003_phase3.sql`. Retrieval filters out retired papers in both ILIKE and semantic-fallback paths.
2. **Admin retire command:** `python -m admin.retire <paper_id> --reason "<text>"`.
3. **Admin list command:** `python -m admin.list [--year YYYY] [--semester ...] [--include-retired]`.
4. **Admin audit command:** `python -m admin.audit [--since YYYY-MM-DD] [--phone E164] [--limit N] [--csv PATH]` — pulls slices of `request_log`.
5. **Admin stats command:** `python -m admin.stats [--days N]` — counts per outcome, total LLM tokens last N days, top-10 most-requested years.
6. **Cloud Run deploy via `Makefile`** (`make deploy`, `make migrate`, `make logs`, `make rollback`, `make smoke`). One-page operations surface.
7. **Secrets wired through Secret Manager.** Cloud Run service is deployed with `--set-secrets` flags; `.env` is for local-dev only.
8. **One log-based metric + one alert.** `errors_per_hour` metric counts log lines where `severity>=ERROR AND service=paperbank-web`. Alert at ≥ 5 over 10 minutes → email Ibrahim.
9. **Smoke script `scripts/smoke.sh`.** `healthz` → 200; `GET /webhook` with bad token → 403; `POST /webhook` with bad signature → 401; `POST /webhook` with valid signature + minimal payload → 200.
10. **`RUNBOOK.md`** — plain-English. Five sections: rotate Meta token; add a paper; retire a paper; bot is silent (triage); restore from backup.
11. **`README.md` rewritten** for Ibrahim. Five steps: clone, install, set up `.env`, run migrations, deploy. No jargon.
12. **`LAUNCH.md`** — one-page launch checklist mapping each box to the verification command.
13. **Cost guard hardening.** Existing `request_rate_limit_per_hour` gate is preserved; add a daily token-budget cap at the LLM router level.

**Out of Phase 3 (do not build):**

- Drive importer (`scripts/drive_import.py`).
- `users` table, `inferred_courses`, `pending_submissions`, curation review CLI.
- Any new tables besides what's needed for `is_retired`.
- Multi-course ingestion. The `--course` flag does **not** appear on any admin command; everything stays MTH102-locked via `settings.hardcoded_course_code`.
- Web UI, Slack bot, dashboards, Looker, BI tools.
- Cloud Tasks, Pub/Sub, Cloud Scheduler. Daily token-budget reset is computed from `request_log`, not from a scheduler.
- Alembic / dbmate / Atlas / Liquibase / any migration tool. Migrations remain hand-applied SQL files. (PHASE_1_SPEC §16.)
- Async / background tasks on the request path.
- Templated WhatsApp messages, marketing/utility/auth template categories.

---

## 2. Repository layout (delta from Phase 2)

Files added (✦) or modified (∆):

```
msa-paperbank/
├── PHASE_3_SPEC.md            ✦
├── README.md                  ∆ (rewritten end-to-end; ≤ 1 page)
├── RUNBOOK.md                 ✦
├── LAUNCH.md                  ✦
├── Makefile                   ✦
├── scripts/
│   └── smoke.sh               ✦  (new dir)
├── app/
│   ├── retrieval.py           ∆ (filter is_retired)
│   ├── pipeline.py            ∆ (daily token budget guard; ≤ 8 LOC)
│   ├── db.py                  ∆ (Paper.is_retired)
│   ├── config.py              ∆ (daily_token_budget setting + admin_bearer_token)
│   └── (all other app/* files unchanged)
├── admin/
│   ├── retire.py              ✦
│   ├── list.py                ✦
│   ├── audit.py               ✦
│   └── stats.py               ✦
├── migrations/
│   └── 003_phase3.sql         ✦
└── tests/
    ├── test_retrieval_retired.py  ✦
    ├── test_admin_retire.py       ✦
    └── test_pipeline.py           ∆ (one new test for token-budget guard)
```

No other files change. Do not "tidy" Phase 1 / Phase 2 modules.

---

## 3. Pinned dependency additions (`requirements.txt`)

Append, do not reformat:

```
google-cloud-secret-manager==2.20.2
tabulate==0.9.0
```

`tabulate` is used by `admin/list.py` and `admin/stats.py` for terminal-readable tables. `google-cloud-secret-manager` is used by `app/config.py`'s optional Secret Manager loader (§5).

Dev-only: nothing new.

---

## 4. Schema migration (`migrations/003_phase3.sql`)

Run order: must be applied after `002_phase2.sql`.

```sql
ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS is_retired BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS retired_by TEXT NULL,
    ADD COLUMN IF NOT EXISTS retired_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS retired_reason TEXT NULL;

CREATE INDEX IF NOT EXISTS papers_active ON papers (course_code, year DESC, semester) WHERE is_retired = FALSE;
```

The partial index lets retrieval ignore retired rows entirely. No backfill required: existing rows default `is_retired=FALSE`.

---

## 5. Configuration delta (`app/config.py`)

Add the following fields. All have defaults so existing deployments don't break.

| Field | Env var | Type | Default |
|---|---|---|---|
| `daily_token_budget` | `DAILY_TOKEN_BUDGET` | `int` | `200_000` (combined Flash input+output across `request_log` over the last 24h) |
| `admin_bearer_token` | `ADMIN_BEARER_TOKEN` | `SecretStr` | — (required only if `/admin/stats` HTTP endpoint is exposed; see §10. CLI commands don't need it.) |

**Optional Secret Manager loader.** Add a helper (not a class change):

```python
def load_settings_with_secret_manager() -> Settings:
    """If GCP_LOAD_FROM_SECRETS=1, load any *_FROM_SECRET=<secret-name> overrides.
    Otherwise behave exactly like Settings()."""
```

Behavior:
- If `os.environ.get("GCP_LOAD_FROM_SECRETS") != "1"`: return `Settings()`.
- Else: for every env var `FOO_FROM_SECRET=projects/.../secrets/.../versions/latest`, fetch via `google.cloud.secretmanager.SecretManagerServiceClient().access_secret_version(name=...)`, set `os.environ[FOO]` to the payload, then return `Settings()`.
- This is opt-in and used only on Cloud Run. Local dev uses `.env`.

Module-level `settings = load_settings_with_secret_manager()` replaces Phase 2's `settings = Settings()`.

---

## 6. Retrieval change (`app/retrieval.py`)

Both `find_paper` and `find_paper_by_semantic_query` add **one** new predicate at the top of their `where` chain:

```python
.where(Paper.is_retired == False)
```

Place it right after the course-code filter, before the active-risk soft filter. No other changes.

---

## 7. Pipeline change (`app/pipeline.py`)

One new guard, between step 3 (rate limit) and step 4 (Route).

```python
# 3b. Daily token budget guard (Phase 3)
twenty_four_h_ago = datetime.now(timezone.utc) - timedelta(hours=24)
budget_query = select(
    func.coalesce(func.sum(RequestLog.flash_input_tokens), 0)
    + func.coalesce(func.sum(RequestLog.flash_output_tokens), 0)
).where(RequestLog.received_at >= twenty_four_h_ago)
spent = session.execute(budget_query).scalar_one()
if spent >= settings.daily_token_budget:
    log_entry.outcome = "rate_limited"
    log_entry.error = "daily_token_budget_exceeded"
    session.commit()
    return TextReply(body="The bot has hit its daily limit. Try tomorrow morning, in shaa Allah.")
```

`outcome` reuses `"rate_limited"` so the per-hour count guard naturally excludes these from its denominator (already does). No new outcome string.

---

## 8. Admin commands

All five commands share the same boilerplate: argparse, `with SessionLocal() as session:`, exit codes (0 success, non-zero on user-input or business errors). All print human-readable summaries; `--csv` flags emit machine-readable CSV.

### 8.1 `admin/retire.py`

```
python -m admin.retire <paper_id> --reason "<text>" [--yes]
```
- Loads paper by id; if not found → exit 1 with "paper not found".
- Prints current state: `paper_id, course, year, semester, gcs_object, is_retired`.
- If already `is_retired=TRUE`: prints "already retired" and exits 0 (idempotent).
- If `--yes` not passed, prompts `Type 'yes' to confirm:`. Any other input aborts with exit 2.
- Sets `is_retired=TRUE`, `retired_by=os.environ.get("USER","ibrahim")`, `retired_at=now()`, `retired_reason=args.reason`. Commits.
- Prints `✓ Retired paper_id=<id> by <user> at <iso8601>`.

### 8.2 `admin/list.py`

```
python -m admin.list [--year YYYY] [--semester {harmattan,rain}] [--session {CA1,CA2,exam}] [--include-retired] [--csv PATH] [--limit 50]
```
- Builds a SELECT on `papers` filtered by the flags. Default excludes retired.
- Renders as table via `tabulate(...)` with columns: `id, course, year, semester, session, gcs_object, is_active_risk, held_until, is_retired, uploaded_at`.
- `--csv PATH` writes the same data as CSV; suppresses table output. Exit 0 always.

### 8.3 `admin/audit.py`

```
python -m admin.audit (--since YYYY-MM-DD | --phone E164) [--limit 100] [--csv PATH]
```
- One of `--since` / `--phone` is required (argparse mutually-exclusive group, required=True).
- Reads `request_log`, ordered `received_at DESC`, limited.
- Columns: `received_at, wa_from, user_text, routed_course, routed_year, routed_semester, outcome, matched_paper_id, flash_input_tokens, flash_output_tokens, error`.
- `--csv` mirrors §8.2.

### 8.4 `admin/stats.py`

```
python -m admin.stats [--days 7]
```
- Computes:
  - Total requests in window.
  - Counts per `outcome` (sent / not_found / ambiguous / error / rate_limited).
  - Sum of `flash_input_tokens + flash_output_tokens` in window.
  - Top-10 `(routed_course, routed_year, routed_semester)` triples by hit count, where `outcome='sent'`.
  - Number of papers in DB (`is_retired=FALSE`).
- Prints three small tables. No flags besides `--days`. Exit 0.

### 8.5 `admin/__init__.py` updated

Add a one-line `__all__ = ["upload", "retire", "list", "audit", "stats"]` so help text in tooling stays predictable. The Phase 1 / 2 `admin/upload.py` is untouched.

---

## 9. `Makefile` (top of repo)

```
PROJECT ?= $(shell gcloud config get-value project)
REGION  ?= africa-south1
SERVICE ?= msa-paperbank
SQL_INSTANCE ?= $(PROJECT):$(REGION):paperbank

.PHONY: deploy migrate logs rollback smoke test

deploy:
	gcloud run deploy $(SERVICE) \
	  --source . --region $(REGION) \
	  --service-account $(SERVICE)-sa@$(PROJECT).iam.gserviceaccount.com \
	  --add-cloudsql-instances $(SQL_INSTANCE) \
	  --set-env-vars GCP_PROJECT=$(PROJECT),GCP_LOCATION=global,CLOUD_SQL_INSTANCE=$(SQL_INSTANCE),GCP_LOAD_FROM_SECRETS=1 \
	  --set-secrets DB_PASSWORD=DB_PASSWORD:latest,WA_ACCESS_TOKEN=WA_ACCESS_TOKEN:latest,WA_APP_SECRET=WA_APP_SECRET:latest,WA_VERIFY_TOKEN=WA_VERIFY_TOKEN:latest,ADMIN_BEARER_TOKEN=ADMIN_BEARER_TOKEN:latest \
	  --memory 512Mi --cpu 1 --concurrency 40 --max-instances 2 --min-instances 0

migrate:
	@echo "Apply 001 -> 002 -> 003 in order via Cloud SQL Auth Proxy."
	@echo "Run: gcloud sql connect paperbank --user=$$DB_USER --database=paperbank"
	@echo "Then \\i migrations/001_init.sql; \\i migrations/002_phase2.sql; \\i migrations/003_phase3.sql"

logs:
	gcloud run services logs read $(SERVICE) --region $(REGION) --limit 200

rollback:
	gcloud run services update-traffic $(SERVICE) --region $(REGION) --to-revisions=PREVIOUS=100

smoke:
	./scripts/smoke.sh

test:
	pytest -q
```

The `migrate` target is intentionally a printed instruction, not a script. Cloud SQL Auth Proxy + interactive `psql` is the only path; we do not run a migration tool.

---

## 10. Smoke script (`scripts/smoke.sh`)

Bash, fail-fast (`set -euo pipefail`). Required env: `BASE_URL` (e.g. the Cloud Run URL), `WA_APP_SECRET`, `WA_VERIFY_TOKEN`.

Steps:
1. `curl -fsS "$BASE_URL/healthz"` must return `{"ok":true}`.
2. `curl -fsS -o /dev/null -w "%{http_code}" "$BASE_URL/webhook?hub.mode=subscribe&hub.verify_token=WRONG&hub.challenge=42"` must equal `403`.
3. `curl -fsS "$BASE_URL/webhook?hub.mode=subscribe&hub.verify_token=$WA_VERIFY_TOKEN&hub.challenge=42"` must return `42`.
4. Compute `body='{"object":"whatsapp_business_account","entry":[]}'`; `sig="sha256=$(printf '%s' "$body" | openssl dgst -sha256 -hmac "$WA_APP_SECRET" | awk '{print $2}')"`. POST with **wrong** signature → expect 401. POST with computed signature → expect 200 (empty payload returns 200 per `app/main.py`).
5. Print `SMOKE OK` and exit 0 only if every step matched.

This script is the single source-of-truth answer to "is the bot up?". It is also the body of the `make smoke` target.

---

## 11. `RUNBOOK.md` (skeleton)

Plain English. No jargon beyond the literal commands. Five H2 sections, in this order:

1. **Rotate the Meta access token.**
   - Steps: Meta Business Manager → System users → generate new token → save to Secret Manager (`gcloud secrets versions add WA_ACCESS_TOKEN --data-file=-`) → `make deploy`. One paragraph each.
2. **Add a past paper.** Two flows: `admin upload pdf` and `admin upload images`. One example each.
3. **Retire a paper.** `python -m admin.retire <id> --reason "..." --yes`. Why this is sometimes needed.
4. **The bot is silent — what to check.** A six-line flowchart: `make smoke` → check Meta webhook health → check Cloud Run logs (`make logs`) → check Cloud SQL is reachable → check Vertex quotas → escalate.
5. **Restore from backup.** Cloud SQL automated backups; the gcloud command to restore in place; how to re-run migrations afterward.

Each section ends with **one** literal command Ibrahim can copy. No prose drifts.

---

## 12. `README.md` (rewritten)

≤ 80 lines. Sections, in order:

1. What it is (one paragraph).
2. Quick start (5 numbered steps: clone, `pip install -r requirements.txt`, copy `.env.example` → `.env`, `\i migrations/00*_*.sql` via psql, `make deploy`).
3. Daily ops: `make smoke`, `make logs`, `python -m admin.list`, `python -m admin.stats`.
4. Adding a paper (link to RUNBOOK.md §2).
5. Where the secrets live (Secret Manager names + the IAM grant Ibrahim needs).
6. License & sadaqah jariyah note.

No architecture diagrams. No technology marketing. The PRDs already cover that.

---

## 13. `LAUNCH.md` (skeleton)

A single checklist that maps each `PRD.md §12` Definition-of-Done item to a verification command. Format:

```markdown
- [ ] **Aisha sends a real request, receives PDF in < 30s on 1-bar MTN.**
  Verification: real-device test from a PAU number; record screenshot.

- [ ] **Ibrahim can add a paper from his laptop, queryable in 60s.**
  Verification: `python -m admin.upload pdf ./samples/mth102-har-2022.pdf --year 2022 --semester harmattan`, then `python -m admin.list --year 2022`.

- [ ] **All secrets in Secret Manager. None in repo.**
  Verification: `gcloud secrets list`; `git grep -nE 'WA_ACCESS_TOKEN|DB_PASSWORD|WA_APP_SECRET' -- '*.py' '*.md'` returns nothing.

- [ ] **RUNBOOK.md lets Ibrahim rotate the Meta token unaided.**
  Verification: dry-run by a non-author MSA exec following only RUNBOOK.md §1.

- [ ] **One full month: total GCP bill ≤ $15 post-credits, error rate < 1%.**
  Verification: GCP billing report + `python -m admin.stats --days 30`.
```

Five boxes. They map 1-to-1 with `PRD.md §12`.

---

## 14. Tests

### 14.1 `tests/test_retrieval_retired.py`
- Skipped unless `DATABASE_URL_TEST` is set (consistent with Phase 1 / 2).
- Insert two MTH102 papers for the same year/semester (one with a different `course_code` if uniqueness blocks; otherwise one harmattan + one rain). Mark one `is_retired=TRUE`.
- `find_paper(course="MTH102", year=Y, semester=S)` for the retired one returns None.
- `find_paper` with no filters returns the non-retired one even if the retired is newer.
- Same coverage for `find_paper_by_semantic_query` using deterministic embedding fixtures.

### 14.2 `tests/test_admin_retire.py`
- Run `admin.retire.main` with monkey-patched argv; assert DB state changes (`is_retired=True`, `retired_by`, `retired_at`, `retired_reason`).
- Idempotent: second call exits 0 without re-writing.
- Missing `--reason` → argparse error, exit 2.

### 14.3 `tests/test_pipeline.py` extension
- `test_pipeline_daily_token_budget_blocks`: insert 50 fake `RequestLog` rows in the last 24h whose `flash_input_tokens + flash_output_tokens` sum exceeds `settings.daily_token_budget`. Send a new message with mocked `llm.route`. Assert the reply is the literal "daily limit" text and `outcome="rate_limited"`, `error="daily_token_budget_exceeded"`.

No test for `Makefile`, `RUNBOOK.md`, `LAUNCH.md`, or `scripts/smoke.sh` content. Those are operational artifacts; their correctness is verified by running them on launch day.

---

## 15. Cost model recheck

Phase 3 adds zero new LLM calls. The daily token budget *reduces* spend in pathological cases (a runaway loop or abuse). Steady-state remains ~$9.50/mo per `PRD.md §5.3`.

The `admin.stats` command surfaces actual token consumption; Ibrahim should run it weekly. RUNBOOK.md §1 closing line: "If `admin stats --days 7` shows tokens > 1.4M, something is wrong — open an issue."

---

## 16. Non-goals reaffirmed

The execution agent must **not** add any of the following:

- Drive importer (`scripts/drive_import.py`). V2 candidate.
- `users` / `inferred_courses` / `pending_submissions` / `image_batches` / `image_batch_items` / `message_log` rename.
- Curation review CLI (`admin curate`). The active-risk flag stays informational only.
- Multi-course catalog or any `--course` flag.
- A web UI (admin or otherwise), Slack bot, or any non-WhatsApp channel.
- Cloud Tasks, Pub/Sub, Cloud Scheduler, Eventarc.
- A migration tool (Alembic etc.). Migrations stay hand-applied SQL files.
- Asyncio / FastAPI BackgroundTasks on the request path.
- BM25, hybrid retrieval, RRF, reranking.
- Templated WhatsApp messages of any kind.
- Authentication on the WhatsApp webhook beyond `X-Hub-Signature-256`.
- Anything described in `MASTER_PRD.md` §13 beyond the five admin commands listed in §8 above. (Specifically: no `import-drive`, no `reembed`, no `set-course-active`, no `review-pending`, no `curate`.)

If any of these become tempting, stop and amend `PHASE_3_SPEC.md` first.

---

## 17. Definition of Done (Phase 3)

A maintainer (Ibrahim) on his laptop, freshly cloning the repo:

1. Reads `README.md`. In ≤ 5 minutes can articulate what the system does and what to do when it breaks.
2. Runs `pip install -r requirements.txt`. No errors.
3. Applies `migrations/003_phase3.sql`. `\d papers` shows `is_retired`, `retired_by`, `retired_at`, `retired_reason`. The partial index `papers_active` exists.
4. Runs `python -m admin.list`. Sees the existing live papers.
5. Runs `python -m admin.retire 1 --reason "test retirement" --yes` then `python -m admin.list`. The retired paper no longer appears. Adds `--include-retired` to see it again.
6. Runs `python -m admin.audit --since 2026-05-01`. Sees recent webhook activity in a readable table.
7. Runs `python -m admin.stats --days 7`. Three small tables print.
8. Runs `make deploy`. Cloud Run service updates with secrets bound from Secret Manager.
9. Runs `make smoke`. Prints `SMOKE OK`.
10. Reads `RUNBOOK.md` §1. Performs a dry-run of token rotation in a scratch project without help.
11. Reads `LAUNCH.md`. Every box has a single verification command Ibrahim can run.
12. `pytest -q` passes, including every Phase 3 test in §14.

When all 12 are green, **V1 is launch-ready**. Hand to Hafeedh for soft launch (10 MSA execs) per `MASTER_PRD §16.1`.
