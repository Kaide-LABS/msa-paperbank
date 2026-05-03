import os
import sys
from datetime import datetime, timezone
from sqlalchemy import select, func
from app.db import SessionLocal, PendingPaper, PendingPaperChunk, Paper, PaperChunk
from google.cloud import storage
from app.config import settings

def main():
    gcs_client = storage.Client(project=settings.gcp_project)
    bucket = gcs_client.bucket(settings.gcs_bucket)
    user = os.environ.get("USER", "ibrahim")
    
    while True:
        with SessionLocal() as session:
            # Refresh queue size
            queue_size = session.execute(
                select(func.count(PendingPaper.id))
                .where(PendingPaper.review_status == 'awaiting_review')
            ).scalar()
            
            if queue_size == 0:
                print("Queue empty.")
                sys.exit(0)
                
            # Get next pending paper
            pending = session.execute(
                select(PendingPaper)
                .where(PendingPaper.review_status == 'awaiting_review')
                .order_by(PendingPaper.uploaded_at.asc())
                .limit(1)
            ).scalar_one_or_none()
            
            if not pending:
                print("Queue empty.")
                sys.exit(0)
                
            # Get chunks
            chunks = session.execute(
                select(PendingPaperChunk)
                .where(PendingPaperChunk.pending_paper_id == pending.id)
                .order_by(PendingPaperChunk.chunk_no.asc())
            ).scalars().all()
            
            print(f"\n[{1}/{queue_size}] pending_paper_id={pending.id}")
            print(f"course={pending.course_code} year={pending.year} session={pending.exam_session} source={pending.source}")
            print(f"gcs_object={pending.gcs_object} chunks={len(chunks)}")
            print("Preview:")
            for c in chunks[:3]:
                print(f"  Q{c.chunk_no}: {c.text[:120]}...")
                
            action = input("\nAction [a/r/d/v/s/q]: ").strip().lower()
            
            if action == 'q':
                print("Saved progress.")
                sys.exit(0)
                
            elif action == 's':
                continue
                
            elif action == 'v':
                print("\n--- FULL TEXT ---")
                for c in chunks:
                    print(f"Q{c.chunk_no}:\n{c.text}\n")
                print("-----------------")
                continue
                
            elif action == 'd':
                reason = input("Defer reason: ")
                pending.review_status = 'deferred'
                pending.review_notes = reason
                session.commit()
                
            elif action == 'r':
                reason = input("Reject reason (required): ")
                if not reason:
                    print("Reason is required for rejection.")
                    continue
                pending.review_status = 'rejected'
                pending.reviewer = user
                pending.reviewed_at = datetime.now(timezone.utc)
                pending.review_notes = reason
                session.commit()
                try:
                    bucket.blob(pending.gcs_object).delete()
                except Exception as e:
                    print(f"Warning: failed to delete blob {pending.gcs_object}: {e}")
                    
            elif action == 'a':
                reason = input("Approve reason (optional): ")
                now_dt = datetime.now(timezone.utc)
                
                new_paper = Paper(
                    course_code=pending.course_code,
                    course_title=pending.course_title,
                    semester=pending.semester,
                    exam_session=pending.exam_session,
                    year=pending.year,
                    gcs_object=pending.gcs_object,
                    sha256=pending.sha256,
                    uploaded_by=pending.uploaded_by,
                    uploaded_at=pending.uploaded_at,
                    is_active_risk=pending.is_active_risk,
                    held_until=pending.held_until,
                    pdf_was_generated=pending.pdf_was_generated
                )
                session.add(new_paper)
                session.flush()
                
                new_chunks = []
                for c in chunks:
                    new_chunks.append(PaperChunk(
                        paper_id=new_paper.id,
                        chunk_no=c.chunk_no,
                        chunk_kind=c.chunk_kind,
                        text=c.text,
                        embedding=c.embedding,
                        created_at=c.created_at
                    ))
                session.add_all(new_chunks)
                
                pending.review_status = 'approved'
                pending.reviewer = user
                pending.reviewed_at = now_dt
                pending.review_notes = reason
                session.commit()
                print(f"Approved. Created paper_id={new_paper.id}")

if __name__ == "__main__":
    main()