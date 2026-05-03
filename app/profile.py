from sqlalchemy.orm import Session
from sqlalchemy import select, func, text, update, delete
from sqlalchemy.dialects.postgresql import insert
from app.db import User, UserTombstone
from datetime import datetime, timezone
import json

OPT_OUT_KEYWORDS: frozenset[str] = frozenset({
    "STOP TRACKING", "STOP TRACKING ME", "OPT OUT",
    "DELETE MY DATA", "FORGET ME",
})

def is_opt_out_message(text: str) -> bool:
    return text.upper().strip() in OPT_OUT_KEYWORDS

def is_tombstoned(session: Session, phone: str) -> bool:
    return session.execute(
        select(1).where(UserTombstone.phone_number == phone)
    ).scalar() is not None

def opt_out(session: Session, phone: str, keyword: str) -> None:
    session.execute(delete(User).where(User.phone_number == phone))
    
    stmt = insert(UserTombstone).values(
        phone_number=phone,
        last_keyword=keyword
    ).on_conflict_do_update(
        index_elements=['phone_number'],
        set_=dict(opted_out_at=func.now(), last_keyword=keyword)
    )
    session.execute(stmt)

def clear_tombstone(session: Session, phone: str) -> None:
    session.execute(delete(UserTombstone).where(UserTombstone.phone_number == phone))

def ensure_user(session: Session, phone: str) -> User:
    stmt = insert(User).values(phone_number=phone).on_conflict_do_nothing(index_elements=['phone_number'])
    session.execute(stmt)
    return session.execute(select(User).where(User.phone_number == phone)).scalar_one()

def record_interaction(session: Session, phone: str, matched_course: str | None) -> None:
    if matched_course is None:
        return
        
    ensure_user(session, phone)
    
    stmt = update(User).where(User.phone_number == phone).values(
        interaction_count=User.interaction_count + 1,
        last_seen_at=func.now(),
        inferred_courses=func.jsonb_set(
            User.inferred_courses,
            func.string_to_array(matched_course, ','), # trick for single-element text array
            func.to_jsonb(func.coalesce(func.cast(func.jsonb_extract_path_text(User.inferred_courses, matched_course), text), '0').cast(text).cast(func.int) + 1)
        )
    )
    
    # Actually, simpler to just pull it, update in python and flush, or do raw SQL to avoid dialect headaches.
    # We will do raw SQL for the jsonb merge to be bulletproof.
    raw_sql = text("""
        UPDATE users SET 
            interaction_count = interaction_count + 1,
            last_seen_at = now(),
            inferred_courses = jsonb_set(
                inferred_courses, 
                ARRAY[:course], 
                to_jsonb(COALESCE((inferred_courses ->> :course)::int, 0) + 1)
            )
        WHERE phone_number = :phone
    """)
    session.execute(raw_sql, {"course": matched_course, "phone": phone})

def get_top_courses(session: Session, phone: str, top_k: int) -> list[str]:
    user = session.execute(select(User).where(User.phone_number == phone)).scalar_one_or_none()
    if not user or not user.inferred_courses:
        return []
        
    # Sort by value desc
    sorted_items = sorted(user.inferred_courses.items(), key=lambda item: item[1], reverse=True)
    return [k for k, v in sorted_items[:top_k]]

def needs_privacy_notice(session: Session, phone: str) -> bool:
    if is_tombstoned(session, phone):
        return False
        
    user = session.execute(select(User).where(User.phone_number == phone)).scalar_one_or_none()
    if user is None:
        return True
        
    return user.privacy_notice_sent_at is None

def mark_privacy_notice_sent(session: Session, phone: str) -> None:
    ensure_user(session, phone)
    session.execute(
        update(User).where(User.phone_number == phone).values(privacy_notice_sent_at=func.now())
    )