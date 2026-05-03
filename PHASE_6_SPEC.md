# PHASE 6 — Technical Spec (Execution Blueprint)

**Source of truth:** `PRD.md` (canonical). `MASTER_PRD.md` is reference-only; this phase consumes its `§4.4` (implicit profile inference, write side already shipped in spirit) plus the V1.1.3 (read-side) and V1.2.1 (soft personalization prefix) backlog items in `§14`.
**Audience:** the execution agent that will write the code. Do not deviate without amending this file first.
**Predecessors:** `PHASE_1_SPEC.md` … `PHASE_5_SPEC.md`. All merged.

---

## 0. Phase 6 mission (one sentence)

Quietly learn which courses each phone number cares about (write-side), use that signal to break ties when retrieval is ambiguous (read-side), prefix the reply with a one-line affordance when we did so — and give every user a documented, **immediate**, no-LLM-needed way to opt out and erase their data.

---

## 1. Scope (locked)

**In Phase 6:**

1. **`users` table.** `phone_number TEXT PRIMARY KEY`, `inferred_courses JSONB DEFAULT '{}'`, `interaction_count INT DEFAULT 0`, `created_at`, `last_seen_at`, `opted_out_at TIMESTAMPTZ NULL`. **`user_tombstones`** table to prevent re-creation post-opt-out.
2. **Write-side inference.** On every successful `paper_request` retrieval (any path), increment `inferred_courses[matched_course]` by 1 and bump `interaction_count` + `last_seen_at` for the sender's phone. **Skipped** when the phone is opted-out or tombstoned. **No** LLM call. **No** new outbound message.
3. **Opt-out keywords.** Before any LLM router call, if `msg.text.body` (uppercased, whitespace-stripped) matches one of `STOP TRACKING` | `STOP TRACKING ME` | `OPT OUT` | `DELETE MY DATA` | `FORGET ME`: hard-delete the `users` row, insert into `user_tombstones`, reply `"Got it — I've forgotten you. Your data is wiped. Send any message later to start fresh (this clears the opt-out)."`. Set `RequestLog.outcome="opted_out"`. **Opt-in re-engagement** is automatic on the next non-opt-out message: if a tombstone exists for the phone, delete the tombstone and proceed normally; the user will be re-profiled from scratch.
4. **Read-side tiebreaker.** When `find_paper_by_semantic_query` is invoked and the user has at least one inferred course, pass the user's top-2 courses as a `prefer_courses` argument; the SQL re-orders ties (cosine distance within `personalization_tie_band`, default `0.05`) by whether the candidate's `course_code` is in that set. Effect: small bias, never a hard filter.
5. **Soft personalization prefix.** When the final retrieved paper's `course_code` matches the user's `inferred_courses`'s top key (and `interaction_count >= personalization_min_interactions`, default `5`), prefix the caption with `"Prioritising your courses — "`. Otherwise the caption is unchanged.
6. **Privacy-notice text.** New first-time-user reply: when a phone has `interaction_count == 0` AND no tombstone, append a one-time line to whatever reply we send: `"\n\n(Tip: I learn which courses you ask about to rank results. Send 'STOP TRACKING' anytime to wipe my notes.)"`. Track delivery via `users.privacy_notice_sent_at`.
7. **Admin commands.** `python -m admin.users {get,list,reset,export}`.
8. **Tests** for opt-out flow, write-side increment, tiebreaker, and privacy-notice once-only behavior.

**Out of Phase 6 (do not build):**

