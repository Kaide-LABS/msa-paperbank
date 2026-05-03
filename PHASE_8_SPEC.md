# PHASE 8 — Technical Spec (Execution Blueprint)

**Source of truth:** `PRD.md` (canonical). `MASTER_PRD.md` is reference-only — this phase implements the *spirit* of `§10 Academic Integrity Policy` items AI-5 ("Lecturer-flagged retraction") and AI-6 ("audit"), and `§15.D5` (durability — offsite backups), without touching any V2 feature.
**Audience:** the execution agent that will write the code. Do not deviate without amending this file first.
**Predecessors:** `PHASE_1_SPEC.md` … `PHASE_7_SPEC.md`. All merged. The bot is public-launched.

**V2 features remain forbidden** until lecturer feedback authorizes (per `MASTER_PRD §14`): no AI summarisation, no practice mode, no mentor of any kind, no community templates. **This phase is the only sanctioned *new* surface for the foreseeable future** — a one-way channel that lets PAU lecturers flag papers for review without giving them DB access, plus a true-offsite weekly backup so the corpus survives even a GCP project loss.

---

## 0. Phase 8 mission (one sentence)

Give PAU lecturers a WhatsApp-native, one-way **flag** channel ("a lecturer texted us 'CSC305 2024 has been republished verbatim — pull it'"); fan-in those flags into an `admin flags` review queue that translates approved flags into the existing `admin retire` action; and ship a synchronous, off-GCP `weekly_offsite_backup` dump that lives on Hafeedh's laptop / a separate-org GCS bucket so the system survives a project compromise.

---

## 1. Scope (locked)

**In Phase 8:**

