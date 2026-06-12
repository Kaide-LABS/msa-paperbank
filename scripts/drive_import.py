import argparse
import hashlib
import io
import os
import sys
import re
from datetime import datetime, timezone
import google.auth
from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.cloud import storage
from pypdf import PdfReader
from sqlalchemy import select
from app.db import SessionLocal, PendingPaper, PendingPaperChunk, Course
from app.config import settings
from app.preprocess import prepare_images_for_ocr
from app.ocr import ocr_paper
from app.paper_splitter import split_pdf_pages, rasterize_pdf_to_pngs
from app.embeddings import embed_many
from app.pdfgen import stitch_images_to_pdf, upload_pdf
from app.errors import PreprocessError, EmbeddingError


def _map_session_hint(hint):
    """Map a PageBoundaryProbe.session_hint ("CA"|"exam"|None) onto the importer's session
    vocabulary. "CA" stays generic (a curator refines CA1 vs CA2); these are pending papers."""
    if hint == "exam":
        return "EXAM"
    if hint == "CA":
        return "CA"
    return None


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
    
    # Filename convention: <COURSE>-<HAR|RAIN>-<SESSION>-<YEAR>[-q<N>].<ext>
    file_regex = re.compile(
        r"^(?P<course>[A-Z]{2,4}[0-9]{2,3})-(?P<sem>HAR|RAIN)-(?P<session>CA1|CA2|EXAM)-(?P<year>[0-9]{4})(?:-q(?P<page>[0-9]+))?\.(?P<ext>pdf|jpg|jpeg|png|heic)$",
        re.IGNORECASE,
    )
    SEM_MAP = {"HAR": "harmattan", "RAIN": "rain"}

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
                
        sem = SEM_MAP[d['sem'].upper()]
        key = (course_code, sem, d['session'].upper(), int(d['year']), d['ext'].lower() == 'pdf')
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
            
        course_code, semester, session_type, year, is_pdf = key
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
                
            # A bundle may split into several constituent papers; each becomes a "unit".
            # unit = dict(chunk_texts, course_title, pdf_bytes, sha, exam_session, pdf_was_generated)
            paper_units = []

            if is_pdf:
                pdf_bytes_out = raw_bytes_list[0]
                reader = PdfReader(io.BytesIO(pdf_bytes_out))
                text = ""
                for p in reader.pages:
                    text += (p.extract_text() or "") + "\n"

                if len(text) >= 200:
                    # Digital text layer: treat as a single paper; store the original PDF.
                    chunk_texts = []
                    for p in reader.pages[:25]:
                        pt = p.extract_text()
                        if pt:
                            chunk_texts.append(pt)
                    paper_units.append(dict(
                        chunk_texts=chunk_texts, course_title=None,
                        pdf_bytes=pdf_bytes_out, sha=sha256_combined,
                        exam_session=session_type, pdf_was_generated=False))
                else:
                    # Scanned PDF: rasterize (pypdfium2 — no poppler) -> (preprocess off) ->
                    # SPLIT into constituent papers (Decision B), then OCR each paper on its own.
                    page_pngs = rasterize_pdf_to_pngs(pdf_bytes_out)
                    page_imgs = prepare_images_for_ocr(page_pngs)
                    groups = split_pdf_pages(page_imgs)
                    multi = len(groups) > 1
                    for gi, group in enumerate(groups):
                        ocr_res = ocr_paper(group.images)
                        # The paper's own header overrides the filename's single session_type —
                        # the whole point of splitting CA-vs-Examination bundles.
                        grp_session = _map_session_hint(group.session_hint) or session_type
                        grp_pdf = stitch_images_to_pdf(group.images)
                        # Per-paper hash so each sub-paper dedupes independently; a single-paper
                        # PDF keeps the original combined hash (dedupe behavior unchanged).
                        grp_sha = sha256_combined if not multi else hashlib.sha256(
                            b"".join(group.images) + str(gi).encode()).hexdigest()
                        paper_units.append(dict(
                            chunk_texts=[q.text for q in ocr_res.questions],
                            course_title=ocr_res.course_title,
                            pdf_bytes=grp_pdf, sha=grp_sha,
                            exam_session=grp_session, pdf_was_generated=True))
            else:
                # Image group: single paper.
                # Decision 2: preprocessing off by default; raw images straight to OCR.
                page_imgs = prepare_images_for_ocr(raw_bytes_list)
                ocr_res = ocr_paper(page_imgs)
                paper_units.append(dict(
                    chunk_texts=[q.text for q in ocr_res.questions],
                    course_title=ocr_res.course_title,
                    pdf_bytes=stitch_images_to_pdf(page_imgs), sha=sha256_combined,
                    exam_session=session_type, pdf_was_generated=True))

            is_active_risk = (year >= datetime.now(timezone.utc).year - 1)
            # `semester` already came from the filename regex via the group key.

            for unit in paper_units:
                vectors = embed_many(unit["chunk_texts"])
                gcs_object = f"papers/{course_code}/{year}-{semester}-{unit['exam_session']}-pending-{unit['sha'][:8]}.pdf"

                gcs_client = storage.Client(project=settings.gcp_project)
                upload_pdf(gcs_client, settings.gcs_bucket, gcs_object, unit["pdf_bytes"])

                with SessionLocal.begin() as session:
                    pending = PendingPaper(
                        course_code=course_code,
                        course_title=unit["course_title"],
                        semester=semester,
                        exam_session=unit["exam_session"],
                        year=year,
                        gcs_object=gcs_object,
                        sha256=unit["sha"],
                        uploaded_by="drive_importer",
                        is_active_risk=is_active_risk,
                        source="drive_import",
                        pdf_was_generated=unit["pdf_was_generated"]
                    )
                    session.add(pending)
                    session.flush()

                    for i, (txt, vec) in enumerate(zip(unit["chunk_texts"], vectors)):
                        session.add(PendingPaperChunk(
                            pending_paper_id=pending.id,
                            chunk_no=i+1,
                            text=txt,
                            embedding=vec
                        ))

                print(f"pending_id={pending.id}, chunks={len(unit['chunk_texts'])}, session={unit['exam_session']}")
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