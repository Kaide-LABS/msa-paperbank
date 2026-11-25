"""Channel-neutral inbound core (Phase 2).

`InboundMessage` is the channel-agnostic envelope every channel adapter maps its own
wire payload onto; `handle_inbound` holds the routing/intent/retrieval/image-intake logic
that used to live in `app.pipeline.handle_message`, expressed against `InboundMessage` only.

This module imports **no** WhatsApp-specific wire types: channels are
translated at the edge by a thin adapter (`app.channels.whatsapp`). `OutboundReply` is an
alias for the already channel-neutral `Reply` union in `app.schemas` — replies carry no
WhatsApp wire types, so they are reused as-is rather than re-modelled.
"""
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import RequestLog
from app.ports import ObjectStore
from app.schemas import Reply, TextReply, DocumentReply
from app import llm
from app import retrieval
from app import intake
from app import profile
from app import pricing
from app.errors import RouterError, DuplicateMessage, EmbeddingError

log = logging.getLogger(__name__)


class InboundMessage(BaseModel):
    """Channel-neutral inbound envelope. Adapters map their own payloads onto this; the
    core never sees a channel-specific wire type."""
    channel: str
    sender: str
    message_id: str
    kind: Literal["text", "image", "other"]
    text: str | None = None
    media_id: str | None = None
    raw: dict | None = None   # opaque channel passthrough (original payload), not inspected by the core


# Re-exported so callers name the outbound seam without reaching into app.schemas; identity this phase.
OutboundReply = Reply


