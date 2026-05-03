import argparse
import hashlib
import os
import sys
from google.cloud import storage
from sqlalchemy import select
from app.db import SessionLocal, Paper
from app.config import settings

def main():
    parser = argparse.ArgumentParser(description="Upload a past paper (Phase 1: MTH102 only).")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--year", type=int, required=True, help="Year of the exam (e.g., 2022)")
    parser.add_argument("--semester", choices=["harmattan", "rain"], required=True, help="Semester")
    
    args = parser.parse_args()
    
    with open(args.pdf_path, "rb") as f:
        pdf_bytes = f.read()
        
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()

    with SessionLocal() as session:
        existing = session.execute(select(Paper).where(Paper.sha256 == sha256)).scalar_one_or_none()
        if existing:
            print(f"Paper already exists: ID={existing.id}")
            sys.exit(0)
            
        gcs_object = f"papers/MTH102/{args.year}-{args.semester}.pdf"
        
        # Upload to GCS
        print(f"Uploading to gs://{settings.gcs_bucket}/{gcs_object} ...")
        client = storage.Client(project=settings.gcp_project)
        bucket = client.bucket(settings.gcs_bucket)
        blob = bucket.blob(gcs_object)
        blob.upload_from_string(pdf_bytes, content_type="application/pdf")
        
        # Insert DB row
        new_paper = Paper(
            course_code="MTH102",
            semester=args.semester,
            year=args.year,
            gcs_object=gcs_object,
            sha256=sha256,
            uploaded_by=os.environ.get("USER", "ibrahim"),
        )
        session.add(new_paper)
        session.commit()

        print(f"Uploaded successfully! Paper ID: {new_paper.id}")

if __name__ == "__main__":
    main()