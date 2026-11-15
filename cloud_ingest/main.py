# -*- coding: utf-8 -*-
"""Cloud Run JOB entrypoint — corpus ingest.

Reads all objects under GCS_PREFIX, runs the REAL pipeline
(rasterize[pypdfium2] -> prepare_images_for_ocr[off] -> split_pdf_pages[masthead] ->
dual-read OCR[Flash+Pro, thinking_budget=0] -> compare_reads), and writes one row per paper to
a self-contained `pending_papers` table on the target Cloud SQL instance, tagged with SOURCE_TAG.
Auth = ADC + Vertex (no API keys). Idempotent by per-paper sha.

SCOPE: processes objects under GCS_PREFIX only. MAX_FILES>0 caps to an even-strided sample
(canary); MAX_FILES=0 processes the full prefix. STUDENT_VISIBLE sets the ship-everything flag.
Invoked MANUALLY only (no trigger/schedule) — the full run fires solely on an explicit execute.
"""
import os, io, sys, json, time, hashlib, traceback, concurrent.futures as cf

# --- env / config (set by the Cloud Run Job; dummies satisfy app.config.Settings) ---
PROJECT = os.environ["GCP_PROJECT"]
LOCATION = os.environ.get("GCP_LOCATION", "global")
GCS_BUCKET = os.environ["GCS_BUCKET"]
GCS_PREFIX = os.environ["GCS_PREFIX"]                     # e.g. "cloud_test_batch/"
SOURCE_TAG = os.environ.get("SOURCE_TAG", "cloud_test")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "3"))
INSTANCE_CONN = os.environ["INSTANCE_CONNECTION_NAME"]    # project:region:instance
DB_USER = os.environ.get("DB_USER", "ingest")
DB_PASS = os.environ["DB_PASS"]
DB_NAME = os.environ.get("DB_NAME", "paperbank_test")
MAX_FILES = int(os.environ.get("MAX_FILES", "0"))        # 0 = all under prefix; >0 = canary cap (even sample)
STUDENT_VISIBLE = os.environ.get("STUDENT_VISIBLE", "true").lower() == "true"  # ship-everything default
for k, v in {"CLOUD_SQL_INSTANCE": INSTANCE_CONN, "GCS_BUCKET": GCS_BUCKET, "DB_PASSWORD": DB_PASS,
             "WA_PHONE_NUMBER_ID": "x", "WA_ACCESS_TOKEN": "x", "WA_APP_SECRET": "x",
             "WA_VERIFY_TOKEN": "x"}.items():
    os.environ.setdefault(k, v)

from google.cloud import storage
from google.genai import types
from google.cloud.sql.connector import Connector
from PIL import Image
from pillow_heif import register_heif_opener; register_heif_opener()

from app.llm import client, settings
from app.ocr import OCR_SYSTEM_PROMPT
from app.schemas import OcrPaperExtraction
from app.preprocess import prepare_images_for_ocr
from app.paper_splitter import split_pdf_pages, rasterize_pdf_to_pngs
from app.validator import compare_reads, Outcome, CurationTier
from app.course_filing import derive_filing

IMG_EXT = ("jpg", "jpeg", "heic", "png")
BACKOFF = [5, 10, 20, 40, 60]
TRANSIENT = ("429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "ConnectError", "ReadError",
             "WriteError", "RemoteProtocolError", "PoolTimeout", "SSL", "getaddrinfo",
             "TransportError", "10054", "10053", "forcibly closed", "aborted", "Connection",
             "Max retries", "NameResolution", "Timeout", "EOF")

# --------------------------------------------------------------------------- DB
_connector = Connector()
def _db():
    return _connector.connect(INSTANCE_CONN, "pg8000", user=DB_USER, password=DB_PASS, db=DB_NAME)