1. **`lecturers` table.** Whitelist of phone numbers (E.164, no `+`) authorised to submit flags. Same shape as `uploaders` from Phase 5: `display_name`, `department`, `added_by`, `added_at`, `revoked_at`, `revoke_reason`.
2. **Admin CLI `admin lecturers {add,revoke,list}`.** Same UX patterns as `admin uploaders`.
3. **`lecturer_flags` table.** One row per flag, statuses: `open` | `reviewed` | `actioned` | `dismissed`. Carries `paper_id`, `course_code`, `year`, `semester`, `exam_session` (last four nullable when the lecturer is reporting a paper that's not in the DB yet), `reason TEXT`, `lecturer_phone`, `created_at`, plus the standard reviewer/reviewed_at/action_notes fields.
4. **Pipeline branch for lecturer numbers.** When an inbound text comes from a phone in `lecturers` (active row), bypass the LLM router entirely and parse the body as a **structured flag**:
   - Format: `FLAG <COURSE> <YEAR> <reason text>` — e.g., `FLAG CSC305 2024 republished CA1 verbatim`.
   - Anything else from a lecturer number gets a single, polite reply explaining the format. **No LLM call ever happens on the lecturer path** (cost-free; fast).
5. **Flag confirmation reply.** On a parsed flag, insert one `lecturer_flags` row, reply to the lecturer with the flag id and a short ack: `"Flag #1234 received. Hafeedh will review CSC305/2024 and reply when actioned."`
6. **`admin flags {list,review,dismiss,action}` CLI.** Paginated review with the same transcript shape as `admin curate`. `action <id>` translates an approved flag into a `python -m admin.retire <paper_id> --reason "<flag reason via lecturer X>"` run, but with `--yes` already set (admin's `action` IS the confirmation). After successful retire, write a `lecturer_messages` row + an `intake_notifications` row so the lecturer is informed via the existing flush path.
7. **Offsite backup script `scripts/offsite_backup.py`.** Synchronous, run from Hafeedh's laptop weekly via `make offsite-backup`. Exports: full `courses`, `papers` (active + retired), `paper_chunks` (without embeddings unless `--include-embeddings`), `uploaders`, `lecturers`, `lecturer_flags`, plus a sample of recent `request_log` (last 30 days, masked). Output: a single `.tar.gz` containing JSON files (one per table) and a SHA-256 manifest. Optional `--gcs gs://OTHER-ORG/path/` uploads to a *different* GCP project bucket; default writes to `./offsite/<YYYY-MM-DD>.tar.gz`.
8. **Tests** for the lecturer-FLAG parser, the `lecturers` whitelist gate, the `admin flags action` → retire integration, and the offsite backup tar contents.

**Out of Phase 8 (do not build):**

- Lecturer-initiated **retire** in one step. Lecturers FLAG; only admin retires. (Trust boundary; one-way channel.)
- Free-form lecturer chat / Q&A. The lecturer parser is strict; non-FLAG messages get a help reply.
- A lecturer-facing reply for in-progress reviews. The single `intake_notifications` ping at action time is enough.
- Cloud Tasks / Pub/Sub / Cloud Scheduler. Offsite backup is a manual `make offsite-backup`.
- A web admin UI.
- Any V2 feature (summarisation, practice mode, mentor).
- Multi-language replies (Yoruba/Hausa). English remains the only language.
- Encryption at rest of the offsite tarball (it's already from a GCP-encrypted DB; admin handles physical safety).
- A flag-rate-limit per lecturer. Flags are inherently low-volume; abuse can be handled by `admin lecturers revoke`.

---

## 2. Repository layout (delta from Phase 7)

Files added (✦) or modified (∆):

```
msa-paperbank/
├── PHASE_8_SPEC.md             ✦
├── README.md                   ∆ (one paragraph: lecturer FLAG channel + offsite backup)
├── RUNBOOK.md                  ∆ (§12 lecturer onboarding, §13 offsite drill)
├── Makefile                    ∆ (+offsite-backup target)
├── requirements.txt            ∆ (no new deps)
├── app/
│   ├── config.py               ∆ (one new setting)
│   ├── db.py                   ∆ (Lecturer, LecturerFlag)
│   ├── lectures.py             ✦  (parser + handle_lecturer_message)
│   └── pipeline.py             ∆ (branch-on-lecturer before any LLM call)
├── admin/
│   ├── lecturers.py            ✦
│   └── flags.py                ✦
├── scripts/
│   └── offsite_backup.py       ✦
├── migrations/
│   └── 007_phase8.sql          ✦
└── tests/
    ├── test_lecturer_parser.py     ✦
    ├── test_lecturer_pipeline.py   ✦
    ├── test_admin_flags.py         ✦
    └── test_offsite_backup.py      ✦
```

No other files change.

---

## 3. Pinned dependency additions

None.

---

## 4. Schema migration (`migrations/007_phase8.sql`)

Run order: must be applied after `006_phase6.sql`.

```sql
CREATE TABLE IF NOT EXISTS lecturers (
    phone_number TEXT PRIMARY KEY,
    display_name TEXT NULL,
    department TEXT NULL,
    added_by TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ NULL,
    revoke_reason TEXT NULL
);
CREATE INDEX IF NOT EXISTS lecturers_active ON lecturers (phone_number) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS lecturer_flags (
    id BIGSERIAL PRIMARY KEY,
    lecturer_phone TEXT NOT NULL REFERENCES lecturers(phone_number),
    paper_id BIGINT NULL REFERENCES papers(id) ON DELETE SET NULL,
    course_code TEXT NULL,
    year INT NULL,
    semester TEXT NULL,
    exam_session TEXT NULL,
    reason TEXT NOT NULL,
    raw_text TEXT NOT NULL,                          -- the original WA body for audit
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN (
        'open', 'reviewed', 'actioned', 'dismissed'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewer TEXT NULL,
    reviewed_at TIMESTAMPTZ NULL,
    action_notes TEXT NULL
);
CREATE INDEX IF NOT EXISTS lecturer_flags_open ON lecturer_flags (created_at DESC) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS lecturer_flags_paper ON lecturer_flags (paper_id) WHERE paper_id IS NOT NULL;
```

No backfill.

---

## 5. Configuration delta (`app/config.py`)

| Field | Env var | Type | Default |
|---|---|---|---|
| `lecturer_flag_format_help` | `LECTURER_FLAG_FORMAT_HELP` | `str` | `"To flag a paper, send: FLAG <COURSE> <YEAR> <reason>. Example: FLAG CSC305 2024 republished CA1 verbatim. Hafeedh will review."` |

No other settings change.

---

## 6. Lecturer parser & handler (`app/lectures.py`)

Pure-Python helpers; **no LLM, no external calls**.

```python
import re
from dataclasses import dataclass
from sqlalchemy.orm import Session
from app.db import Lecturer, LecturerFlag, Paper
from app.schemas import WAMessage, TextReply
from app.config import settings

FLAG_REGEX = re.compile(
    r"^FLAG\s+(?P<course>[A-Z]{2,4}[0-9]{2,3})\s+(?P<year>[12][0-9]{3})\s+(?P<reason>.{3,500})$",
    re.IGNORECASE,
)

@dataclass
class ParsedFlag:
    course_code: str
    year: int
    reason: str

def is_lecturer(session: Session, phone: str) -> bool: ...
    # SELECT 1 FROM lecturers WHERE phone_number=:phone AND revoked_at IS NULL.

def parse_flag(body: str) -> ParsedFlag | None:
    m = FLAG_REGEX.match(body.strip())
    if not m:
        return None
    return ParsedFlag(
        course_code=m["course"].upper(),
        year=int(m["year"]),
        reason=m["reason"].strip(),
    )

def handle_lecturer_message(session: Session, msg: WAMessage) -> TextReply:
    """Bypasses the LLM. Either inserts a lecturer_flag row or returns help text."""
    body = (msg.text.body if msg.text else "").strip()
    parsed = parse_flag(body)
    if parsed is None:
        return TextReply(body=settings.lecturer_flag_format_help)

    # Best-effort paper resolution (active + retired both)
    paper_id = session.execute(
        select(Paper.id)
        .where(Paper.course_code.ilike(parsed.course_code))
        .where(Paper.year == parsed.year)
        .order_by(Paper.uploaded_at.desc())
        .limit(1)
    ).scalar()

    flag = LecturerFlag(
        lecturer_phone=msg.from_,
        paper_id=paper_id,
        course_code=parsed.course_code,
        year=parsed.year,
        reason=parsed.reason,
        raw_text=body,
    )
    session.add(flag)
    session.commit()

    return TextReply(body=(
        f"Flag #{flag.id} received. Hafeedh will review {parsed.course_code}/{parsed.year} "
        f"and reply when actioned."
    ))
```

`is_lecturer` is **not** cached (admin add/revoke must take effect immediately, like Phase 5's `is_whitelisted`).

---

## 7. Pipeline change (`app/pipeline.py`)

Insert a new step **0.5**, between step 0 (opt-out) and step 1 (idempotency). The lecturer branch must run *before* any LLM call but *after* the opt-out branch (so a lecturer who's also opted out can still wipe their data).

```python
# 0.5. Lecturer flag channel (Phase 8) — bypasses the LLM entirely.
if msg.type == "text" and lectures.is_lecturer(session, msg.from_):
    log_entry = RequestLog(
        wa_message_id=msg.id, wa_from=msg.from_,
        user_text=msg.text.body if msg.text else "",
        outcome="lecturer_flag",
    )
    session.add(log_entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DuplicateMessage()
    return lectures.handle_lecturer_message(session, msg)
```

`outcome="lecturer_flag"` is the only new outcome string.

`from app import lectures` is added to the imports at the top of `pipeline.py`.

The privacy-notice helper is **not** applied to lecturer replies (lecturers are by definition not anonymous askers; the notice doesn't fit).

---

## 8. Admin commands

### 8.1 `admin/lecturers.py`

```
python -m admin.lecturers add <PHONE> [--name "Dr. Adebayo"] [--department CSC]
python -m admin.lecturers revoke <PHONE> --reason "<text>" [--yes]
python -m admin.lecturers list [--include-revoked] [--csv PATH]
```

Same UX as `admin uploaders`. Insert with `added_by=os.environ.get("USER","ibrahim")`.

### 8.2 `admin/flags.py`

```
python -m admin.flags list [--status STATUS] [--limit 50] [--csv PATH]
python -m admin.flags review <FLAG_ID>
python -m admin.flags dismiss <FLAG_ID> --reason "<text>" [--yes]
python -m admin.flags action <FLAG_ID> [--yes]
```

- `list`: `tabulate` grid with `id, lecturer_phone (last-4 only), course_code, year, paper_id, status, created_at, reason (first 60 chars)`. Default excludes `actioned` and `dismissed`.
- `review <id>`: prints the full flag + the resolved Paper (if any) + the lecturer's display name. Marks status `reviewed`, `reviewer`, `reviewed_at`. Used to indicate "Hafeedh has read this".
- `dismiss <id>`: terminal state; reason required. Inserts an `intake_notifications` row to ping the lecturer with `"Flag #<id> dismissed: <reason>"`.
- `action <id>`: prompts unless `--yes`. Resolves the paper (must exist; if `flag.paper_id IS NULL`, exit with "no paper resolved — use admin retire manually"). Calls into the same code path as `python -m admin.retire`: `paper.is_retired=True`, `retired_by=lecturer:<phone-last-4>`, `retired_reason=f"flag #{id}: {flag.reason}"`. Marks flag `actioned`. Inserts `intake_notifications` row pinging the lecturer with `"Flag #<id> actioned — paper {course}/{year} retired."`.

The retire-integration deliberately reuses `paper.is_retired = True` directly inside this command (rather than spawning `admin.retire` as a subprocess) so the transaction stays atomic.

---

## 9. Offsite backup (`scripts/offsite_backup.py`)

Synchronous, idempotent, runs from Hafeedh's laptop on demand.

```
python scripts/offsite_backup.py [--out-dir ./offsite] [--include-embeddings] [--gcs gs://other-bucket/path/]
```

Implementation contract:

1. Open `SessionLocal()`.
2. For each table in this fixed list, `SELECT *` and serialize rows to a JSON-lines file:
   - `courses`, `papers`, `paper_chunks` (omit `embedding` column unless `--include-embeddings`), `uploaders`, `lecturers`, `lecturer_flags`, plus `request_log_recent.jsonl` containing the last 30 days of `request_log` with `wa_from` masked to last-4 only.
3. Write a `manifest.json` containing per-file SHA-256 + row counts + timestamp.
4. `tar -czf <out-dir>/<YYYY-MM-DD>.tar.gz` over the temp dir; clean up the temp dir.
5. If `--gcs` set: `gcs_client.bucket(<bucket>).blob(<path>+filename).upload_from_filename(...)`. Use a **second** GCP project's bucket so a single-project compromise doesn't lose the backup. Document in RUNBOOK.
6. Print final path + size + manifest summary.

`Makefile` adds:

```
offsite-backup:
	python scripts/offsite_backup.py --out-dir ./offsite
```

The "weekly" cadence is a documented expectation in `RUNBOOK.md §13`, not a cron job. Hafeedh literally types `make offsite-backup` every Friday after Jumu'ah.

---

## 10. Tests

### 10.1 `tests/test_lecturer_parser.py`
- `parse_flag("FLAG CSC305 2024 republished CA1 verbatim")` → `ParsedFlag(course="CSC305", year=2024, reason="republished CA1 verbatim")`.
- `parse_flag("flag csc305 2024 ok")` → uppercases course (`"CSC305"`).
- `parse_flag("hello")` → `None`.
- `parse_flag("FLAG CSC305 1899 too old")` → `None` (year regex enforces `[12][0-9]{3}`).
- `parse_flag("FLAG CSC305 2024 ab")` → `None` (reason regex enforces `.{3,500}`).

### 10.2 `tests/test_lecturer_pipeline.py`
- Insert a lecturer row for `2348131111111`. Mock `llm.route` so test fails loudly if it's called.
- Send `WAMessage(text="FLAG MTH102 2022 typo in Q3")` from that phone. Assert reply is the ack containing `"Flag #"`, that `lecturer_flags` has one row, that LLM was not called, that `RequestLog.outcome="lecturer_flag"`.
- Same lecturer sends `"hello"` → reply is the help text; no `lecturer_flags` row created.
- Non-lecturer phone sends `"FLAG MTH102 2022 ..."` → goes through the normal pipeline; `llm.route` is called.

### 10.3 `tests/test_admin_flags.py`
- Insert one Paper, one Lecturer, one open `LecturerFlag` resolved to that paper.
- Run `admin.flags.action` (monkey-patched argv, `--yes`). Assert the Paper row is now `is_retired=True`, the flag is `actioned`, and an `intake_notifications` row was created with the lecturer's phone.
- `admin.flags.dismiss` flips status to `dismissed` and writes a notification.

### 10.4 `tests/test_offsite_backup.py`
- Seed minimal data across all 7 exported tables.
- Run `offsite_backup.py --out-dir tmp`. Assert a `.tar.gz` exists; extract; assert the 7 expected `.jsonl` files + a `manifest.json` are present; the manifest's per-file SHA-256 matches the actual file contents.

---

## 11. RUNBOOK / README updates

### `RUNBOOK.md`
- New §12: **Lecturer onboarding.** Three steps: add to `lecturers` table; share the bot's WhatsApp number; share the FLAG format card. One paragraph each.
- New §13: **Offsite backup drill.** Weekly `make offsite-backup`. Quarterly: copy the latest `.tar.gz` to a non-GCP location (an MSA exec's laptop, an external drive). The point is durability against an entire-project loss.

### `README.md`
- "Daily ops" section gains: `make offsite-backup` (weekly), `python -m admin.flags list` (whenever a lecturer texts).
- "Privacy" section unchanged.

---

## 12. Cost recheck

Phase 8 adds **zero LLM calls**. The lecturer branch *removes* an LLM call per lecturer message (router would otherwise fire). Steady-state monthly cost stays at ~$9.50.

The offsite backup downloads chunked rows over local network from Cloud SQL via the proxy; egress to a *non-GCP* destination would charge ~$0.12/GB. With ~5 MB JSONL/week, that's negligible.

---

## 13. Non-goals reaffirmed

The execution agent must **not** add any of the following:

- Lecturer-initiated retire in one step. Two-stage flag-then-action stays.
- Free-form chat with lecturers. Strict parser only.
- Cloud Tasks, Pub/Sub, Cloud Scheduler. Offsite backup is manual.
- A web admin UI.
- Auto-translation of replies.
- Encryption at rest beyond what GCP/Cloud SQL/GCS already provide.
- Any V2 feature.
- A migration tool.
- Caching of `is_lecturer` results.
- A separate "lecturer_users" with `inferred_courses` — lecturers are not subject to the Phase-6 personalization layer.

If any become tempting, stop and amend `PHASE_8_SPEC.md` first.

---

## 14. Definition of Done (Phase 8)

A maintainer (Hafeedh or Ibrahim) on his laptop:

1. Pulls `master`, `pip install -r requirements.txt`. No errors.
2. Applies `migrations/007_phase8.sql`. `\d lecturers`, `\d lecturer_flags` exist with the indexes.
3. Runs `python -m admin.lecturers add 2348131111111 --name "Dr. Adebayo" --department CSC`. `python -m admin.lecturers list` shows the row.
4. From that phone, sends `"FLAG CSC305 2024 republished CA1 verbatim"`. Bot replies `"Flag #1 received. Hafeedh will review..."`.
5. Sends `"hello"` from the same phone. Receives the format-help text.
6. Sends `"FLAG ..."` from a non-lecturer phone. Goes through the normal LLM pipeline; no `lecturer_flags` row.
7. Runs `python -m admin.flags list`. Sees flag #1 open. `python -m admin.flags review 1` then `python -m admin.flags action 1 --yes`. The CSC305/2024 paper is now `is_retired=TRUE`. Within seconds of the next webhook, the lecturer receives `"Flag #1 actioned — paper CSC305/2024 retired."`.
8. Runs `make offsite-backup`. A new `.tar.gz` appears in `./offsite/`. Extracting shows 7 JSONL files + `manifest.json` with matching SHA-256s.
9. `pytest -q` passes including every Phase 8 test in §10.
10. `make smoke` and `make health` still print/return PASS.
11. Total monthly cost remains ≤ $15.

When all 11 are green, Phase 8 is implementation-complete. After this point, **do not propose new feature phases** without explicit written sign-off from Hafeedh and an MSA exec — the V2 firewall stays up.
