# -*- coding: utf-8 -*-
"""V1 serving handler — lean retrieval-only WhatsApp path over the corpus-index pending_papers.

V1.1 adds a per-student SCHOOL profile + school-scoped matching (still retrieval-only; AI-3
firewall holds). First contact onboards the student to one of the 3 PAU schools (numbered tap),
then retrieval is scoped to that school — with a SOFT fallback to all-PAU when the school has no
match, so nobody is left empty-handed. School is the only fixed taxonomy; departments grow freely
underneath (matching never enumerates departments — a new dept's papers carry their school from
the ingest folder path and are picked up automatically).

Operational state (NOT corpus promotion):
  served_log      — idempotency + per-hour rate limit + token accounting
  serve_session   — one-shot tap state: {"kind": "disambiguation"|"onboarding", "items":[...],
                    "pending_query": <original text to replay after onboarding>}
  student_profile — phone_number -> school (SMSS/SMC/SST), dept (optional, later)
"""
import re
import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.config import settings
from app.schemas import WAMessage, Reply, TextReply, DocumentReply
from app import llm, contributions
from app.serve_index import search_index, candidate_by_id
from app.errors import RouterError, DuplicateMessage

log = logging.getLogger(__name__)
_PICK_RE = re.compile(r"^\s*([1-9])\s*$")
_CHANGE_RE = re.compile(r"\b(change|switch)\s+(my\s+)?schools?\b", re.I)

# The ONLY fixed taxonomy. Departments are intentionally NOT listed anywhere.
SCHOOLS = [
    ("SMSS", "School of Management and Social Sciences"),
    ("SMC",  "School of Media and Communication"),
    ("SST",  "School of Science and Technology"),
]

_GREETING = ("Hi! Send a course code or title — e.g. 'GST111' or "
             "'introduction to finance' — and I'll find the past paper for you.")
_OTHER = ("I'm the PAU Muslim Ummah past-paper bot — I find past papers. Send a course code or title, "
          "e.g. 'CSC201' or 'organic chemistry'.")
_MISS = ("I couldn't find that paper. Try the course code or a fuller title "
         "(e.g. 'GST111' or 'introduction to finance'). Soon you'll be able to send a photo to "
         "add a paper yourself.")
_BUSY = "The bot is busy right now. Please try again in a minute."


def _school_prompt(lead: str) -> str:
    lines = [lead, "Which school are you in? Reply with a number:"]
    for i, (code, name) in enumerate(SCHOOLS, 1):
        lines.append(f"{i}) {code} — {name}")
    lines.append("(You can say 'change school' anytime.)")
    return "\n".join(lines)


def _onboarding_items():
    return [{"onboard": code, "label": f"{code} — {name}"} for code, name in SCHOOLS]


# ----------------------------------------------------------------------------- served_log
def _log_insert(session: Session, msg: WAMessage) -> None:
    session.execute(text(
        "INSERT INTO served_log (wa_message_id, wa_from, user_text, outcome) "
        "VALUES (:mid, :frm, :txt, 'received')"
    ), {"mid": msg.id, "frm": msg.from_, "txt": (msg.text.body if msg.text else "")})


def _log_update(session: Session, msg: WAMessage, outcome: str, intent: str | None = None,
                matched_id: int | None = None, in_tok: int | None = None, out_tok: int | None = None) -> None:
    session.execute(text(
        "UPDATE served_log SET outcome = :o, intent = COALESCE(:intent, intent), "
        "matched_id = COALESCE(:mid, matched_id), in_tok = COALESCE(:itok, in_tok), "
        "out_tok = COALESCE(:otok, out_tok) WHERE wa_message_id = :wamid"
    ), {"o": outcome, "intent": intent, "mid": matched_id, "itok": in_tok, "otok": out_tok, "wamid": msg.id})


# ----------------------------------------------------------------------------- serve_session
def _store_session(session: Session, phone: str, payload: dict) -> None:
    session.execute(text(
        "INSERT INTO serve_session (phone_number, candidates, created_at) VALUES (:p, :c, now()) "
        "ON CONFLICT (phone_number) DO UPDATE SET candidates = EXCLUDED.candidates, created_at = now()"
    ), {"p": phone, "c": json.dumps(payload)})


