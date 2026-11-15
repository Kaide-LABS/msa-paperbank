import json
import time
import httpx
from sqlalchemy import select
from google.cloud import storage
from google.genai import types
from app.config import settings
from app.db import SessionLocal
from app.llm import client as genai_client

def check_db():
    start = time.time()
    try:
        with SessionLocal() as session:
            session.execute(select(1)).scalar()
        return True, int((time.time() - start) * 1000), "ok"
    except Exception as e:
        return False, int((time.time() - start) * 1000), str(e)

def check_gcs():
    start = time.time()
    try:
        gcs = storage.Client(project=settings.gcp_project)
        exists = gcs.bucket(settings.object_store_bucket).exists()
        if exists:
            return True, int((time.time() - start) * 1000), f"bucket={settings.object_store_bucket}"
        else:
            return False, int((time.time() - start) * 1000), f"bucket {settings.object_store_bucket} not found"
    except Exception as e:
        return False, int((time.time() - start) * 1000), str(e)

def check_vertex_flash():
    start = time.time()
    try:
        genai_client.models.generate_content(
            model=settings.model_flash,
            contents="ping",
            config=types.GenerateContentConfig(max_output_tokens=4)
        )
        return True, int((time.time() - start) * 1000), f"model={settings.model_flash}"
    except Exception as e:
        return False, int((time.time() - start) * 1000), str(e)

def check_vertex_embedding():
    start = time.time()
    try:
        genai_client.models.embed_content(
            model=settings.model_embedding,
            contents="ping",
            config=types.EmbedContentConfig(output_dimensionality=settings.embedding_dim)
        )
        return True, int((time.time() - start) * 1000), f"dim={settings.embedding_dim}"
    except Exception as e:
        return False, int((time.time() - start) * 1000), str(e)

def check_meta():
    start = time.time()
    try:
        url = f"https://graph.facebook.com/{settings.wa_graph_version}/{settings.wa_phone_number_id}"
        headers = {"Authorization": f"Bearer {settings.wa_access_token.get_secret_value()}"}
        with httpx.Client() as client:
            resp = client.get(url, headers=headers)
        if resp.status_code == 200:
            return True, int((time.time() - start) * 1000), f"phone_number_id={settings.wa_phone_number_id}"
        else:
            return False, int((time.time() - start) * 1000), f"status={resp.status_code} body={resp.text[:100]}"
    except Exception as e:
        return False, int((time.time() - start) * 1000), str(e)

def run_health():
    checks = [
        ("db", check_db),
        ("gcs", check_gcs),
        ("vertex_flash", check_vertex_flash),
        ("vertex_embedding", check_vertex_embedding),
        ("meta", check_meta),
    ]
    
    results = []
    overall_pass = True
    start_total = time.time()
    
    for name, fn in checks:
        ok, ms, detail = fn()
        results.append({"name": name, "ok": ok, "ms": ms, "detail": detail})
        if not ok:
            overall_pass = False
            
    total_ms = int((time.time() - start_total) * 1000)
    summary = {
        "overall": "PASS" if overall_pass else "FAIL",
        "ms": total_ms,
        "checks": results
    }
    
    print(json.dumps(summary))
    return 0 if overall_pass else 1

if __name__ == "__main__":
    import sys
    sys.exit(run_health())
