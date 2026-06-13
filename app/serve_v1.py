# -*- coding: utf-8 -*-
"""V1 serving handler — the lean retrieval-only WhatsApp path over the corpus-index pending_papers.

Replaces the normalized-schema pipeline (papers/courses/paper_chunks/users/intake_* don't exist in
prod). Reuses llm.route (intent + course parse) and the committed enhanced-serve path. AI-3 firewall
intact: it finds papers, offers a tap-to-choose disambiguation, or honestly misses — no tutoring.

Operational state lives in two lean tables (NOT corpus promotion):
  served_log    — idempotency (unique wa_message_id) + per-hour rate limit + token accounting
  serve_session — remembers a disambiguation list per phone so a bare '2' resolves to a paper
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
from app import llm
from app.serve_index import search_index, candidate_by_id, Candidate
from app.errors import RouterError, DuplicateMessage

log = logging.getLogger(__name__)
_PICK_RE = re.compile(r"^\s*([1-9])\s*$")

_GREETING = ("Wa alaykum salaam. Send a course code or title — e.g. 'GST111' or "
             "'introduction to finance' — and I'll find the past paper, in shaa Allah.")
_OTHER = ("I'm the PAU MSA past-paper bot — I find past papers. Send a course code or title, "
          "e.g. 'CSC201' or 'organic chemistry'.")
_MISS = ("I couldn't find that paper. Try the course code or a fuller title "
         "(e.g. 'GST111' or 'introduction to finance'). Soon you'll be able to send a photo to "
         "add a paper yourself, in shaa Allah.")
_BUSY = "The bot is busy right now. Please try again in a minute, in shaa Allah."


# ----------------------------------------------------------------------------- served_log helpers
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
    ), {"o": outcome, "intent": intent, "mid": matched_id, "itok": in_tok, "otok": out_tok,
        "wamid": msg.id})


# ----------------------------------------------------------------------------- serve_session helpers
def _store_session(session: Session, phone: str, candidates: list[Candidate]) -> None:
    payload = json.dumps([{"id": c.id, "label": c.label(), "code": c.course_code} for c in candidates])
    session.execute(text(
        "INSERT INTO serve_session (phone_number, candidates, created_at) "
        "VALUES (:p, :c, now()) "
        "ON CONFLICT (phone_number) DO UPDATE SET candidates = EXCLUDED.candidates, created_at = now()"
    ), {"p": phone, "c": payload})


def _resolve_pick(session: Session, phone: str, n: int) -> int | None:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.serve_session_ttl_seconds)
    row = session.execute(text(
        "SELECT candidates FROM serve_session WHERE phone_number = :p AND created_at >= :cut"
    ), {"p": phone, "cut": cutoff}).mappings().first()
    if not row:
        return None
    cands = row["candidates"] if isinstance(row["candidates"], list) else json.loads(row["candidates"])
    if 1 <= n <= len(cands):
        session.execute(text("DELETE FROM serve_session WHERE phone_number = :p"), {"p": phone})
        return int(cands[n - 1]["id"])
    return None


# ----------------------------------------------------------------------------- main entry
def handle_message_v1(session: Session, msg: WAMessage, http_client, gcs_client) -> Reply:
    if msg.type != "text" or not msg.text:
        return TextReply(body="Send a course code or title as a text message, e.g. 'GST111' or "
                              "'introduction to finance'.")
    body = msg.text.body.strip()

    # 1. Idempotency (Meta retries the webhook). Unique wa_message_id => duplicate.
    try:
        _log_insert(session, msg)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DuplicateMessage()

    # 2. Rate limit (global, per hour) — cheap abuse/cost guard.
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = session.execute(text(
        "SELECT count(*) FROM served_log WHERE created_at >= :t AND outcome <> 'rate_limited'"
    ), {"t": one_hour_ago}).scalar()
    if recent and recent >= settings.request_rate_limit_per_hour:
        _log_update(session, msg, "rate_limited"); session.commit()
        return TextReply(body=_BUSY)

    # 3. Tap-to-choose: a bare number resolves a pending disambiguation list.
    pick = _PICK_RE.match(body)
    if pick:
        chosen = _resolve_pick(session, msg.from_, int(pick.group(1)))
        if chosen is not None:
            c = candidate_by_id(session, chosen)
            _log_update(session, msg, "sent", intent="pick", matched_id=chosen)
            session.commit()
            return DocumentReply(paper_id=chosen, caption=(c.label() if c else "Your paper"))
        # no live session -> fall through to normal routing (treat the number as a query)

    # 4. Route (the only LLM call — Flash intent parse).
    try:
        routed, in_tok, out_tok = llm.route(body)
    except RouterError as e:
        _log_update(session, msg, "error", intent="error"); session.commit()
        log.error("v1_router_failed", extra={"wa_message_id": msg.id, "err": str(e)})
        return TextReply(body="Sorry, I couldn't understand that. Send a course code or title.")

    if routed.intent == "greeting":
        _log_update(session, msg, "sent", intent="greeting", in_tok=in_tok, out_tok=out_tok)
        session.commit()
        return TextReply(body=_GREETING)
    if routed.intent == "other":
        _log_update(session, msg, "not_found", intent="other", in_tok=in_tok, out_tok=out_tok)
        session.commit()
        return TextReply(body=_OTHER)

    # 5. paper_request -> layered search over the index.
    result = search_index(session, routed, body)

    if result.kind == "serve":
        c = result.match
        _log_update(session, msg, "sent", intent="paper_request", matched_id=c.id,
                    in_tok=in_tok, out_tok=out_tok)
        session.commit()
        log.info("v1_paper_sent", extra={"wa_from": msg.from_, "code": c.course_code, "id": c.id})
        return DocumentReply(paper_id=c.id, caption=c.label())

    if result.kind == "disambiguate":
        _store_session(session, msg.from_, result.candidates)
        _log_update(session, msg, "disambiguate", intent="paper_request",
                    in_tok=in_tok, out_tok=out_tok)
        session.commit()
        lines = ["I found a few — which one? Reply with the number:"]
        for i, c in enumerate(result.candidates, 1):
            lines.append(f"{i}) {c.label()}")
        return TextReply(body="\n".join(lines))

    # 6. Honest miss.
    _log_update(session, msg, "not_found", intent="paper_request", in_tok=in_tok, out_tok=out_tok)
    session.commit()
    log.info("v1_not_found", extra={"wa_from": msg.from_, "text": body[:80]})
    return TextReply(body=_MISS)
