from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.config import settings
from app.db import RequestLog
from app.schemas import WAMessage, Reply, TextReply, DocumentReply
from app import llm
from app import retrieval
from app.errors import RouterError, DuplicateMessage
import logging

log = logging.getLogger(__name__)

def handle_message(session: Session, msg: WAMessage) -> Reply:
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
        log.info("Duplicate message received", extra={"wa_message_id": msg.id})
        raise DuplicateMessage()

    try:
        # We need to update this log entry, so let's re-fetch it or just use it since it's committed
        # Actually it's detached after commit unless we set expire_on_commit=False (which we did).
        
        # 2. Type guard
        if msg.type != "text":
            log_entry.outcome = "error"
            log_entry.error = "non_text_message"
            session.commit()
            return TextReply(body="Send the course code, year, and semester as a text message, e.g. 'MTH102 harmattan 2022'.")

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
            return TextReply(body="The bot is busy right now. Try again in a minute, in shaa Allah.")

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
            return TextReply(body="Sorry, I couldn't understand that request. Please try again.")

        # 5. Branch on intent
        if routed.intent == "greeting":
            log_entry.outcome = "sent"
            session.commit()
            return TextReply(body="Wa alaykum salaam. Send a request like 'MTH102 harmattan 2022' to get the past paper.")
        elif routed.intent == "other":
            log_entry.outcome = "not_found"
            session.commit()
            return TextReply(body="I only handle MTH102 past-paper requests for now. Try 'MTH102 rain 2023'.")

        # paper_request intent
        # 6. Course guard
        if not routed.course_code or routed.course_code.upper() != settings.hardcoded_course_code.upper():
            log_entry.outcome = "not_found"
            session.commit()
            return TextReply(body=f"Phase 1 only serves {settings.hardcoded_course_code}. Other courses are coming soon.")

        # 7. Lookup
        paper = retrieval.find_paper(session, settings.hardcoded_course_code, routed.year, routed.semester)

        # 8. Result
        if paper:
            log_entry.matched_paper_id = paper.id
            log_entry.outcome = "sent"
            session.commit()
            return DocumentReply(
                paper_id=paper.id, 
                caption=f"{paper.course_code} {paper.semester.title()} {paper.year}"
            )
        else:
            log_entry.outcome = "not_found"
            session.commit()
            return TextReply(body=f"We don't have this {settings.hardcoded_course_code} paper yet — Ibrahim is uploading.")
            
    except Exception:
        session.rollback()
        raise