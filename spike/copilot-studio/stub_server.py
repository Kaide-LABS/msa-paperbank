"""Copilot Studio spike: a stand-in for the Paperbank tool endpoint.

It keeps the REAL contract (POST /tool/retrieve with a bearer token, signed GET /download, GET /healthz) so
what the spike learns about Copilot Studio and Teams carries over to the real backend. It needs no database,
no model and no GCP. Everything it returns is fake. It also logs every request, so you can see exactly what
Copilot Studio sends, and it has a /tool/probe endpoint for the image and file tests.

Run (from this folder):
    pip install fastapi uvicorn
    set SPIKE_TOKEN=pick-a-long-random-string
    set PUBLIC_BASE_URL=https://<your-tunnel-host>
    python -m uvicorn stub_server:app --port 8000

Environment:
    SPIKE_TOKEN          bearer token the tool endpoint accepts (required; no default on purpose).
    PUBLIC_BASE_URL      the public https address of this server, used in signed links (required for the link tests).
    SPIKE_DOWNLOAD_MODE  "octet" (default) mirrors the real app: application/octet-stream, no filename.
                         "pdf" sends application/pdf with a filename, which is the likely fix. Compare both in Teams.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

TOKEN = os.environ.get("SPIKE_TOKEN", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
DOWNLOAD_MODE = os.environ.get("SPIKE_DOWNLOAD_MODE", "octet")
SIGNING_KEY = secrets.token_hex(32)  # new on every start, so old links die with the process
TTL_SECONDS = 900
LOG_PATH = Path(__file__).with_name("spike_requests.jsonl")

# Fake papers: enough variety to test "found", "not found", and the course-filter argument.
PAPERS = [
    {"id": 1, "course_code": "CSC101", "course_title": "Introduction to Computing", "year": 2023, "semester": 1, "exam_session": "Final"},
    {"id": 2, "course_code": "MAT201", "course_title": "Linear Algebra", "year": 2022, "semester": 2, "exam_session": "Final"},
    {"id": 3, "course_code": "ENG110", "course_title": "Technical Writing", "year": 2024, "semester": 1, "exam_session": "Midterm"},
]

app = FastAPI(title="Paperbank tool stub (Copilot Studio spike)", version="0.0.1")


def _minimal_pdf(title: str) -> bytes:
    """A tiny but valid one-page PDF, so Teams has something real to open."""
    text = f"BT /F1 18 Tf 72 720 Td ({title}) Tj ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def _sign(key: str, exp: int) -> str:
    return hmac.new(SIGNING_KEY.encode(), f"{key}:{exp}".encode(), hashlib.sha256).hexdigest()


def _signed_url(key: str) -> str:
    exp = int(time.time()) + TTL_SECONDS
    return f"{PUBLIC_BASE_URL}/download?key={quote(key)}&exp={exp}&sig={_sign(key, exp)}"


def require_token(authorization: str = Header(default="")) -> None:
    scheme, _, presented = authorization.partition(" ")
    if not TOKEN or scheme.lower() != "bearer" or not presented or not hmac.compare_digest(presented, TOKEN):
        raise HTTPException(status_code=401, detail="missing, malformed or wrong bearer token")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Record what Copilot Studio actually sends. The token itself is never written down."""
    body = await request.body()
    headers = {k: v for k, v in request.headers.items()}
    if "authorization" in headers:
        scheme, _, rest = headers["authorization"].partition(" ")
        headers["authorization"] = f"{scheme} <{len(rest)} chars>"
    response = await call_next(request)
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query)[:300],
        "client": request.client.host if request.client else None,
        "status": response.status_code,
        "headers": headers,
        "body_bytes": len(body),
        "body_preview": body[:2000].decode("utf-8", "replace"),
    }
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return response


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


class ToolRetrieveRequest(BaseModel):
    query: str
    prefer_courses: list[str] | None = None


@app.post("/tool/retrieve")
def tool_retrieve(body: ToolRetrieveRequest, _: None = Depends(require_token)) -> dict:
    """Same request and response shape as the real endpoint in app/main.py."""
    q = body.query.lower()
    preferred = {c.upper() for c in (body.prefer_courses or [])}
    hits = [
        p for p in PAPERS
        if p["course_code"].lower() in q or p["course_title"].lower() in q or any(w in q for w in p["course_title"].lower().split() if len(w) > 4)
    ]
    if preferred:
        hits = [p for p in hits if p["course_code"] in preferred] or hits
    if not hits:
        return {"found": False, "intent": "past_paper", "course_code": None, "course_known": False}
    paper = hits[0]
    return {"found": True, "intent": "past_paper", "paper": paper, "signed_url": _signed_url(f"papers/{paper['id']}.pdf")}


@app.get("/download")
def download(key: str = Query(...), exp: int = Query(...), sig: str = Query(...)) -> Response:
    if exp < int(time.time()) or not hmac.compare_digest(_sign(key, exp), sig):
        raise HTTPException(status_code=403, detail="invalid or expired signature")
    pdf = _minimal_pdf(f"Fake past paper {key}")
    if DOWNLOAD_MODE == "pdf":
        name = key.rsplit("/", 1)[-1]
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})
    return Response(pdf, media_type="application/octet-stream")  # what the real app does today


@app.post("/tool/probe")
async def tool_probe(request: Request, _: None = Depends(require_token)) -> dict:
    """Accepts any JSON and reports what arrived. For the image and file tests: does Copilot Studio send the
    bytes, a URL, a reference, or nothing?"""
    raw = await request.body()
    try:
        data = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {"parsed": False, "bytes": len(raw), "content_type": request.headers.get("content-type")}

    def describe(v):
        if isinstance(v, str):
            kind = "string"
            if v.startswith(("http://", "https://")):
                kind = "url"
            else:
                try:
                    if len(v) > 100:
                        base64.b64decode(v, validate=True)
                        kind = "base64-like"
                except Exception:
                    pass
            return {"type": kind, "length": len(v), "head": v[:60]}
        if isinstance(v, dict):
            return {"type": "object", "fields": {k: describe(x) for k, x in v.items()}}
        if isinstance(v, list):
            return {"type": "array", "length": len(v), "first": describe(v[0]) if v else None}
        return {"type": type(v).__name__, "value": v}

    return {"parsed": True, "bytes": len(raw), "content_type": request.headers.get("content-type"), "fields": {k: describe(v) for k, v in data.items()}}