def _pop_session(session: Session, phone: str) -> dict | None:
    """One-shot read+delete of the tap state, honouring per-kind TTL."""
    row = session.execute(text(
        "SELECT candidates, created_at FROM serve_session WHERE phone_number = :p"
    ), {"p": phone}).mappings().first()
    if not row:
        return None
    payload = row["candidates"] if isinstance(row["candidates"], (dict, list)) else json.loads(row["candidates"])
    if isinstance(payload, list):                      # back-compat: pre-V1.1 bare disambiguation list
        payload = {"kind": "disambiguation", "items": payload}
    ttl = (settings.serve_onboarding_ttl_seconds if payload.get("kind") == "onboarding"
           else settings.serve_session_ttl_seconds)
    fresh = row["created_at"] is None or row["created_at"] >= datetime.now(timezone.utc) - timedelta(seconds=ttl)
    session.execute(text("DELETE FROM serve_session WHERE phone_number = :p"), {"p": phone})
    return payload if fresh else None


# ----------------------------------------------------------------------------- student_profile
def _get_profile(session: Session, phone: str) -> dict | None:
    row = session.execute(text(
        "SELECT school, dept FROM student_profile WHERE phone_number = :p"
    ), {"p": phone}).mappings().first()
    return dict(row) if row else None


def _set_school(session: Session, phone: str, school: str) -> None:
    session.execute(text(
        "INSERT INTO student_profile (phone_number, school, created_at, last_seen_at) "
        "VALUES (:p, :s, now(), now()) "
        "ON CONFLICT (phone_number) DO UPDATE SET school = EXCLUDED.school, last_seen_at = now()"
    ), {"p": phone, "s": school})


# ----------------------------------------------------------------------------- serve a query
def _serve_for(session: Session, msg: WAMessage, routed, body: str, school: str | None,
               in_tok: int, out_tok: int, prefix: str = "") -> Reply:
    result = search_index(session, routed, body, school=school)
    note = ""
    if result.fellback and result.scoped_school is None and school:
        note = f"No {school} match for that — here's what I found across PAU:\n"

    if result.kind == "serve":
        c = result.match
        _log_update(session, msg, "sent", intent="paper_request", matched_id=c.id, in_tok=in_tok, out_tok=out_tok)
        session.commit()
        cap = f"{prefix}{('(across PAU) ' if note else '')}{c.label()}".strip()
        return DocumentReply(paper_id=c.id, caption=cap[:1000])

    if result.kind == "disambiguate":
        _store_session(session, msg.from_, {"kind": "disambiguation",
            "items": [{"id": c.id, "label": c.label(), "code": c.course_code} for c in result.candidates]})
        _log_update(session, msg, "disambiguate", intent="paper_request", in_tok=in_tok, out_tok=out_tok)
        session.commit()
        head = (prefix + note + "I found a few — which one? Reply with the number:").strip()
        lines = [head] + [f"{i}) {c.label()}" for i, c in enumerate(result.candidates, 1)]
        return TextReply(body="\n".join(lines))

    _log_update(session, msg, "not_found", intent="paper_request", in_tok=in_tok, out_tok=out_tok)
    session.commit()
    return TextReply(body=(prefix + _MISS).strip())


def _route_and_serve(session: Session, msg: WAMessage, body: str, school: str | None, prefix: str = "") -> Reply:
    try:
        routed, in_tok, out_tok = llm.route(body)
    except RouterError as e:
        _log_update(session, msg, "error", intent="error"); session.commit()
        log.error("v1_router_failed", extra={"wa_message_id": msg.id, "err": str(e)})
        return TextReply(body=(prefix + "Sorry, I couldn't understand that. Send a course code or title.").strip())
    if routed.intent == "greeting":
        _log_update(session, msg, "sent", intent="greeting", in_tok=in_tok, out_tok=out_tok); session.commit()
        return TextReply(body=(prefix + _GREETING).strip())
    if routed.intent == "other":
        _log_update(session, msg, "not_found", intent="other", in_tok=in_tok, out_tok=out_tok); session.commit()
        return TextReply(body=(prefix + _OTHER).strip())
    return _serve_for(session, msg, routed, body, school, in_tok, out_tok, prefix=prefix)


