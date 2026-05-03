# PHASE 7 — Technical Spec (Execution Blueprint)

**Source of truth:** `PRD.md` (canonical). `MASTER_PRD.md` is reference-only — its `§12.1` failure catalogue, `§12.2` minimal monitoring, and `§15` Sadaqah Jariyah Durability Checklist drive this phase.
**Audience:** the execution agent that will write the code. Do not deviate without amending this file first.
**Predecessors:** `PHASE_1_SPEC.md` … `PHASE_6_SPEC.md`. All merged.

**Status of master PRD V1.1+ backlog after this phase:**
- V1.1.1 Hybrid BM25/pgvector RRF — **deferred** (pg_bm25 unavailable on Cloud SQL; vector recall has been adequate so far).
- V1.1.2 User photo ingestion — **shipped** in Phase 5.
- V1.1.3 Implicit profile read-side — **shipped** in Phase 6.
- V1.1.4 CAC + Meta business verification — **operational, not code**; tracked in `RUNBOOK.md`.
- V1.2.1 Soft personalization — **shipped** in Phase 6.
- V2.x — **out of scope, permanently** until lecturer feedback authorizes.

Phase 7 is the last code phase before Hafeedh's public launch. Purpose: **make sure nothing surprises Ibrahim in production.**

---

## 0. Phase 7 mission (one sentence)

Add a hard daily *dollar* cost circuit breaker, an end-to-end health-probe admin command, a weekly digest script, structured-field logging, and a backup-restore drill — so that the launch checklist in `LAUNCH.md` becomes literally executable.

---

## 1. Scope (locked)

**In Phase 7:**

1. **Daily $ cost circuit breaker.** Replace the per-day token budget guard with a more accurate per-day estimated *USD* guard. Pulls Flash + Pro + embedding token counts from `request_log` and `pending_papers` activity over the last 24h, multiplies by per-model unit prices declared in config, refuses new LLM calls (with the same `rate_limited` outcome) when the projected day exceeds `daily_cost_usd_cap` (default `0.50`).
2. **Health probe.** `python -m admin.health` runs five sub-checks (DB connect, Vertex Flash ping, GCS bucket head, Meta token validity, embedding probe). Emits a one-line JSON result and exits 0 only if all pass. Used by `RUNBOOK.md §4` and the launch checklist.
3. **Weekly digest.** `python scripts/weekly_digest.py [--days 7] [--out PATH]` produces a Markdown summary identical in spirit to `admin stats` but readable for forwarding: total requests, outcomes breakdown, top-10 courses, top-10 askers (anonymized — last 4 digits only), token spend, $ spend, batches sealed/failed/deferred, papers added, papers retired. Writes to stdout by default; `--out path.md` writes a file Hafeedh can paste into WhatsApp/email.
4. **Structured logging fields.** Every `log.info|warning|error|exception` call in `app/pipeline.py`, `app/main.py`, `app/intake.py`, `app/whatsapp.py` adds a stable `extra` payload with `wa_message_id` (when known), `wa_from` (when known), `course` (when routed), `phase` (one of `request`/`intake`/`webhook`/`sealer`). The existing `JSONFormatter` already promotes `record.__dict__` extras; this phase enforces consistent field names.
5. **Backup restore drill script.** `scripts/restore_drill.sh` — interactive, documented in `RUNBOOK.md §5`. Steps: pick latest Cloud SQL backup, prompt for confirmation, restore to a *new temporary instance* named `paperbank-drill-<date>`, run `migrations/00*_*.sql` against it, run a smoke SELECT count(*) on the three core tables, **prompt before deleting** the temp instance. No code path touches the production instance.
6. **`admin tail` command.** `python -m admin.tail [--minutes 30] [--errors-only]` — prints recent `request_log` and any errors in tabular form; useful for live triage during launch.
7. **`LAUNCH.md` rewrite.** Now lists exactly the commands needed to verify each `PRD.md §12` DoD box. Soft-launch and public-launch sections trim to checklists with command-line verification per item.
8. **Tests** for the cost-cap branch and the digest renderer.

**Out of Phase 7 (do not build):**

