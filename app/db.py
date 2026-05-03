import os
from datetime import datetime
from typing import Optional
from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine, BigInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from app.config import settings

# Test DB URL hook for pytest
TEST_DB_URL = os.environ.get("DATABASE_URL_TEST")

connector = None

def getconn():
    global connector
    if connector is None:
        connector = Connector()
    return connector.connect(
        settings.cloud_sql_instance,
        "psycopg",
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
        db=settings.db_name,
    )

if TEST_DB_URL:
    engine = create_engine(TEST_DB_URL, pool_size=2, max_overflow=2, pool_pre_ping=True)
else:
    engine = create_engine("postgresql+psycopg://", creator=getconn, pool_size=2, max_overflow=2, pool_pre_ping=True, pool_recycle=1800)

SessionLocal = sessionmaker(engine, expire_on_commit=False, autoflush=False)

def dispose() -> None:
    global connector
    engine.dispose()
    if connector is not None:
        connector.close()
        connector = None

class Base(DeclarativeBase):
    pass

class Course(Base):
    __tablename__ = "courses"
    code: Mapped[str] = mapped_column(primary_key=True)         # 'MTH102'
    title: Mapped[str]
    level: Mapped[int]
    department: Mapped[str]

class Paper(Base):
    __tablename__ = "papers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.code"), index=True)
    semester: Mapped[str]                                        # 'harmattan' | 'rain'
    year: Mapped[int]
    gcs_object: Mapped[str]
    sha256: Mapped[str] = mapped_column(unique=True)
    uploaded_by: Mapped[str]
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_quarantined: Mapped[bool] = mapped_column(default=False) # Anti-Replication mechanism
    __table_args__ = (UniqueConstraint("course_code", "semester", "year"),)

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