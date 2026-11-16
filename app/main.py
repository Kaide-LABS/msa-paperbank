import logging
import threading
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, Query, HTTPException, Depends
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session
from google.cloud import storage

from app.config import settings
from app.logging_setup import setup_logging
from app.providers import get_object_store, get_embedder
from app import db
from app.deps import get_session
from app.schemas import WAWebhookPayload, TextReply
from app import whatsapp
from app import serve_v1
from app import retrieval
from app.inbound import handle_inbound
from app.channels import whatsapp as whatsapp_channel
from app.errors import DuplicateMessage
from app import signing
from app.auth import require_tool_token

log = logging.getLogger(__name__)

def _warmup(embedder) -> None:
    """Fire-and-forget at boot: pay the cold-init costs OFF the first user message's critical path.
    Force the embedder's first (cold) call here and preload the in-memory title vectors.
    Behaviour-unchanged: this only moves WHEN init happens. Routes through the ACTIVE embedder
    (`app.state.embedder`) — the local CPU model under provider=local (no network, loads from the
    baked cache), or the Vertex adapter under provider=gcp (the ~11s gemini-embedding cold init) —
    so a credential-free local boot never reaches Vertex.
    NEVER fatal — warmup is an optimisation, not a dependency (a boot-time hiccup is logged
    and swallowed; the bot starts and serves regardless)."""
    try:
        try:
            embedder.embed_query("warmup")           # forces the active embedder's cold init
        except Exception:
            log.warning("warmup_embed_failed", extra={"phase": "warmup"}, exc_info=True)
        try:
            from app import title_index
            s = db.SessionLocal()
            try:
                title_index.ensure_loaded(s)         # ~322 bytea vectors into RAM
            finally:
                s.close()
        except Exception:
            log.warning("warmup_title_index_failed", extra={"phase": "warmup"}, exc_info=True)
        log.info("warmup_complete", extra={"phase": "warmup"})
    except Exception:
        log.exception("warmup_failed", extra={"phase": "warmup"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    app.state.http = httpx.Client(timeout=httpx.Timeout(connect=5, read=30, write=30, pool=5))
    # Provider-gate the residual GCP boot path: only construct the GCS client under
    # provider=gcp. A credential-free provider=local boot leaves app.state.gcs=None and
    # reaches no GCP service, so `docker compose up` starts healthy without credentials (E1).
    app.state.gcs = storage.Client(project=settings.gcp_project) if settings.provider == "gcp" else None
    app.state.store = get_object_store(settings)
    # Build the active embedder once (mirrors app.state.store). CPU model — nothing to
    # dispose; the GCP default's from_settings is lazy so this stays cheap under "gcp".
    app.state.embedder = get_embedder(settings)
    # NON-BLOCKING: start warmup in a daemon thread so readiness is NOT delayed (the startup probe
    # passes immediately; the embed-init runs in the background, not before 'ready'). Warmup goes
    # through the ACTIVE embedder, never the Vertex-only import, so local boot stays GCP-free.
    threading.Thread(target=_warmup, args=(app.state.embedder,), name="warmup", daemon=True).start()
    yield
    app.state.http.close()
    db.dispose()

app = FastAPI(lifespan=lifespan, title="msa-paperbank", version="0.1.0")

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/download")
def download(
    request: Request,
    key: str = Query(...),
    exp: int = Query(...),
    sig: str = Query(...),
) -> Response:
    """Stateless signed-URL download (Phase 3, AC 6).

    The HMAC signature over (key, exp) IS the capability: accept iff it verifies and has
    not expired, else 403. No DB lookup and no auth header — the ~15-min TTL bounds
    exposure. On success stream the object bytes from the active object store.
    """
    if not signing.verify(key, exp, sig):
        raise HTTPException(status_code=403, detail="invalid or expired signature")
    try:
        data = request.app.state.store.download_bytes(key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="object not found")
    return Response(content=data, media_type="application/octet-stream")


class ToolRetrieveRequest(BaseModel):
    query: str
    prefer_courses: list[str] | None = None


@app.post("/tool/retrieve")
def tool_retrieve(
    body: ToolRetrieveRequest,
    request: Request,
    session: Session = Depends(get_session),
    _: None = Depends(require_tool_token),
) -> dict:
    """Authed single-call retrieval seam for the future Copilot Studio agent (Phase 3).

    Minimal JSON `{query, prefer_courses?}` -> `retrieval.answer_query`; returns the
    matched paper's metadata plus a short-lived `signed_url` for its object. Guarded by
    the bearer dependency; imports no WhatsApp types.
    """
    result = retrieval.answer_query(session, body.query, prefer_courses=body.prefer_courses)
    paper = result.paper
    if paper is None:
        return {
            "found": False,
            "intent": result.intent,
            "course_code": result.course_code,
            "course_known": result.course_known,
        }
    serve_key = paper.served_object_key or paper.object_key
    return {
        "found": True,
        "intent": result.intent,
        "paper": {
            "id": paper.id,
            "course_code": paper.course_code,
            "course_title": paper.course_title,
            "year": paper.year,
            "semester": paper.semester,
            "exam_session": paper.exam_session,
        },
        "signed_url": request.app.state.store.signed_url(serve_key),
    }

@app.get("/webhook")
def webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    if whatsapp.verify_token_match(hub_mode, hub_verify_token, settings.wa_verify_token.get_secret_value()):
        return PlainTextResponse(hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="verify_token mismatch")

@app.post("/webhook")
async def webhook_inbound(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    session: Session = Depends(get_session),
) -> Response:
    raw = await request.body()
    if not whatsapp.verify_signature(raw, x_hub_signature_256, settings.wa_app_secret.get_secret_value()):
        raise HTTPException(status_code=401, detail="bad signature")
    try:
        payload = WAWebhookPayload.model_validate_json(raw)
    except ValidationError as e:
        log.warning("invalid_payload", extra={"phase": "webhook", "err": str(e)})
        return Response(status_code=200)   # always 200 to Meta on parseable-but-unexpected

    for entry in payload.entry:
        for change in entry.changes:
            for msg in (change.value.messages or []):
                try:
                    if settings.serve_v1_enabled:
                        reply = serve_v1.handle_message_v1(
                            session, msg, request.app.state.http, request.app.state.store
                        )
                        paper_loader = lambda pid: retrieval.load_served_cached(
                            session, pid, request.app.state.store
                        )
                    else:
                        inbound = whatsapp_channel.to_inbound(msg)
                        reply = handle_inbound(
                            session, inbound, request.app.state.http, request.app.state.store
                        )
                        paper_loader = lambda pid: retrieval.load_pdf_bytes(
                            session.get(db.Paper, pid), request.app.state.store
                        )
                    reply = whatsapp_channel.from_reply(reply)
                    if not (isinstance(reply, TextReply) and reply.body == ""):
                        whatsapp.send_reply(
                            http_client=request.app.state.http,
                            to=msg.from_,
                            reply=reply,
                            paper_loader=paper_loader,
                        )
                except DuplicateMessage:
                    continue
                except Exception:
                    log.exception("handle_message_failed", extra={"wa_message_id": msg.id, "wa_from": msg.from_, "phase": "webhook"})
                    session.rollback()

    # Flush notifications (one fresh transaction; SQLAlchemy autobegins on the SELECT).
    try:
        from app.db import IntakeNotification
        from sqlalchemy import select

        notifications = session.execute(
            select(IntakeNotification)
            .where(IntakeNotification.sent_at == None)
            .order_by(IntakeNotification.created_at.asc())
            .limit(5)
            .with_for_update(skip_locked=True)
        ).scalars().all()
        
        for n in notifications:
            try:
                whatsapp.send_text(request.app.state.http, n.phone_number, n.body)
                from datetime import datetime, timezone
                n.sent_at = datetime.now(timezone.utc)
            except Exception as e:
                log.error("failed_to_send_notification", extra={"id": n.id, "wa_from": n.phone_number, "phase": "webhook", "err": str(e)})
        session.commit()
    except Exception:
        log.exception("flush_notifications_failed", extra={"phase": "webhook"})
        session.rollback()

    return Response(status_code=200)