- Cloud Monitoring alert wiring (still configured by hand per `PHASE_3_SPEC §1.8`; not generated from code).
- Email/SMS notification dispatch from the digest. The script writes Markdown; Hafeedh forwards manually.
- A web admin UI of any kind.
- Cloud Tasks, Pub/Sub, Cloud Scheduler. The weekly digest runs from Hafeedh's laptop on demand.
- Hybrid BM25 retrieval. Deferred per `MASTER_PRD §14`.
- A new monitoring SaaS (Datadog, NewRelic, etc.).
- Auto-rollback on cost-cap breach. The cap returns text replies; rollback is still a manual `make rollback`.
- A change to the existing `daily_token_budget` guard's removal — the new $ guard *replaces* it (the token guard becomes a fallback floor and is renamed to `daily_token_floor` only in config; behavior is preserved).

---

## 2. Repository layout (delta from Phase 6)

Files added (✦) or modified (∆):

```
msa-paperbank/
├── PHASE_7_SPEC.md             ✦
├── README.md                   ∆ (one paragraph: how to run health/digest)
├── RUNBOOK.md                  ∆ (§4 health, §5 restore drill, §11 cost dashboards)
├── LAUNCH.md                   ∆ (rewritten as a command checklist)
├── Makefile                    ∆ (+health, +digest, +drill targets)
├── requirements.txt            ∆ (no new deps)
├── app/
│   ├── config.py               ∆ (cost settings)
│   ├── pipeline.py             ∆ (replace token guard with $ guard; tighten logging fields)
│   ├── main.py                 ∆ (consistent extras on every log call)
│   ├── whatsapp.py             ∆ (logging fields)
│   ├── intake.py               ∆ (logging fields)
│   └── pricing.py              ✦ (one source of truth for $/1M token rates)
├── admin/
│   ├── health.py               ✦
│   └── tail.py                 ✦
├── scripts/
│   ├── weekly_digest.py        ✦
│   └── restore_drill.sh        ✦
└── tests/
    ├── test_cost_breaker.py    ✦
    └── test_digest_render.py   ✦
```

No other files change. No new migrations.

---

## 3. Pinned dependency additions

None. The digest script uses `tabulate` (already pinned) with the `format="github"` style for Markdown tables.

---

## 4. Schema migration

None. Phase 7 is purely operational and does not touch the schema.

---

## 5. Configuration delta (`app/config.py`)

| Field | Env var | Type | Default |
|---|---|---|---|
| `daily_cost_usd_cap` | `DAILY_COST_USD_CAP` | `float` | `0.50` |
| `daily_token_floor` | `DAILY_TOKEN_FLOOR` | `int` | `200_000` (renamed from `daily_token_budget`; both names accepted via env, with `daily_cost_usd_cap` taking priority when both would trigger) |
| `price_flash_input_per_1m_usd` | `PRICE_FLASH_INPUT_PER_1M_USD` | `float` | `0.50` |
| `price_flash_output_per_1m_usd` | `PRICE_FLASH_OUTPUT_PER_1M_USD` | `float` | `3.00` |
| `price_pro_input_per_1m_usd` | `PRICE_PRO_INPUT_PER_1M_USD` | `float` | `2.00` |
| `price_pro_output_per_1m_usd` | `PRICE_PRO_OUTPUT_PER_1M_USD` | `float` | `12.00` |
| `price_embedding_per_1m_usd` | `PRICE_EMBEDDING_PER_1M_USD` | `float` | `0.05` |

**Backwards-compat note:** `daily_token_budget` is preserved as an alias for `daily_token_floor` in `Settings` via `Field(validation_alias=AliasChoices("daily_token_floor","daily_token_budget"))`. Existing deployments don't break.

---

## 6. Pricing helper (`app/pricing.py`)

Pure functions, no I/O:

```python
def estimate_request_cost_usd(flash_in: int, flash_out: int) -> float: ...
def estimate_pro_cost_usd(pro_in: int, pro_out: int) -> float: ...
def estimate_embedding_cost_usd(emb_tokens: int) -> float: ...

def estimate_daily_spend_usd(session: Session) -> float:
    """Sum the last 24h of activity from request_log + pending_papers + intake.
    Returns total estimated $ across all three model classes.
    Uses settings.price_*_per_1m_usd as the per-1M USD rates.
    Pro / embedding token counts come from a small heuristic — see below.
    """
```