DDL = """
CREATE TABLE IF NOT EXISTS pending_papers (
    id            SERIAL PRIMARY KEY,
    source        TEXT NOT NULL,
    sha           TEXT UNIQUE NOT NULL,
    object_key    TEXT,
    course_code   TEXT,
    school        TEXT, dept TEXT, level TEXT, semester TEXT, year TEXT,
    exam_session  TEXT,
    outcome       TEXT NOT NULL,
    curation_tier TEXT NOT NULL,
    primary_reader TEXT,
    num_questions INTEGER,
    flags         TEXT,
    reason        TEXT,
    questions_json TEXT,
    course_title  TEXT,
    filing_confidence TEXT,
    filing_source TEXT,
    student_visible BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT now()
);
"""
# Non-destructive migration so an existing throwaway table (from a prior run) gains the new
# filing columns without DROP.
MIGRATE = [
    "ALTER TABLE pending_papers ADD COLUMN IF NOT EXISTS course_title TEXT",
    "ALTER TABLE pending_papers ADD COLUMN IF NOT EXISTS filing_confidence TEXT",
    "ALTER TABLE pending_papers ADD COLUMN IF NOT EXISTS filing_source TEXT",
    "ALTER TABLE pending_papers ADD COLUMN IF NOT EXISTS student_visible BOOLEAN NOT NULL DEFAULT TRUE",
]
def init_db():
    c = _db()
    try:
        cur = c.cursor()
        cur.execute(DDL)
        for stmt in MIGRATE:
            cur.execute(stmt)
        c.commit()
    finally:
        c.close()

def already_written(sha):
    c = _db()
    try:
        cur = c.cursor(); cur.execute("SELECT 1 FROM pending_papers WHERE sha=%s", (sha,))
        return cur.fetchone() is not None
    finally:
        c.close()

def write_paper(row):
    c = _db()
    try:
        cur = c.cursor()
        cur.execute("""INSERT INTO pending_papers
            (source,sha,object_key,course_code,school,dept,level,semester,year,exam_session,
             outcome,curation_tier,primary_reader,num_questions,flags,reason,questions_json,
             course_title,filing_confidence,filing_source,student_visible)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (sha) DO NOTHING""",
            (row["source"], row["sha"], row["gcs_object"], row["course_code"], row["school"],
             row["dept"], row["level"], row["semester"], row["year"], row["exam_session"],
             row["outcome"], row["curation_tier"], row["primary_reader"], row["num_questions"],
             row["flags"], row["reason"], row["questions_json"],
             row["course_title"], row["filing_confidence"], row["filing_source"], row["student_visible"]))
        c.commit()
    finally:
        c.close()

# ------------------------------------------------------------------- metadata
def folder_meta(object_key):
    """Folder-derived filing metadata. course_code/title/dept come from the CONTEXT-AWARE deriver
    (app.course_filing.derive_filing: direct-code -> catalog -> dept+title slug -> dept fallback);
    school/level/semester/year are read positionally/by regex from the path under GCS_PREFIX."""
    rel = object_key[len(GCS_PREFIX):] if object_key.startswith(GCS_PREFIX) else object_key
    ds = [p for p in rel.split("/") if p][:-1]   # drop filename
    import re
    school = ds[0] if len(ds) > 0 else ""
    level = next((s for s in ds if re.search(r"\d00\s*level|year\s*\d|\blevel\b", s, re.I)), "")
    sem = next((s for s in ds if re.search(r"semester|harmattan|rain", s, re.I)), "")
    ym = next((re.search(r"20\d{2}\s*[-/]\s*20\d{2}|20\d{2}", s).group(0) for s in ds
               if re.search(r"20\d{2}", s)), None)
    sl = sem.lower()
    semester = "harmattan" if re.search(r"1st|first|semester\s*1|harmattan", sl) else \
               ("rain" if re.search(r"2nd|second|semester\s*2|rain", sl) else None)
    filing = derive_filing(object_key)           # context-aware course filing
    return {"course_code": filing["course_code"], "course_title": filing["course_title"],
            "dept": filing["dept"] or (ds[1] if len(ds) > 1 else ""),
            "school": school, "level": level, "semester": semester, "year": ym,
            "filing_confidence": filing["confidence"], "filing_source": filing["source"]}