- Reading inferred_courses to *generate* arbitrary recommendations ("you might also like…"). This is V2 mentor territory.
- Storing message bodies past `request_log` (no chat history mining beyond what's already there).
- A separate consent table or interactive opt-in flow. The privacy notice + opt-out keyword is the entire UX.
- Email / SMS notifications about data. Everything stays inside the WhatsApp thread.
- Any external analytics destination (no BigQuery, no Mixpanel, etc.).
- A web profile dashboard.
- LLM-driven inference on user state (no Pro/Flash calls beyond the existing router).
- Re-ranking the *primary* ILIKE result. The tiebreaker only fires inside the semantic-fallback path.

---

## 2. Repository layout (delta from Phase 5)

Files added (✦) or modified (∆):

```
msa-paperbank/
├── PHASE_6_SPEC.md             ✦
├── README.md                   ∆ (one-paragraph privacy section)
├── RUNBOOK.md                  ∆ (opt-out FAQ, admin users commands)
├── requirements.txt            ∆ (no new deps)
├── app/
│   ├── config.py               ∆ (3 new settings)
│   ├── db.py                   ∆ (User, UserTombstone)
│   ├── retrieval.py            ∆ (find_paper_by_semantic_query gains prefer_courses)
│   ├── pipeline.py             ∆ (opt-out keyword branch + write-side increment + privacy notice)
│   └── profile.py              ✦
├── admin/
│   └── users.py                ✦
├── migrations/
│   └── 006_phase6.sql          ✦
└── tests/
    ├── test_profile.py             ✦
    ├── test_opt_out.py             ✦
    ├── test_personalization.py     ✦
    └── test_pipeline.py            ∆ (new: privacy notice once-only)
```

No other files change.

---

## 3. Pinned dependency additions

None. `JSONB` access uses SQLAlchemy's existing `JSONB` import from `sqlalchemy.dialects.postgresql`.

---

## 4. Schema migration (`migrations/006_phase6.sql`)

Run order: must be applied after `005_phase5.sql`.

```sql
CREATE TABLE IF NOT EXISTS users (
    phone_number TEXT PRIMARY KEY,
    inferred_courses JSONB NOT NULL DEFAULT '{}'::jsonb,
    interaction_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    privacy_notice_sent_at TIMESTAMPTZ NULL,
    opted_out_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS users_last_seen ON users (last_seen_at DESC);

CREATE TABLE IF NOT EXISTS user_tombstones (
    phone_number TEXT PRIMARY KEY,
    opted_out_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_keyword TEXT NULL
);
```

No backfill. Existing senders with prior `request_log` entries do not get a `users` row until they next send a message.

---

## 5. Configuration delta (`app/config.py`)

Add the following fields. All have defaults.

| Field | Env var | Type | Default |
|---|---|---|---|
| `personalization_min_interactions` | `PERSONALIZATION_MIN_INTERACTIONS` | `int` | `5` |
| `personalization_tie_band` | `PERSONALIZATION_TIE_BAND` | `float` | `0.05` |
| `personalization_top_k_for_bias` | `PERSONALIZATION_TOP_K_FOR_BIAS` | `int` | `2` |

---

## 6. Profile module (`app/profile.py`)

Pure SQL helpers, no LLM, no external calls.

```python
OPT_OUT_KEYWORDS: frozenset[str] = frozenset({
    "STOP TRACKING", "STOP TRACKING ME", "OPT OUT",
    "DELETE MY DATA", "FORGET ME",
})

def is_opt_out_message(text: str) -> bool: ...
    # text.upper().strip() in OPT_OUT_KEYWORDS

def is_tombstoned(session: Session, phone: str) -> bool: ...
    # SELECT 1 FROM user_tombstones WHERE phone_number=:phone

def opt_out(session: Session, phone: str, keyword: str) -> None: ...
    # DELETE FROM users WHERE phone_number=:phone
    # INSERT INTO user_tombstones(phone_number, last_keyword) VALUES (:phone,:kw)
    #   ON CONFLICT (phone_number) DO UPDATE SET opted_out_at=now(), last_keyword=:kw
    # Caller commits.

def clear_tombstone(session: Session, phone: str) -> None: ...
    # DELETE FROM user_tombstones WHERE phone_number=:phone

def ensure_user(session: Session, phone: str) -> User: ...
    # INSERT ... ON CONFLICT DO NOTHING; then SELECT. Returns the User row.

def record_interaction(session: Session, phone: str, matched_course: str | None) -> None: ...
    # ensure_user
    # UPDATE users SET interaction_count = interaction_count + 1,
    #                  last_seen_at = now(),
    #                  inferred_courses = jsonb_set(
    #                      inferred_courses,
    #                      ARRAY[:matched_course],
    #                      to_jsonb(COALESCE((inferred_courses ->> :matched_course)::int, 0) + 1)
    #                  )
    # WHERE phone_number=:phone
    # Skipped entirely (return early) if matched_course is None.
    # Caller commits.

def get_top_courses(session: Session, phone: str, top_k: int) -> list[str]: ...
    # Returns the top_k course codes by JSONB count, descending. Empty if user missing.

def needs_privacy_notice(session: Session, phone: str) -> bool: ...
    # True iff users row missing OR privacy_notice_sent_at IS NULL.
    # Tombstoned phones return False (we don't re-spam them).

def mark_privacy_notice_sent(session: Session, phone: str) -> None: ...
```

All functions are sync, take a `Session`, and never call out to GCP / Vertex / Meta. No caching.

---

## 7. Retrieval change (`app/retrieval.py`)

Extend `find_paper_by_semantic_query`:

```python
def find_paper_by_semantic_query(
    session: Session,
    course_code: str,
    query_text: str,
    top_k: int | None = None,
    prefer_courses: list[str] | None = None,
) -> Paper | None
```

Behavior change:

- The base SQL is unchanged: ANN order by cosine distance, with `is_retired`/active-risk filters.
- When `prefer_courses` is non-empty, fetch `top_k * 2` candidates instead of `top_k`. In Python, partition by `(distance, is_preferred)` where `is_preferred = paper.course_code in prefer_courses`. **Within a window of `settings.personalization_tie_band`**, prefer rows whose course is in `prefer_courses`. Outside the window, distance wins. Return the first survivor.
- If `prefer_courses` is empty/None, behavior is byte-identical to Phase 5.

This is intentionally Python-side post-processing, not a SQL CASE rewrite — it keeps the HNSW index uncluttered and makes the tiebreaker easy to reason about.

`find_paper` is **not** changed. Personalization affects only the semantic-fallback path.

---

## 8. Pipeline change (`app/pipeline.py`)

The structure preserves the existing 1–8 step flow. Insertions:

### 8.1 New step **0**, before idempotency

```python
# 0. Opt-out keyword detection (Phase 6) — runs before LLM, before billable work.
if msg.type == "text" and msg.text and profile.is_opt_out_message(msg.text.body):
    profile.opt_out(session, msg.from_, msg.text.body.upper().strip())
    session.commit()
    # Idempotency log still happens, but use a synthetic outcome.
    log_entry = RequestLog(
        wa_message_id=msg.id,
        wa_from=msg.from_,
        user_text=msg.text.body,
        outcome="opted_out",
    )
    session.add(log_entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DuplicateMessage()
    return TextReply(body=(
        "Got it — I've forgotten you. Your data is wiped. "
        "Send any message later to start fresh (this clears the opt-out)."
    ))
```

This block returns **before** step 1's idempotency commit. It writes its own RequestLog row using the same dedup contract (`IntegrityError → DuplicateMessage`).

### 8.2 In step 5 (intent branches), `paper_request` path

After the course guard (step 6) but **before** ILIKE lookup (step 7), clear any tombstone:

```python
if profile.is_tombstoned(session, msg.from_):
    profile.clear_tombstone(session, msg.from_)
    session.commit()
```

Then in step 7b (semantic fallback), pass `prefer_courses`:

```python
prefer = []
if not profile.is_tombstoned(session, msg.from_):
    prefer = profile.get_top_courses(session, msg.from_, settings.personalization_top_k_for_bias)
paper = retrieval.find_paper_by_semantic_query(
    session, course_code, msg.text.body, prefer_courses=prefer
)
```

### 8.3 In step 8 (Result), after a `paper` is matched

```python
# Write-side inference + soft personalization prefix
if not profile.is_tombstoned(session, msg.from_):
    profile.record_interaction(session, msg.from_, paper.course_code)
    top_courses = profile.get_top_courses(session, msg.from_, 1)
    user = session.execute(select(User).where(User.phone_number == msg.from_)).scalar_one_or_none()
    eligible = (
        user is not None
        and user.interaction_count >= settings.personalization_min_interactions
        and top_courses
        and top_courses[0] == paper.course_code
    )
    caption_prefix = "Prioritising your courses — " if eligible else ""
else:
    caption_prefix = ""

caption = f"{caption_prefix}{paper.course_code} {paper.semester.title()} {paper.year}"
```

The DocumentReply uses this `caption`.

### 8.4 Privacy notice append

Before any `return TextReply(...)` or `return DocumentReply(...)` on the **success** path (greeting, found-paper, semantic-fallback found, course-suggestion, "we don't have it yet"), check `profile.needs_privacy_notice(session, msg.from_)`. If True:

```python
notice = "\n\n(Tip: I learn which courses you ask about to rank results. Send 'STOP TRACKING' anytime to wipe my notes.)"
if isinstance(reply, TextReply):
    reply = TextReply(body=reply.body + notice)
elif isinstance(reply, DocumentReply):
    # DocumentReply caption is short; prefer to send a follow-up TextReply.
    # Implementation: in main.py the route handler sends both — see §9.
    ...
profile.mark_privacy_notice_sent(session, msg.from_)
session.commit()
```

For `DocumentReply`, append a "secondary text" via a new `Reply` discriminated form `DocumentReply.followup_text: str | None = None`. The route layer in `app/main.py` sends a follow-up `send_text` after `send_document` if `followup_text` is set. This avoids polluting the PDF caption with an entire privacy paragraph.

`Reply` schema gains:

```python
class DocumentReply(BaseModel):
    kind: Literal["document"] = "document"
    paper_id: int
    caption: str
    followup_text: str | None = None
```

`whatsapp.send_reply` extends:

```python
elif isinstance(reply, DocumentReply):
    pdf_bytes, filename = paper_loader(reply.paper_id)
    media_id = upload_media(http_client, pdf_bytes, filename)
    send_document(http_client, to, media_id, reply.caption, filename)
    if reply.followup_text:
        send_text(http_client, to, reply.followup_text)
```

**No** new outcome strings beyond `"opted_out"`.

---

## 9. Concurrency & idempotency

- All `users` mutations happen inside the same session as the request; SQLAlchemy 2.0 autobegins a transaction.
- `record_interaction` uses `INSERT ... ON CONFLICT DO NOTHING` for `users` and a row-level UPDATE for the increment. No `FOR UPDATE` needed: a Meta retry would be deduped by the existing `request_log.wa_message_id` UNIQUE — `record_interaction` is reachable only from the post-dedup branch, so a retry never double-counts.
- `opt_out` uses `INSERT ... ON CONFLICT (phone_number) DO UPDATE SET opted_out_at=now()` on `user_tombstones`; idempotent.

---

## 10. Admin commands

### `admin/users.py`

```
python -m admin.users get <PHONE>
python -m admin.users list [--limit 50] [--csv PATH]
python -m admin.users reset <PHONE> [--yes]
python -m admin.users export <PHONE> [--out PATH]
```

- `get`: print `phone_number, interaction_count, last_seen_at, inferred_courses, opted_out_at, tombstoned (Y/N)`.
- `list`: tabulated, sorted by `last_seen_at DESC`. Excludes tombstoned by default; `--include-tombstoned` flag flips it.
- `reset <PHONE>`: clears `inferred_courses` to `'{}'`, sets `interaction_count=0`. Confirmation prompt unless `--yes`. **Does NOT** opt the user out.
- `export <PHONE>`: writes JSON of the user's full row + their last 50 `request_log` entries to `--out` (default stdout). Used to honor data-access requests.

---

## 11. Tests

### 11.1 `tests/test_profile.py`
- `is_opt_out_message`: `"OPT OUT"` → True; `"opt out"` → True (case-insensitive); `"random"` → False; `"OPTOUT"` → False (no space).
- `record_interaction` increments JSONB counter atomically; second call increments to 2; passing `None` does nothing.
- `get_top_courses` returns courses in descending count order.
- `is_tombstoned`/`clear_tombstone` round-trip.

### 11.2 `tests/test_opt_out.py`
- Send `WAMessage(text="STOP TRACKING")`. Assert reply is the opt-out confirmation; `users` row absent; `user_tombstones` present.
- Send next message from same phone (a normal `paper_request`). Assert tombstone is cleared by the time the LLM is mocked. After a successful retrieval, `users` row exists with `interaction_count=1`.

### 11.3 `tests/test_personalization.py`
- Insert a user with `inferred_courses={"CSC305": 10, "MTH102": 1}`, `interaction_count=11`. Two papers: CSC305 and MTH102, both with chunks whose embeddings are within `personalization_tie_band` of the query.
- Mock `embed_query` to return a fixture vector. Assert `find_paper_by_semantic_query` with `prefer_courses=["CSC305"]` returns the CSC305 paper even when MTH102 has a marginally smaller distance.
- With `prefer_courses=[]` and the same fixtures, the smallest-distance paper wins.
- Pipeline-level: matching CSC305 with `interaction_count=11` and `inferred_courses` top=CSC305 yields a DocumentReply whose caption starts with `"Prioritising your courses — "`. With `interaction_count=2`, the caption is unchanged.

### 11.4 `tests/test_pipeline.py` extension
- `test_pipeline_privacy_notice_first_time`: brand-new phone sends a greeting. Assert reply ends with the privacy-notice line. Send a 2nd greeting → assert reply does *not* contain the notice.

---

## 12. RUNBOOK / README updates

### `RUNBOOK.md`
- New §10: **Privacy / opt-out.** "Any user can wipe their record by sending STOP TRACKING. To reset a single user's profile without opting them out: `python -m admin.users reset <PHONE> --yes`. To export a user's data on request: `python -m admin.users export <PHONE> --out user.json`."

### `README.md`
- New "Privacy" section, two paragraphs: what we store (phone, count of asks per course, last-seen time), how to wipe (STOP TRACKING keyword), where the data lives (Cloud SQL row in `users`).

---

## 13. Cost recheck

Phase 6 adds **zero LLM calls**. The opt-out branch *removes* an LLM call per opted-out message. Steady-state monthly cost remains ~$9.50 per `PRD.md §5.3`.

Storage: each `users` row is < 200 bytes typical; with 500 active users that's < 100 KB. Negligible.

---

## 14. Non-goals reaffirmed

The execution agent must **not** add any of the following:

- LLM-based recommendations / mentor responses / "you might also like" replies.
- Background workers, queues, schedulers.
- A web profile UI or public data-access portal.
- Caching of `is_tombstoned` results (must reflect immediate state).
- Re-ranking the primary ILIKE retrieval. Tiebreaker only fires inside the semantic-fallback.
- A separate consent table or interactive opt-in flow.
- LLM summarisation of `users.inferred_courses` (e.g., the deferred `users.user_summaries` field from `MASTER_PRD §6` — explicitly V1.2+, not Phase 6).
- Sending follow-up messages to opted-out phones for any reason.
- Calling Vertex on the opt-out path.

If any become tempting, stop and amend `PHASE_6_SPEC.md` first.

---

## 15. Definition of Done (Phase 6)

A maintainer (Hafeedh or Ibrahim) on his laptop:

1. Pulls `master`, `pip install -r requirements.txt`. No errors.
2. Applies `migrations/006_phase6.sql`. `\d users` and `\d user_tombstones` exist.
3. Sends three `paper_request` messages from his phone for CSC305. `python -m admin.users get <his phone>` shows `inferred_courses={"CSC305":3}`, `interaction_count=3`.
4. Sends `STOP TRACKING`. Receives the wipe confirmation. `python -m admin.users get` shows the row gone; `user_tombstones` has the entry.
5. Sends another `paper_request`. Tombstone clears; new `users` row appears with `interaction_count=1`.
6. From a brand-new phone: first message returns reply with the privacy-notice tail line; second message does not.
7. With `interaction_count >= 5` and a clear top inferred course, sending a request that resolves to that course yields a `DocumentReply` whose caption starts with `"Prioritising your courses — "`.
8. `pytest -q` passes including every Phase 6 test in §11.
9. `make smoke` still prints `SMOKE OK`.
10. Total monthly cost remains ≤ $15.

When all 10 are green, Phase 6 is implementation-complete.