**Heuristic for Pro and embedding token counts** (since we don't store them per-call):
- Each `image_batches.status='ocr_done'` row sealed in the last 24h ≈ 4 image-pages × 1290 input tokens + 500 output tokens ≈ `5660` Pro tokens. Multiply by sealed_count.
- Each `pending_papers` row created via admin `images` upload in the last 24h: count `(course_code, semester, year, exam_session)` insertions in `pending_papers` where `source='cli_images' OR source='wa_intake'`, multiply by the same `5660`.
- Each `paper_chunks` row created in the last 24h ≈ 1 embedding call ≈ `200` embedding tokens. (Phase 4 Drive importer also produces chunks.)

These are bounded over-estimates — the goal is "trip the breaker before it actually hurts," not perfect accuracy.

---

## 7. Pipeline change (`app/pipeline.py`)

Replace step 3b (token budget guard) with:

```python
# 3b. Daily cost circuit breaker (Phase 7).
# Hard $ ceiling, computed from request_log + pending_papers/paper_chunks.
spent_usd = pricing.estimate_daily_spend_usd(session)
if spent_usd >= settings.daily_cost_usd_cap:
    log_entry.outcome = "rate_limited"
    log_entry.error = "daily_cost_cap_exceeded"
    session.commit()
    log.warning("daily_cost_cap_exceeded", extra={
        "wa_from": msg.from_, "phase": "request", "spent_usd": round(spent_usd, 4),
    })
    return _apply_privacy_notice(TextReply(
        body="The bot has hit its daily limit. Try tomorrow morning, in shaa Allah."
    ))

# 3c. Token floor (preserved from Phase 3 as a defense-in-depth lower-cost check)
twenty_four_h_ago = datetime.now(timezone.utc) - timedelta(hours=24)
budget_query = select(
    func.coalesce(func.sum(RequestLog.flash_input_tokens), 0)
    + func.coalesce(func.sum(RequestLog.flash_output_tokens), 0)
).where(RequestLog.received_at >= twenty_four_h_ago)
spent_tok = session.execute(budget_query).scalar_one()
if spent_tok >= settings.daily_token_floor:
    log_entry.outcome = "rate_limited"
    log_entry.error = "daily_token_floor_exceeded"
    session.commit()
    return _apply_privacy_notice(TextReply(
        body="The bot has hit its daily limit. Try tomorrow morning, in shaa Allah."
    ))
```

Both branches use the existing `rate_limited` outcome — no new outcome strings.

---

## 8. Logging field standard

Every `log.X(...)` call gains an `extra={...}` with these keys when applicable:

| Key | When |
|---|---|
| `phase` | Always — one of `request`, `intake`, `webhook`, `sealer`, `admin` |
| `wa_message_id` | When the call is downstream of message parsing |
| `wa_from` | When known |
| `course` | When the router has resolved a course |
| `outcome` | When a final outcome is set |
| `cost_estimate_usd` | When the cost breaker logs |

The `JSONFormatter` from `PHASE_1_SPEC §4` already promotes record extras to top-level JSON keys; no formatter change needed.

The execution agent must edit at minimum:
- `app/pipeline.py`: every `log.exception/warning/info` call.
- `app/main.py`: `invalid_payload`, `handle_message_failed`, `failed_to_send_notification`, `flush_notifications_failed`.
- `app/intake.py`: `image_from_non_whitelisted`, `handle_image_error`, `sweep_and_seal_batch_failed`, `batch_processing_error`.

Existing log calls that already pass extras keep them; just *add* the missing fields — do not remove anything.

---

## 9. Health probe (`admin/health.py`)

Run exactly five sub-checks, in this order. Each returns `(name, ok: bool, ms: int, detail: str)`. The command writes one JSON line to stdout summarizing all results, exits 0 iff every check passed.

1. `db`: open a `SessionLocal()`, run `SELECT 1`. Time the call.
2. `gcs`: `gcs_client.bucket(settings.gcs_bucket).exists()` (a HEAD via the SDK).
3. `vertex_flash`: send a 1-token ping via `client.models.generate_content(model=settings.model_flash, contents="ping", config=GenerateContentConfig(max_output_tokens=4))`. Don't validate the body; the call returning successfully is the success criterion.
4. `vertex_embedding`: `client.models.embed_content(model=settings.model_embedding, contents="ping", config=EmbedContentConfig(output_dimensionality=settings.embedding_dim))`.
5. `meta`: `httpx.get(f"https://graph.facebook.com/{settings.wa_graph_version}/{settings.wa_phone_number_id}", headers={"Authorization": f"Bearer {settings.wa_access_token.get_secret_value()}"})`. 200 = pass.

JSON output shape:

```json
{"overall":"PASS","ms":1234,"checks":[
  {"name":"db","ok":true,"ms":12,"detail":"ok"},
  {"name":"gcs","ok":true,"ms":34,"detail":"bucket=msa-paperbank-pdfs-..."},
  {"name":"vertex_flash","ok":true,"ms":420,"detail":"model=gemini-3-flash-preview"},
  {"name":"vertex_embedding","ok":true,"ms":210,"detail":"dim=768"},
  {"name":"meta","ok":true,"ms":160,"detail":"phone_number_id=..."}
]}
```

Exit codes: `0` overall PASS, `1` any FAIL.

`Makefile` adds:

```
health:
	python -m admin.health
```

---

## 10. Weekly digest (`scripts/weekly_digest.py`)

Argparse: `--days 7`, `--out PATH`. Default writes to stdout.

Sections (Markdown headings + tables):

1. **Window**: `start_at`, `end_at`, `days`.
2. **Activity**: total requests, distinct phones, sent/not_found/error/rate_limited counts.
3. **Top 10 courses requested** (group by `routed_course` where `outcome='sent'`).
4. **Top 10 askers** — masked: `phone[:-4] + 'XXXX'` so the digest is shareable.
5. **Spend** — total tokens (Flash in/out, Pro est., embedding est.) and the $ from `pricing.estimate_daily_spend_usd` summed across the window.
6. **Intake** — batches opened / sealed / failed / deferred_ocr in the window.
7. **Library** — total active papers, papers added in window, papers retired in window.
8. **Health** — `python -m admin.health` JSON, embedded inline.

`Makefile` adds:

```
digest:
	python scripts/weekly_digest.py --out weekly_$$(date +%Y-%m-%d).md
```

---

## 11. Backup restore drill (`scripts/restore_drill.sh`)

Bash, `set -euo pipefail`, **interactive only** (do not run in CI). Steps:

1. Print `WARNING: this creates a temporary Cloud SQL instance and restores the latest backup into it. The production instance is NOT touched.` Prompt `Continue? [yes/N]`.
2. `gcloud sql backups list --instance paperbank --filter='status=SUCCESSFUL' --sort-by=~window_start_time --limit=1 --format=json` → parse latest backup id.
3. `gcloud sql instances create paperbank-drill-$(date +%Y%m%d-%H%M) --database-version=POSTGRES_16 --tier=db-f1-micro --region=$REGION`.
4. `gcloud sql backups restore <id> --restore-instance=<temp> --backup-instance=paperbank`.
5. Connect via Cloud SQL Auth Proxy, run all migrations in order, then `SELECT count(*) FROM papers, paper_chunks, courses, request_log` — print results.
6. Prompt `Drill complete. Delete temp instance <name>? [yes/N]`. On yes: `gcloud sql instances delete <name> --quiet`. On no: print `LEFT INTACT — remember to delete manually with: gcloud sql instances delete <name> --quiet`.

Documented in `RUNBOOK.md §5`. Run quarterly per `MASTER_PRD §15.D5`.

---

## 12. `admin tail` (`admin/tail.py`)

Argparse: `--minutes 30`, `--errors-only`, `--limit 50`.

```
python -m admin.tail [--minutes 30] [--errors-only] [--limit 50]
```

Behavior:
- Selects `request_log` rows in the window, ordered `received_at DESC`.
- `--errors-only` filters `outcome IN ('error','rate_limited')`.
- Renders a `tabulate` grid: `received_at, wa_from (last 4 only), outcome, routed_course, error`.

`Makefile` adds:

```
tail:
	python -m admin.tail --minutes 60
```

---

## 13. Tests

### 13.1 `tests/test_cost_breaker.py`
- Insert one `RequestLog` with `flash_input_tokens=400_000, flash_output_tokens=200_000` in the last 24h (≈ $0.80). Set `daily_cost_usd_cap=0.50`.
- Send a new message via `pipeline.handle_message`. Assert reply is the daily-limit text and `RequestLog.outcome="rate_limited"`, `error="daily_cost_cap_exceeded"`.
- Repeat with cap raised to `2.00`. Assert the request proceeds (mock `llm.route`).

### 13.2 `tests/test_digest_render.py`
- Seed a small `request_log` with diverse outcomes and one sealed `image_batch`.
- Run `weekly_digest.py --days 7 --out tmp.md`. Assert file exists, contains every section heading, contains masked phone numbers (no full E.164), and contains a non-empty health block.

No tests for the restore drill (manual operation).

---

## 14. RUNBOOK / README updates

### `RUNBOOK.md`
- New §11: **Cost dashboards.** "Run `make digest` weekly. The `Spend` section is the truth; if it trends > $2/day for 3+ days, raise the cost cap deliberately or open an issue."
- §4 (silent bot triage) gains: "First step: `python -m admin.health`. If anything is FAIL, that's your symptom."
- §5 (restore from backup): now references `scripts/restore_drill.sh` for the dry-run path; the destructive in-place path stays in §5 with a clear warning.

### `README.md`
- "Daily ops" section: add `make health`, `make digest`, `make tail`.
- "Privacy" section unchanged from Phase 6.

### `LAUNCH.md`
Rewritten as a pure checklist where every box has exactly one verification command:

```markdown
- [ ] **All secrets in Secret Manager. None in repo.**
  Verify: `gcloud secrets list && git grep -nE 'WA_ACCESS_TOKEN|DB_PASSWORD|WA_APP_SECRET' -- '*.py' '*.md' | grep -v EXAMPLE`

- [ ] **Health probe green.**
  Verify: `make health`

- [ ] **End-to-end retrieval works on weak signal.**
  Verify: real-device test, screenshot, attach to launch issue.

- [ ] **Backup restore drill executed within the last 90 days.**
  Verify: `scripts/restore_drill.sh` produced a successful run, log saved.

- [ ] **Cost cap configured and tested.**
  Verify: temporarily set DAILY_COST_USD_CAP=0.0001, send a request, see "daily limit" reply; reset.

- [ ] **Token rotation rehearsed.**
  Verify: a non-author MSA exec performed RUNBOOK.md §1 end-to-end in a scratch project.
```

---

## 15. Cost recheck

Phase 7 adds **zero LLM calls** to the request path. The cost breaker *reduces* worst-case spend.

The health probe makes 2 small Vertex calls per invocation (~2 cents at $0.50/1M Flash + $0.05/1M embedding). At one health probe per hour during launch monitoring, that's <$0.50/month — well within ceiling.

---

## 16. Non-goals reaffirmed

The execution agent must **not** add any of the following:

- Cloud Tasks, Pub/Sub, Cloud Scheduler, Eventarc, Workflows.
- A web admin UI.
- LLM-driven recommendations / mentor / summarisation.
- A third-party monitoring SaaS.
- Email / SMS dispatch from the digest script.
- An auto-rollback on cost-cap breach.
- A migration tool. Migrations stay hand-applied SQL.
- Hybrid BM25 retrieval. Deferred.
- Removal of `daily_token_floor` — it stays as a defense-in-depth fallback.
- Anything described in `MASTER_PRD §14` V2 column.

If any become tempting, stop and amend `PHASE_7_SPEC.md` first.

---

## 17. Definition of Done (Phase 7)

A maintainer (Hafeedh or Ibrahim) on his laptop:

1. Pulls `master`, `pip install -r requirements.txt`. No errors.
2. Runs `make health`. JSON line printed; overall PASS; exit 0.
3. Sets `DAILY_COST_USD_CAP=0.0001`, sends one webhook, receives the daily-limit text. Resets cap.
4. Runs `make digest`. A `weekly_<date>.md` file appears with all 8 sections populated and phone numbers masked.
5. Runs `scripts/restore_drill.sh` in a sandbox project. Prompts walk to completion; temp instance is created, migrated, queried, and deleted on confirmation.
6. Runs `make tail --minutes 60` (via `python -m admin.tail`). Recent activity prints with masked phones.
7. `pytest -q` passes including every Phase 7 test in §13.
8. `make smoke` still prints `SMOKE OK`.
9. Every box in `LAUNCH.md` has been ticked on a real environment by following its `Verify:` command.
10. Total monthly cost remains ≤ $15 with the cost cap active.

When all 10 are green, Phase 7 is complete and `msa-paperbank` is **public-launch ready** per `MASTER_PRD §16.2`.
