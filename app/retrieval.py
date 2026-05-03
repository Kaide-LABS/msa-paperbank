from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func
from app.db import Paper, PaperChunk
from app.config import settings
from app import embeddings
from google.cloud import storage

def find_paper(session: Session, course_code: str, year: int | None, semester: str | None) -> Paper | None:
    if not course_code or course_code.upper() != settings.hardcoded_course_code.upper():
        return None
        
    query = select(Paper).where(Paper.course_code.ilike(course_code))
    
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
) -> Paper | None:
    if not course_code or course_code.upper() != settings.hardcoded_course_code.upper():
        return None

    qvec = embeddings.embed_query(query_text)
    
    stmt = (
        select(Paper)
        .join(PaperChunk, PaperChunk.paper_id == Paper.id)
        .where(Paper.course_code.ilike(course_code))
        .where(
            or_(
                Paper.is_active_risk == False,
                Paper.held_until == None,
                Paper.held_until <= func.current_date()
            )
        )
        .order_by(PaperChunk.embedding.cosine_distance(qvec))
        .limit(top_k or settings.semantic_fallback_top_k)
    )
    return session.execute(stmt).scalars().first()

def load_pdf_bytes(paper: Paper, gcs_client: storage.Client, bucket_name: str) -> tuple[bytes, str]:
    bucket = gcs_client.bucket(bucket_name)
    blob = bucket.blob(paper.gcs_object)
    pdf_bytes = blob.download_as_bytes()
    filename = f"{paper.course_code}_{paper.semester}_{paper.year}.pdf"
    return pdf_bytes, filename