# ------------------------------------------------------------------- OCR
def _ext(name): return name.rsplit(".", 1)[-1].lower() if "." in name else ""

def normalize_image(name, raw):
    e = _ext(name)
    if e in ("jpg", "jpeg"): return (raw, "image/jpeg")
    if e == "png": return (raw, "image/png")
    if e == "heic":
        im = Image.open(io.BytesIO(raw)).convert("RGB"); b = io.BytesIO(); im.save(b, "PNG")
        return (b.getvalue(), "image/png")
    return (raw, "image/jpeg")

def ocr_one(model, parts):
    p = [types.Part.from_bytes(data=b, mime_type=m) for b, m in parts]
    last = "no_attempt"
    for attempt in range(6):
        try:
            resp = client.models.generate_content(
                model=model, contents=p,
                config=types.GenerateContentConfig(
                    system_instruction=OCR_SYSTEM_PROMPT, response_mime_type="application/json",
                    response_schema=OcrPaperExtraction, temperature=0.0, max_output_tokens=4096,
                    thinking_config=types.ThinkingConfig(thinking_budget=0)))
            if resp.text is None:
                last = "empty_response"; time.sleep(BACKOFF[min(attempt, len(BACKOFF)-1)]); continue
            um = resp.usage_metadata
            data = OcrPaperExtraction.model_validate_json(resp.text)
            return dict(ok=True, in_tok=getattr(um, "prompt_token_count", 0) if um else 0,
                        out_tok=getattr(um, "candidates_token_count", 0) if um else 0, data=data)
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:140]}"
            if any(x in str(e) or x in type(e).__name__ for x in TRANSIENT):
                time.sleep(BACKOFF[min(attempt, len(BACKOFF)-1)]); continue
            return dict(ok=False, error=last)
    return dict(ok=False, error=f"exhausted; last={last}")

def dual_read(parts):
    f = ocr_one(settings.model_flash, parts)
    p = ocr_one(settings.model_pro, parts)
    return f, p

# ------------------------------------------------------------------- per file
def process_file(blob):
    """Returns (list_of_written_rows, metrics dict)."""
    name = blob.name
    raw = blob.download_as_bytes()
    meta = folder_meta(name)
    e = _ext(name)
    written = []
    tin = tout = 0
    t0 = time.time()
    # build the list of (paper_parts, page_bytes_for_sha)
    papers = []
    if e == "pdf":
        pngs = rasterize_pdf_to_pngs(raw)
        page_imgs = prepare_images_for_ocr(pngs)
        groups = split_pdf_pages(page_imgs)
        for g in groups:
            papers.append((g.images, [(b, "image/png") for b in g.images], g.session_hint))
    elif e in IMG_EXT:
        b, mime = normalize_image(name, raw)
        page_imgs = prepare_images_for_ocr([b])
        papers.append((page_imgs, [(x, mime) for x in page_imgs], None))
    else:
        return [], {"file": name, "skipped": True}

    for gi, (imgs, parts, sess_hint) in enumerate(papers):
        sha = hashlib.sha256(b"".join(imgs)).hexdigest()[:24] if len(papers) > 1 else \
              hashlib.sha256(raw).hexdigest()[:24]
        if already_written(sha):
            continue
        flash, pro = dual_read(parts)
        for rd in (flash, pro):
            if rd.get("ok"):
                tin += rd.get("in_tok", 0); tout += rd.get("out_tok", 0)
        f_read = flash["data"] if flash.get("ok") else None
        p_read = pro["data"] if pro.get("ok") else None
        res = compare_reads(f_read, p_read, meta, paper_sha=sha, curation_mode="index")
        primary = res.primary
        row = dict(
            source=SOURCE_TAG, sha=sha, gcs_object=name,
            course_code=meta["course_code"], school=meta["school"], dept=meta["dept"],
            level=meta["level"], semester=meta["semester"], year=meta["year"],
            exam_session=(getattr(primary, "exam_session", None) if primary else None),
            outcome=res.outcome.value, curation_tier=res.curation_tier.value,
            primary_reader=res.primary_reader,
            num_questions=(len(primary.questions) if primary else 0),
            flags="; ".join(f"{f.type.value}/{f.severity.value}" for f in res.flags),
            reason=res.reason[:500],
            questions_json=(primary.model_dump_json() if primary else None),
            course_title=meta["course_title"], filing_confidence=meta["filing_confidence"],
            filing_source=meta["filing_source"], student_visible=STUDENT_VISIBLE,
        )
        write_paper(row)
        written.append(row)
    return written, {"file": name, "papers": len(papers), "latency_s": round(time.time()-t0, 2),
                     "in_tok": tin, "out_tok": tout}