def handle_inbound(session: Session, msg: InboundMessage, http_client, store: ObjectStore) -> Reply:
    """Channel-neutral entrypoint: same routing/intent/retrieval behaviour as the former
    `app.pipeline.handle_message`, driven off `InboundMessage` instead of a channel wire type."""
    # Phase 5: opportunistic sealer.
    try:
        intake.sweep_and_seal(session, store)
    except Exception:
        log.exception("intake_sweep_failed", extra={"phase": "sealer"})

    # 0. Opt-out keyword detection (Phase 6) — runs before LLM, before billable work.
    if msg.kind == "text" and msg.text and profile.is_opt_out_message(msg.text):
        profile.opt_out(session, msg.sender, msg.text.upper().strip())
        session.commit()
        # Idempotency log still happens, but use a synthetic outcome.
        log_entry = RequestLog(
            wa_message_id=msg.message_id,
            wa_from=msg.sender,
            user_text=msg.text,
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

    # 1. Idempotency
    user_text = msg.text if msg.text else ""
    log_entry = RequestLog(
        wa_message_id=msg.message_id,
        wa_from=msg.sender,
        user_text=user_text,
        outcome="received"
    )
    session.add(log_entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        log.info("Duplicate message received", extra={"wa_message_id": msg.message_id, "wa_from": msg.sender, "phase": "request"})
        raise DuplicateMessage()

    def _apply_privacy_notice(reply: Reply) -> Reply:
        if profile.needs_privacy_notice(session, msg.sender):
            notice = "\n\n(Tip: I learn which courses you ask about to rank results. Send 'STOP TRACKING' anytime to wipe my notes.)"
            if isinstance(reply, TextReply):
                reply = TextReply(body=reply.body + notice)
            elif isinstance(reply, DocumentReply):
                reply.followup_text = notice
            profile.mark_privacy_notice_sent(session, msg.sender)
            session.commit()
        return reply

    try:
        # Phase 5: Image branch
        if msg.kind == "image":
            if msg.media_id is None:
                log_entry.outcome = "error"
                log_entry.error = "image_payload_missing"
                session.commit()
                return _apply_privacy_notice(TextReply(body="Send a clear photo of the paper."))

            reply = intake.handle_image_inbound(
                session, http_client, store,
                phone=msg.sender, media_id=msg.media_id, message_id=msg.message_id,
            )
            if isinstance(reply, TextReply) and "isn't approved" in reply.body:
                log_entry.outcome = "not_whitelisted"
            elif isinstance(reply, TextReply) and "submitted enough" in reply.body:
                log_entry.outcome = "rate_limited"
            else:
                log_entry.outcome = "received_image" # internal success
            session.commit()
            return _apply_privacy_notice(reply)

        # 2. Type guard
        if msg.kind != "text":
            log_entry.outcome = "error"
            log_entry.error = "non_text_message"
            session.commit()
            return _apply_privacy_notice(TextReply(body="Send the course code, year, and semester as a text message, e.g. 'MTH102 harmattan 2022'."))

        # 3. Rate limit
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        count_query = select(func.count(RequestLog.id)).where(
            RequestLog.received_at >= one_hour_ago,
            RequestLog.outcome != 'rate_limited'
        )
        recent_count = session.execute(count_query).scalar_one()

        if recent_count >= settings.request_rate_limit_per_hour:
            log_entry.outcome = "rate_limited"
            session.commit()
            log.warning("request_rate_limit_exceeded", extra={"wa_from": msg.sender, "phase": "request", "count": recent_count})
            return _apply_privacy_notice(TextReply(body="The bot is busy right now. Try again in a minute, in shaa Allah."))

        # 3b. Daily cost circuit breaker (Phase 7).
        spent_usd = pricing.estimate_daily_spend_usd(session)
        if spent_usd >= settings.daily_cost_usd_cap:
            log_entry.outcome = "rate_limited"
            log_entry.error = "daily_cost_cap_exceeded"
            session.commit()
            log.warning("daily_cost_cap_exceeded", extra={
                "wa_from": msg.sender, "phase": "request", "spent_usd": round(spent_usd, 4),
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
            log.warning("daily_token_floor_exceeded", extra={"wa_from": msg.sender, "phase": "request", "spent_tok": spent_tok})
            return _apply_privacy_notice(TextReply(
                body="The bot has hit its daily limit. Try tomorrow morning, in shaa Allah."
            ))

        # 4. Route
        try:
            routed, in_tok, out_tok = llm.route(msg.text)
            log_entry.flash_input_tokens = in_tok
            log_entry.flash_output_tokens = out_tok
            log_entry.routed_course = routed.course_code
            log_entry.routed_year = routed.year
            log_entry.routed_semester = routed.semester
        except RouterError as e:
            log_entry.outcome = "error"
            log_entry.error = str(e)
            session.commit()
            log.error("router_failed", extra={"wa_message_id": msg.message_id, "wa_from": msg.sender, "phase": "request", "err": str(e)})
            return _apply_privacy_notice(TextReply(body="Sorry, I couldn't understand that request. Please try again."))

        # 5. Branch on intent
        if routed.intent == "greeting":
            log_entry.outcome = "sent"
            session.commit()
            return _apply_privacy_notice(TextReply(body="Wa alaykum salaam. Send a request like 'MTH102 harmattan 2022' to get the past paper."))
        elif routed.intent == "other":
            log_entry.outcome = "not_found"
            session.commit()
            other_replies = [
                "I'm the PAU Muslim Ummah past-paper bot. I find past papers — send a course, year and semester like 'MTH102 harmattan 2022'.",
                "I only fetch past papers for now. Try something like 'CSC201 rain 2023'.",
                "I keep it simple: tell me a course code, year and semester and I'll send the paper, e.g. 'GST122 harmattan 2022'.",
            ]
            return _apply_privacy_notice(TextReply(body=random.choice(other_replies)))

        # paper_request intent

        # Clear tombstone on re-engagement
        if profile.is_tombstoned(session, msg.sender):
            profile.clear_tombstone(session, msg.sender)
            session.commit()

        # 6. Course guard (Phase 4: DB-backed)
        known = retrieval.known_courses(session)
        proposed = (routed.course_code or "").upper().replace(" ", "")
        if not proposed or proposed not in known:
            suggestions = retrieval.nearest_courses(session, proposed, settings.unknown_course_suggest_count)
            log_entry.outcome = "not_found"
            session.commit()
            if suggestions:
                body = "I don't have that course yet. Did you mean: " + ", ".join(suggestions) + "?"
            else:
                body = "I don't have that course in the catalog. Send something like 'MTH102 harmattan 2022'."
            return _apply_privacy_notice(TextReply(body=body))

        course_code = proposed

        # 7. Lookup
        paper = retrieval.find_paper(session, course_code, routed.year, routed.semester)

        # 7b. Phase 2/6 semantic fallback
        if paper is None and routed.confidence >= settings.semantic_fallback_min_router_confidence:
            try:
                prefer = []
                if not profile.is_tombstoned(session, msg.sender):
                    prefer = profile.get_top_courses(session, msg.sender, settings.personalization_top_k_for_bias)
                paper = retrieval.find_paper_by_semantic_query(
                    session, course_code, msg.text, prefer_courses=prefer
                )
            except EmbeddingError:
                # Soft fallback: stay with paper=None and let step 8 reply "not found".
                log.warning("semantic_fallback_embedding_failed", extra={"wa_message_id": msg.message_id, "wa_from": msg.sender, "phase": "request"})

        # 8. Result
        if paper:
            log_entry.matched_paper_id = paper.id
            log_entry.outcome = "sent"

            # Write-side inference + soft personalization prefix
            if not profile.is_tombstoned(session, msg.sender):
                profile.record_interaction(session, msg.sender, paper.course_code)
                top_courses = profile.get_top_courses(session, msg.sender, 1)

                from app.db import User
                user = session.execute(select(User).where(User.phone_number == msg.sender)).scalar_one_or_none()
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

            session.commit()
            log.info("paper_sent", extra={"wa_message_id": msg.message_id, "wa_from": msg.sender, "phase": "request", "course": paper.course_code, "outcome": "sent"})
            return _apply_privacy_notice(DocumentReply(
                paper_id=paper.id,
                caption=caption
            ))
        else:
            log_entry.outcome = "not_found"
            session.commit()
            log.info("paper_not_found", extra={"wa_message_id": msg.message_id, "wa_from": msg.sender, "phase": "request", "course": course_code, "outcome": "not_found"})
            return _apply_privacy_notice(TextReply(body=f"We don't have this {course_code} paper yet — Ibrahim is uploading."))

    except Exception:
        session.rollback()
        raise
