import time
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func
from pgvector.sqlalchemy import Vector
from app.db import Paper, PaperChunk, Course
from app.config import settings
from app import embeddings
from google.cloud import storage

_courses_cache = None
_courses_cache_time = 0

def known_courses(session: Session) -> set[str]:
    global _courses_cache, _courses_cache_time
    now = time.time()
    if _courses_cache is not None and (now - _courses_cache_time) < settings.course_catalog_cache_seconds:
        return _courses_cache

    rows = session.execute(select(Course.code).where(Course.is_active == True)).scalars().all()
    _courses_cache = {c.upper() for c in rows}
    _courses_cache_time = now
    return _courses_cache

def nearest_courses(session: Session, query_code: str, limit: int) -> list[str]:
    stmt = (
        select(Course.code)
        .where(Course.is_active == True)
        .order_by(func.similarity(Course.code, query_code).desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())

def find_paper(session: Session, course_code: str, year: int | None, semester: str | None) -> Paper | None:
    query = select(Paper).where(Paper.course_code.ilike(course_code))
    
    # Phase 3: exclude retired papers
    query = query.where(Paper.is_retired == False)

    # Soft active-risk filter
    query = query.where(
        or_(
            Paper.is_active_risk == False,
            Paper.held_until == None,
            Paper.held_until <= func.current_date()
        )
    )

    if year is not None:
        query = query.where(Paper.year == year)
    if semester is not None:
        query = query.where(Paper.semester.ilike(semester))

    query = query.order_by(Paper.year.desc()).limit(1)
    return session.execute(query).scalar_one_or_none()

def find_paper_by_semantic_query(
    session: Session,
    course_code: str,
    query_text: str,
    top_k: int | None = None,
    prefer_courses: list[str] | None = None,
) -> Paper | None:
    qvec = embeddings.embed_query(query_text)
    
    limit_k = top_k or settings.semantic_fallback_top_k
    fetch_k = limit_k * 2 if prefer_courses else limit_k

    stmt = (
        select(Paper, PaperChunk.embedding.cosine_distance(qvec).label("distance"))
        .join(PaperChunk, PaperChunk.paper_id == Paper.id)
        .where(Paper.course_code.ilike(course_code))
        .where(Paper.is_retired == False)
        .where(
            or_(
                Paper.is_active_risk == False,
                Paper.held_until == None,
                Paper.held_until <= func.current_date()
            )
        )
        .order_by(text("distance"))
        .limit(fetch_k)
    )
    results = session.execute(stmt).all()
    if not results:
        return None
        
    if not prefer_courses:
        return results[0][0]
        
    best_dist = results[0][1]
    
    for paper, dist in results:
        if paper.course_code in prefer_courses and (dist - best_dist) <= settings.personalization_tie_band:
            return paper
            
    return results[0][0]

def load_pdf_bytes(paper: Paper, gcs_client: storage.Client, bucket_name: str) -> tuple[bytes, str]:
    bucket = gcs_client.bucket(bucket_name)
    blob = bucket.blob(paper.gcs_object)
    pdf_bytes = blob.download_as_bytes()
    filename = f"{paper.course_code}_{paper.semester}_{paper.year}.pdf"
    return pdf_bytes, filename