# ------------------------------------------------------------------- main
def main():
    print(f"[cloud_ingest] project={PROJECT} bucket={GCS_BUCKET} prefix={GCS_PREFIX} "
          f"db={INSTANCE_CONN}/{DB_NAME} source={SOURCE_TAG} concurrency={CONCURRENCY}", flush=True)
    init_db()
    sc = storage.Client(project=PROJECT)
    blobs = [b for b in sc.list_blobs(GCS_BUCKET, prefix=GCS_PREFIX) if not b.name.endswith("/")]
    blobs.sort(key=lambda b: b.name)
    print(f"[cloud_ingest] {len(blobs)} objects under prefix", flush=True)
    if MAX_FILES and len(blobs) > MAX_FILES:
        step = max(1, len(blobs) // MAX_FILES)
        blobs = blobs[::step][:MAX_FILES]
        print(f"[cloud_ingest] CANARY cap: every {step}th file -> {len(blobs)} files "
              f"(spans schools/types)", flush=True)

    t0 = time.time()
    all_rows, metrics = [], []
    with cf.ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {ex.submit(process_file, b): b.name for b in blobs}
        for fut in cf.as_completed(futs):
            name = futs[fut]
            try:
                rows, m = fut.result()
                all_rows += rows; metrics.append(m)
                print(f"[done] {name.split('/')[-1][:40]:40} papers={m.get('papers')} "
                      f"lat={m.get('latency_s')}s", flush=True)
            except Exception:
                print(f"[ERROR] {name}\n{traceback.format_exc()}", flush=True)
                metrics.append({"file": name, "error": True})

    wall = round(time.time()-t0, 2)
    tin = sum(m.get("in_tok", 0) for m in metrics)
    tout = sum(m.get("out_tok", 0) for m in metrics)
    cost = (tin*settings.price_flash_input_per_1m_usd/2 + tout*settings.price_flash_output_per_1m_usd/2
            + tin*settings.price_pro_input_per_1m_usd/2 + tout*settings.price_pro_output_per_1m_usd/2)/1e6
    from collections import Counter
    dist = Counter((r["outcome"], r["curation_tier"]) for r in all_rows)
    lats = [m["latency_s"] for m in metrics if "latency_s" in m]
    print("\n===== CLOUD TEST SUMMARY =====", flush=True)
    print(f"files={len(blobs)} papers_written={len(all_rows)} wall_time={wall}s", flush=True)
    print(f"per-file latency: min={min(lats) if lats else 0} max={max(lats) if lats else 0} "
          f"mean={round(sum(lats)/len(lats),2) if lats else 0}s", flush=True)
    print(f"tokens in={tin} out={tout}  est_spend=~${cost:.2f}", flush=True)
    print("routing distribution:", flush=True)
    for (oc, tier), c in sorted(dist.items()):
        print(f"   {oc}/{tier}: {c}", flush=True)
    fsrc = Counter(r.get("filing_source") for r in all_rows)
    print("filing source:", flush=True)
    for s, c in sorted(fsrc.items(), key=lambda kv: -kv[1]):
        print(f"   {s}: {c}", flush=True)
    print("[cloud_ingest] DONE", flush=True)

if __name__ == "__main__":
    main()
