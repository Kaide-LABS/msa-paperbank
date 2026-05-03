from typing import Iterator
from sqlalchemy.orm import Session
from app.db import SessionLocal

def get_session() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()