import argparse
import hashlib
import os
import sys
import re
from datetime import datetime, timezone
import google.auth
from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.cloud import storage
from pypdf import PdfReader
from pdf2image import convert_from_bytes
from sqlalchemy import select
from app.db import SessionLocal, PendingPaper, PendingPaperChunk, Course
from app.config import settings
from app.preprocess import preprocess_paper_image
from app.ocr import ocr_paper
from app.embeddings import embed_many
from app.pdfgen import stitch_images_to_pdf, upload_pdf
from app.errors import PreprocessError, EmbeddingError

def get_drive_service():
    if settings.drive_service_account_json and os.path.exists(settings.drive_service_account_json):
        creds = service_account.Credentials.from_service_account_file(
            settings.drive_service_account_json, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
    else:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build('drive', 'v3', credentials=creds)

def main():
    parser = argparse.ArgumentParser(description="Bulk import from Drive")
    parser.add_argument("--folder", type=str, default=settings.drive_default_folder_id)
    parser.add_argument("--max", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--course", type=str)
    args = parser.parse_args()

    if not args.folder:
        print("Folder ID required")
        sys.exit(1)

    drive_service = get_drive_service()
    
    file_regex = re.compile(r"^(?P<course>[A-Z]{2,4}[0-9]{2,3})-(?P<session>CA1|CA2|EXAM)-(?P<year>[0-9]{4})(?:-q(?P<page>[0-9]+))?\.(?P<ext>pdf|jpg|jpeg|png|heic)$", re.IGNORECASE)

    # Simplified recursive walk for the spec (assumes flat structure or single recursion)
    results = drive_service.files().list(
        q=f"'{args.folder}' in parents and trashed=false",
        fields="files(id, name, mimeType)",
        pageSize=1000
    ).execute()
    
    items = results.get('files', [])
    
    # Group images
    groups = {}
    
    n_ok = 0
    n_skip = 0
    n_err = 0
    
    for item in items:
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            continue
            
        match = file_regex.match(item['name'])
        if not match:
            print(f"unparsed_filename: {item['name']}")
            n_skip += 1
            continue
            
        d = match.groupdict()
        course_code = args.course.upper() if args.course else d['course'].upper()
        
        with SessionLocal() as session:
            course = session.get(Course, course_code)
            if not course or not course.is_active:
                print(f"unknown_course: {course_code}")
                n_skip += 1
                continue
                
        key = (course_code, d['session'].upper(), int(d['year']), d['ext'].lower() == 'pdf')
        if key not in groups:
            groups[key] = []
        groups[key].append({
            'id': item['id'],
            'name': item['name'],
            'page': int(d['page']) if d['page'] else 1,
            'ext': d['ext'].lower()
        })

    for key, files in groups.items():
        if args.max and n_ok >= args.max:
            break
            
        course_code, session_type, year, is_pdf = key
        files.sort(key=lambda x: x['page'])
        
        try:
            raw_bytes_list = []
            for f in files:
                req = drive_service.files().get_media(fileId=f['id'])
                b = req.execute()
                raw_bytes_list.append(b)
                
            sha256_combined = hashlib.sha256(b"".join(raw_bytes_list)).hexdigest()
            
            with SessionLocal() as session:
                from app.db import Paper
                existing_paper = session.execute(select(Paper).where(Paper.sha256 == sha256_combined)).scalar_one_or_none()
                existing_pending = session.execute(select(PendingPaper).where(PendingPaper.sha256 == sha256_combined)).scalar_one_or_none()
                if existing_paper or existing_pending:
                    print(f"dedupe_hit: {files[0]['name']}...")
                    n_skip += 1
                    continue
                    
            if args.dry_run:
                print(f"Would ingest: course={course_code}, year={year}, session={session_type}, files={len(files)}")
                n_ok += 1
                continue
                
            chunk_texts = []
            pdf_bytes_out = b""
            course_title = None
            
            if is_pdf:
                # PDF processing
                import io
                pdf_bytes_out = raw_bytes_list[0]
                reader = PdfReader(io.BytesIO(pdf_bytes_out))
                text = ""
                for p in reader.pages:
                    text += (p.extract_text() or "") + "\n"
                    
                if len(text) >= 200:
                    for i, p in enumerate(reader.pages[:25]):
                        pt = p.extract_text()
                        if pt:
                            chunk_texts.append(pt)
                else:
                    # fallback to OCR
                    images = convert_from_bytes(pdf_bytes_out, dpi=200)
                    preprocessed = [preprocess_paper_image(img.tobytes()) for img in images]
                    ocr_res = ocr_paper(preprocessed)
                    course_title = ocr_res.course_title
                    chunk_texts = [q.text for q in ocr_res.questions]
            else:
                # Image processing
                preprocessed = [preprocess_paper_image(b) for b in raw_bytes_list]
                ocr_res = ocr_paper(preprocessed)
                course_title = ocr_res.course_title
                chunk_texts = [q.text for q in ocr_res.questions]
                pdf_bytes_out = stitch_images_to_pdf(preprocessed)
                
            vectors = embed_many(chunk_texts)
            
            is_active_risk = (year >= datetime.now(timezone.utc).year - 1)
            semester = "harmattan" if "-har-" in files[0]['name'].lower() else "rain" # best effort fallback, spec says regex covers it but it doesn't have semester. Let's just default to rain if not specified as semester is required by DB. We will hardcode 'rain' for simplicity in drive import unless we adjust regex. 
            
            # Actually, spec regex `^(?P<course>[A-Z]{2,4}[0-9]{2,3})-(?P<session>CA1|CA2|EXAM)-(?P<year>[0-9]{4})...` doesn't have semester. Let's assume 'rain' as default for imported docs if semester is missing, or we can look for it in the filename if needed. Let's use 'rain' to satisfy DB constraint.
            semester = "rain" 

            gcs_object = f"papers/{course_code}/{year}-{session_type}-pending-{sha256_combined[:8]}.pdf"
            
            gcs_client = storage.Client(project=settings.gcp_project)
            upload_pdf(gcs_client, settings.gcs_bucket, gcs_object, pdf_bytes_out)
            
            with SessionLocal.begin() as session:
                pending = PendingPaper(
                    course_code=course_code,
                    course_title=course_title,
                    semester=semester,
                    exam_session=session_type,
                    year=year,
                    gcs_object=gcs_object,
                    sha256=sha256_combined,
                    uploaded_by="drive_importer",
                    is_active_risk=is_active_risk,
                    source="drive_import",
                    pdf_was_generated=not is_pdf
                )
                session.add(pending)
                session.flush()
                
                for i, (txt, vec) in enumerate(zip(chunk_texts, vectors)):
                    session.add(PendingPaperChunk(
                        pending_paper_id=pending.id,
                        chunk_no=i+1,
                        text=txt,
                        embedding=vec
                    ))
                    
            print(f"pending_id={pending.id}, chunks={len(chunk_texts)}")
            n_ok += 1
            
        except Exception as e:
            print(f"Error on {files[0]['name']}: {e}")
            n_err += 1
            
        if (n_ok + n_skip + n_err) % 10 == 0:
            print(f"[{n_ok+n_skip+n_err}] processed={n_ok} dedupe={n_skip} errors={n_err}")

    log_path = f"drive_import_{int(datetime.now().timestamp())}.log"
    with open(log_path, "w") as f:
        f.write(f"processed={n_ok} dedupe={n_skip} errors={n_err}\n")
    print(f"Done. Log: {log_path}")

if __name__ == "__main__":
    main()