from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.config import settings
from app.db import RequestLog
from app.schemas import WAMessage, Reply, TextReply, DocumentReply
from app import llm
from app import retrieval
from app.errors import RouterError, DuplicateMessage, EmbeddingError
from app import intake
from app import profile
from app import pricing
import logging

log = logging.getLogger(__name__)

def handle_message(session: Session, msg: WAMessage, http_client, gcs_client) -> Reply:
    # Phase 5: opportunistic sealer.
    try:
        intake.sweep_and_seal(session, gcs_client)
    except Exception:
        log.exception("intake_sweep_failed", extra={"phase": "sealer"})

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

    # 1. Idempotency
    user_text = msg.text.body if msg.text else ""
    log_entry = RequestLog(
        wa_message_id=msg.id,
        wa_from=msg.from_,
        user_text=user_text,
        outcome="received"
    )
    session.add(log_entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        log.info("Duplicate message received", extra={"wa_message_id": msg.id, "wa_from": msg.from_, "phase": "request"})
        raise DuplicateMessage()

    def _apply_privacy_notice(reply: Reply) -> Reply:
        if profile.needs_privacy_notice(session, msg.from_):
            notice = "\n\n(Tip: I learn which courses you ask about to rank results. Send 'STOP TRACKING' anytime to wipe my notes.)"
            if isinstance(reply, TextReply):
                reply = TextReply(body=reply.body + notice)
            elif isinstance(reply, DocumentReply):
                reply.followup_text = notice
            profile.mark_privacy_notice_sent(session, msg.from_)
            session.commit()
        return reply

    try:
        # Phase 5: Image branch
        if msg.type == "image":
            if msg.image is None:
                log_entry.outcome = "error"
                log_entry.error = "image_payload_missing"
                session.commit()
                return _apply_privacy_notice(TextReply(body="Send a clear photo of the paper."))
            
            reply = intake.handle_image(session, http_client, gcs_client, msg)
            if isinstance(reply, TextReply) and "isn't approved" in reply.body:
                log_entry.outcome = "not_whitelisted"
            elif isinstance(reply, TextReply) and "submitted enough" in reply.body:
                log_entry.outcome = "rate_limited"
            else:
                log_entry.outcome = "received_image" # internal success
            session.commit()
            return _apply_privacy_notice(reply)

        # 2. Type guard
        if msg.type != "text":
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
            log.warning("request_rate_limit_exceeded", extra={"wa_from": msg.from_, "phase": "request", "count": recent_count})
            return _apply_privacy_notice(TextReply(body="The bot is busy right now. Try again in a minute, in shaa Allah."))

        # 3b. Daily cost circuit breaker (Phase 7).
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
            log.warning("daily_token_floor_exceeded", extra={"wa_from": msg.from_, "phase": "request", "spent_tok": spent_tok})
            return _apply_privacy_notice(TextReply(
                body="The bot has hit its daily limit. Try tomorrow morning, in shaa Allah."
            ))

        # 4. Route
        try:
            routed, in_tok, out_tok = llm.route(msg.text.body)
            log_entry.flash_input_tokens = in_tok
            log_entry.flash_output_tokens = out_tok
            log_entry.routed_course = routed.course_code
            log_entry.routed_year = routed.year
            log_entry.routed_semester = routed.semester
        except RouterError as e:
            log_entry.outcome = "error"
            log_entry.error = str(e)
            session.commit()
            log.error("router_failed", extra={"wa_message_id": msg.id, "wa_from": msg.from_, "phase": "request", "err": str(e)})
            return _apply_privacy_notice(TextReply(body="Sorry, I couldn't understand that request. Please try again."))

        # 5. Branch on intent
        if routed.intent == "greeting":
            log_entry.outcome = "sent"
            session.commit()
            return _apply_privacy_notice(TextReply(body="Wa alaykum salaam. Send a request like 'MTH102 harmattan 2022' to get the past paper."))
        elif routed.intent == "other":
            log_entry.outcome = "not_found"
            session.commit()
            return _apply_privacy_notice(TextReply(body="I only handle past-paper requests. Try something like 'MTH102 harmattan 2022'."))

        # paper_request intent
        
        # Clear tombstone on re-engagement
        if profile.is_tombstoned(session, msg.from_):
            profile.clear_tombstone(session, msg.from_)
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
                if not profile.is_tombstoned(session, msg.from_):
                    prefer = profile.get_top_courses(session, msg.from_, settings.personalization_top_k_for_bias)
                paper = retrieval.find_paper_by_semantic_query(
                    session, course_code, msg.text.body, prefer_courses=prefer
                )
            except EmbeddingError:
                # Soft fallback: stay with paper=None and let step 8 reply "not found".
                log.warning("semantic_fallback_embedding_failed", extra={"wa_message_id": msg.id, "wa_from": msg.from_, "phase": "request"})

        # 8. Result
        if paper:
            log_entry.matched_paper_id = paper.id
            log_entry.outcome = "sent"
            
            # Write-side inference + soft personalization prefix
            if not profile.is_tombstoned(session, msg.from_):
                profile.record_interaction(session, msg.from_, paper.course_code)
                top_courses = profile.get_top_courses(session, msg.from_, 1)
                
                from app.db import User
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
            
            session.commit()
            log.info("paper_sent", extra={"wa_message_id": msg.id, "wa_from": msg.from_, "phase": "request", "course": paper.course_code, "outcome": "sent"})
            return _apply_privacy_notice(DocumentReply(
                paper_id=paper.id, 
                caption=caption
            ))
        else:
            log_entry.outcome = "not_found"
            session.commit()
            log.info("paper_not_found", extra={"wa_message_id": msg.id, "wa_from": msg.from_, "phase": "request", "course": course_code, "outcome": "not_found"})
            return _apply_privacy_notice(TextReply(body=f"We don't have this {course_code} paper yet — Ibrahim is uploading."))
            
    except Exception:
        session.rollback()
        raise