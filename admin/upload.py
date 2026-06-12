import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from google.cloud import storage
from sqlalchemy import select
from app.db import SessionLocal, Paper, PaperChunk, PendingPaper, PendingPaperChunk, Course
from app.config import settings
from app.preprocess import prepare_images_for_ocr
from app.ocr import ocr_paper
from app.embeddings import embed_many
from app.pdfgen import stitch_images_to_pdf, upload_pdf
from app.errors import PreprocessError, EmbeddingError

def _validate_course(session, code):
    course = session.get(Course, code)
    if not course or not course.is_active:
        print(f"course not found in catalog; run admin courses add")
        sys.exit(1)

def upload_pdf_cmd(args):
    code = args.course.upper()
    with open(args.pdf_path, "rb") as f:
        pdf_bytes = f.read()
        
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    is_active_risk = (args.year >= datetime.now(timezone.utc).year - 1)
    
    held_until = None
    if args.held_until:
        held_until = datetime.strptime(args.held_until, "%Y-%m-%d").date()
    
    with SessionLocal() as session:
        _validate_course(session, code)
        existing = session.execute(select(Paper).where(Paper.sha256 == sha256)).scalar_one_or_none()
        if existing:
            print(f"Paper already exists: ID={existing.id}")
            sys.exit(0)
            
        gcs_object = f"papers/{code}/{args.year}-{args.semester}-{args.session or 'exam'}.pdf"
        
        print(f"Uploading to gs://{settings.gcs_bucket}/{gcs_object} ...")
        client = storage.Client(project=settings.gcp_project)
        upload_pdf(client, settings.gcs_bucket, gcs_object, pdf_bytes)
        
        new_paper = Paper(
            course_code=code,
            semester=args.semester,
            year=args.year,
            exam_session=args.session,
            gcs_object=gcs_object,
            sha256=sha256,
            uploaded_by=os.environ.get("USER", "ibrahim"),
            is_active_risk=is_active_risk,
            held_until=held_until,
            pdf_was_generated=False
        )
        session.add(new_paper)
        session.commit()
        
        print(f"Uploaded successfully! Paper ID: {new_paper.id}")
        if is_active_risk:
            print("Note: marked is_active_risk=TRUE.")

def upload_images_cmd(args):
    code = args.course.upper()
    if not (1 <= len(args.images) <= settings.ocr_max_images_per_paper):
        print(f"Must provide 1 to {settings.ocr_max_images_per_paper} images.")
        sys.exit(1)
        
    raw_bytes_list = []
    for p in args.images:
        size = os.path.getsize(p)
        if size > settings.ocr_max_image_bytes:
            print(f"Image {p} too large: {size} bytes.")
            sys.exit(1)
        with open(p, "rb") as f:
            raw_bytes_list.append(f.read())
            
    sha256_combined = hashlib.sha256(b"".join(raw_bytes_list)).hexdigest()
    
    with SessionLocal() as session:
        _validate_course(session, code)
        existing = session.execute(select(PendingPaper).where(PendingPaper.sha256 == sha256_combined)).scalar_one_or_none()
        if existing:
            print(f"Pending paper already exists: ID={existing.id}")
            sys.exit(0)

    # Decision 2: preprocessing off by default; raw images go straight to OCR.
    try:
        images = prepare_images_for_ocr(raw_bytes_list)
    except PreprocessError as e:
        print(f"Preprocess error: {e}")
        sys.exit(2)

    if not args.no_ocr:
        ocr_result = ocr_paper(images)
        if ocr_result.error is not None or not ocr_result.questions:
            print(f"OCR empty or error: {ocr_result.error}")
            sys.exit(3)
            
    is_active_risk = (args.year >= datetime.now(timezone.utc).year - 1)
    held_until = None
    if args.held_until:
        held_until = datetime.strptime(args.held_until, "%Y-%m-%d").date()
    
    pdf_bytes = stitch_images_to_pdf(images)
    
    gcs_object = f"papers/{code}/{args.year}-{args.semester}-{args.session or 'exam'}.pdf"
    
    client = storage.Client(project=settings.gcp_project)
    bucket = client.bucket(settings.gcs_bucket)
    if bucket.blob(gcs_object).exists():
        gcs_object = f"papers/{code}/{args.year}-{args.semester}-{args.session or 'exam'}-{sha256_combined[:8]}.pdf"
        
    upload_pdf(client, settings.gcs_bucket, gcs_object, pdf_bytes)
    
    try:
        vectors = []
        if not args.no_ocr:
            vectors = embed_many([q.text for q in ocr_result.questions])
            
        with SessionLocal.begin() as session:
            paper = PendingPaper(
                course_code=code,
                course_title=ocr_result.course_title if not args.no_ocr else None,
                semester=args.semester,
                exam_session=args.session,
                year=args.year,
                gcs_object=gcs_object,
                sha256=sha256_combined,
                uploaded_by=os.environ.get("USER", "ibrahim"),
                is_active_risk=is_active_risk,
                held_until=held_until,
                pdf_was_generated=True,
                source='cli_images'
            )
            session.add(paper)
            session.flush()
            if not args.no_ocr:
                session.add_all([
                    PendingPaperChunk(pending_paper_id=paper.id, chunk_no=i+1, text=q.text, embedding=vec)
                    for i, (q, vec) in enumerate(zip(ocr_result.questions, vectors))
                ])
                
        print(f"Uploaded to curation queue! pending_id={paper.id}, chunks={len(ocr_result.questions) if not args.no_ocr else 0}")
        if is_active_risk:
            print("Note: marked is_active_risk=TRUE.")
            
    except EmbeddingError as e:
        print(f"Embedding failed: {e}")
        bucket.blob(gcs_object).delete()
        sys.exit(4)
    except Exception as e:
        print(f"Insert failed: {e}")
        bucket.blob(gcs_object).delete()
        raise e

def main():
    parser = argparse.ArgumentParser(description="Upload a past paper to MSA Paperbank.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    
    # PDF subparser
    parser_pdf = subparsers.add_parser("pdf", help="Upload a single PDF file (no OCR/embeddings)")
    parser_pdf.add_argument("pdf_path", help="Path to the PDF file")
    parser_pdf.add_argument("--course", type=str, required=True, help="Course code")
    parser_pdf.add_argument("--year", type=int, required=True, help="Year of the exam (e.g., 2022)")
    parser_pdf.add_argument("--semester", choices=["harmattan", "rain"], required=True, help="Semester")
    parser_pdf.add_argument("--session", choices=["CA1", "CA2", "exam"], help="Exam session")
    parser_pdf.add_argument("--held-until", type=str, help="YYYY-MM-DD")
    
    # Images subparser
    parser_img = subparsers.add_parser("images", help="Upload images to curation queue")
    parser_img.add_argument("images", nargs="+", help="Paths to image files")
    parser_img.add_argument("--course", type=str, required=True, help="Course code")
    parser_img.add_argument("--year", type=int, required=True, help="Year of the exam")
    parser_img.add_argument("--semester", choices=["harmattan", "rain"], required=True, help="Semester")
    parser_img.add_argument("--session", choices=["CA1", "CA2", "exam"], help="Exam session")
    parser_img.add_argument("--no-ocr", action="store_true", help="Skip OCR and embeddings")
    parser_img.add_argument("--held-until", type=str, help="YYYY-MM-DD")
    
    args = parser.parse_args()
    
    if args.subcommand == "pdf":
        upload_pdf_cmd(args)
    elif args.subcommand == "images":
        upload_images_cmd(args)

if __name__ == "__main__":
    main()