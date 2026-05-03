import pytest
import os
from sqlalchemy.orm import Session
from app.db import SessionLocal, Base, engine

@pytest.fixture(scope="session")
def setup_database():
    if not os.environ.get("DATABASE_URL_TEST"):
        pytest.skip("DATABASE_URL_TEST not set, skipping DB tests")
        
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    from app.db import Course
    with SessionLocal() as session:
        session.add(Course(code="MTH102", title="General Math", level=100, department="Math"))
        session.commit()
        
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(setup_database):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()