import os
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, BigInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, synonym
from pgvector.sqlalchemy import Vector
from app.config import settings

# Test DB URL hook for pytest
TEST_DB_URL = os.environ.get("DATABASE_URL_TEST")

_engine_provider = None

if TEST_DB_URL:
    engine = create_engine(TEST_DB_URL, pool_size=2, max_overflow=2, pool_pre_ping=True)
else:
    from app.providers import get_engine_provider

    _engine_provider = get_engine_provider(settings)
    engine = _engine_provider.create_engine()

SessionLocal = sessionmaker(engine, expire_on_commit=False, autoflush=False)

def dispose() -> None:
    if _engine_provider is not None:
        _engine_provider.dispose()
    else:
        engine.dispose()

from sqlalchemy.dialects.postgresql import JSONB

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    phone_number: Mapped[str] = mapped_column(primary_key=True)
    inferred_courses: Mapped[dict] = mapped_column(JSONB, default={}, server_default='{}')
    interaction_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    privacy_notice_sent_at: Mapped[Optional[datetime]]
    opted_out_at: Mapped[Optional[datetime]]

class UserTombstone(Base):
    __tablename__ = "user_tombstones"
    phone_number: Mapped[str] = mapped_column(primary_key=True)
    opted_out_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_keyword: Mapped[Optional[str]]

class Course(Base):
    __tablename__ = "courses"
    code: Mapped[str] = mapped_column(primary_key=True)         # 'MTH102'
    title: Mapped[str]
    level: Mapped[int]
    department: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)

class Paper(Base):
    __tablename__ = "papers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.code"), index=True)
    course_title: Mapped[Optional[str]]
    exam_session: Mapped[Optional[str]]                          # 'CA1' | 'CA2' | 'exam' | NULL
    semester: Mapped[str]                                        # 'harmattan' | 'rain'
    year: Mapped[int]
    object_key: Mapped[str]
    gcs_object = synonym("object_key")
    served_object_key: Mapped[Optional[str]]
    served_object = synonym("served_object_key")
    sha256: Mapped[str] = mapped_column(unique=True)
    uploaded_by: Mapped[str]
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_active_risk: Mapped[bool] = mapped_column(default=False)
    held_until: Mapped[Optional[datetime]]
    pdf_was_generated: Mapped[bool] = mapped_column(default=False)
    is_retired: Mapped[bool] = mapped_column(default=False)
    retired_by: Mapped[Optional[str]]
    retired_at: Mapped[Optional[datetime]]
    retired_reason: Mapped[Optional[str]]
    __table_args__ = (UniqueConstraint("course_code", "semester", "year"),)

class PaperChunk(Base):
    __tablename__ = "paper_chunks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    chunk_no: Mapped[int]
    chunk_kind: Mapped[str] = mapped_column(default='question')
    text: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    __table_args__ = (UniqueConstraint("paper_id", "chunk_no"),)

class PendingPaper(Base):
    __tablename__ = "pending_papers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.code"))
    course_title: Mapped[Optional[str]]
    semester: Mapped[str]
    exam_session: Mapped[Optional[str]]
    year: Mapped[int]
    object_key: Mapped[str]
    gcs_object = synonym("object_key")
    sha256: Mapped[str] = mapped_column(unique=True)
    uploaded_by: Mapped[str]
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_active_risk: Mapped[bool] = mapped_column(default=False)
    held_until: Mapped[Optional[datetime]]
    pdf_was_generated: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(default='drive_import')
    review_status: Mapped[str] = mapped_column(default='awaiting_review', index=True)
    reviewer: Mapped[Optional[str]]
    reviewed_at: Mapped[Optional[datetime]]
    review_notes: Mapped[Optional[str]]
    __table_args__ = (UniqueConstraint("course_code", "semester", "year", "exam_session"),)

class PendingPaperChunk(Base):
    __tablename__ = "pending_paper_chunks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pending_paper_id: Mapped[int] = mapped_column(ForeignKey("pending_papers.id", ondelete="CASCADE"))
    chunk_no: Mapped[int]
    chunk_kind: Mapped[str] = mapped_column(default='question')
    text: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    __table_args__ = (UniqueConstraint("pending_paper_id", "chunk_no"),)

class RequestLog(Base):
    __tablename__ = "request_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wa_message_id: Mapped[str] = mapped_column(unique=True, index=True)
    wa_from: Mapped[str]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    user_text: Mapped[str]
    routed_course: Mapped[Optional[str]]
    routed_year: Mapped[Optional[int]]
    routed_semester: Mapped[Optional[str]]
    matched_paper_id: Mapped[Optional[int]] = mapped_column(ForeignKey("papers.id"), nullable=True)
    outcome: Mapped[str] = mapped_column(index=True) # indexed for rate limit counting
    flash_input_tokens: Mapped[Optional[int]]
    flash_output_tokens: Mapped[Optional[int]]
    error: Mapped[Optional[str]]

class Uploader(Base):
    __tablename__ = "uploaders"
    phone_number: Mapped[str] = mapped_column(primary_key=True)
    display_name: Mapped[Optional[str]]
    added_by: Mapped[str]
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    revoked_at: Mapped[Optional[datetime]]
    revoke_reason: Mapped[Optional[str]]

class ImageBatch(Base):
    __tablename__ = "image_batches"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(index=True)
    pending_paper_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pending_papers.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(default='open')
    opened_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_item_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    sealed_at: Mapped[Optional[datetime]]
    failure_reason: Mapped[Optional[str]]

class ImageBatchItem(Base):
    __tablename__ = "image_batch_items"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("image_batches.id", ondelete="CASCADE"))
    wa_media_id: Mapped[str]
    wa_message_id: Mapped[str] = mapped_column(unique=True)
    object_key: Mapped[str]
    gcs_object = synonym("object_key")
    mime_type: Mapped[str]
    sha256: Mapped[str]
    ord: Mapped[int]
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    __table_args__ = (UniqueConstraint("batch_id", "ord"),)

class IntakeNotification(Base):
    __tablename__ = "intake_notifications"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone_number: Mapped[str]
    body: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sent_at: Mapped[Optional[datetime]]