# ----------------------------------------------------------------------------- main entry
def handle_message_v1(session: Session, msg: WAMessage, http_client, gcs_client) -> Reply:
    # Opportunistic contribution idle-sweep (check-ins / finalize) — side-effect only (Phase-5 pattern).
    if settings.serve_contributions_enabled:
        try:
            contributions.sweep(session, http_client, gcs_client)
        except Exception:
            log.exception("contribution_sweep_failed")
            session.rollback()

    # 1. Idempotency first — covers images + text; Meta retries the webhook.
    try:
        _log_insert(session, msg)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DuplicateMessage()

    # 2. Contribution intake: image messages, or any text while a contribution session is active.
    if settings.serve_contributions_enabled:
        reply = contributions.handle(session, msg, http_client, gcs_client)
        if reply is not None:
            return reply

    # --- retrieval path (text only from here) ---
    if msg.type != "text" or not msg.text:
        return TextReply(body="Send a course code or title, e.g. 'GST111' or 'introduction to finance'. "
                              "Or send a photo of a past paper to contribute one.")
    body = msg.text.body.strip()

    # 3. Rate limit (retrieval, global per hour).
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = session.execute(text(
        "SELECT count(*) FROM served_log WHERE created_at >= :t AND outcome <> 'rate_limited'"
    ), {"t": one_hour_ago}).scalar()
    if recent and recent >= settings.request_rate_limit_per_hour:
        _log_update(session, msg, "rate_limited"); session.commit()
        return TextReply(body=_BUSY)

    # 3. Flag OFF -> legacy unscoped V1 behaviour (no profile, no onboarding).
    if not settings.serve_school_scoping_enabled:
        return _route_and_serve(session, msg, body, school=None)

    # ---- V1.1 school-scoping path ----
    phone = msg.from_

    # 3a. change-school keyword (re-onboard, keep no pending query).
    if _CHANGE_RE.search(body):
        _store_session(session, phone, {"kind": "onboarding", "items": _onboarding_items(), "pending_query": None})
        _log_update(session, msg, "onboarding", intent="change_school"); session.commit()
        return TextReply(body=_school_prompt("Sure — let's switch your school."))

    # 3b. tap resolution (onboarding pick OR disambiguation pick).
    pm = _PICK_RE.match(body)
    if pm:
        payload = _pop_session(session, phone)
        if payload:
            items = payload.get("items", [])
            n = int(pm.group(1))
            if 1 <= n <= len(items):
                chosen = items[n - 1]
                if payload.get("kind") == "onboarding":
                    school = chosen["onboard"]
                    _set_school(session, phone, school)
                    confirm = f"Got it — I'll find papers from {school} for you. "
                    pq = payload.get("pending_query")
                    if pq:                               # replay the original request, now scoped
                        return _route_and_serve(session, msg, pq, school=school, prefix=confirm)
                    _log_update(session, msg, "sent", intent="onboarded"); session.commit()
                    return TextReply(body=confirm + "Send a course code or title and I'll find the paper.")
                else:                                    # disambiguation paper pick (may be a grouped exam)
                    _log_update(session, msg, "sent", intent="pick", matched_id=chosen["id"]); session.commit()
                    return DocumentReply(paper_id=chosen["id"], caption=chosen.get("label", "Your paper"))
        # no/expired/invalid session -> fall through

    # 3c. onboarding gate: unknown student.
    profile = _get_profile(session, phone)
    if profile is None:
        stash = None if pm else body                     # don't stash a bare number as a query
        _store_session(session, phone, {"kind": "onboarding", "items": _onboarding_items(), "pending_query": stash})
        _log_update(session, msg, "onboarding", intent="onboarding"); session.commit()
        return TextReply(body=_school_prompt("Welcome to the PAU Muslim Ummah past-paper bot!"))

    # 3d. known student -> school-scoped serve.
    return _route_and_serve(session, msg, body, school=profile["school"])
