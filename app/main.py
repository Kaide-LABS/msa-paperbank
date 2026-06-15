import logging
import threading
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, Query, HTTPException, Depends
from fastapi.responses import PlainTextResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from google.cloud import storage

from app.config import settings
from app.logging_setup import setup_logging
from app import db
from app.deps import get_session
from app.schemas import WAWebhookPayload, TextReply
from app import whatsapp
from app import pipeline
from app import serve_v1
from app import retrieval
from app.errors import DuplicateMessage

log = logging.getLogger(__name__)

def _warmup() -> None:
    """Fire-and-forget at boot: pay the cold-init costs OFF the first user message's critical path.
    The embedding model's first call is ~11s cold (gemini-embedding-001) — force it here; also
    preload the in-memory title vectors. Behaviour-unchanged: this only moves WHEN init happens.
    NEVER fatal — warmup is an optimisation, not a dependency (a boot-time Vertex hiccup is logged
    and swallowed; the bot starts and serves regardless)."""
    try:
        from app.embeddings import embed_query
        try:
            embed_query("warmup")                    # forces the ~11s gemini-embedding cold init
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
    app.state.gcs = storage.Client(project=settings.gcp_project)
    # NON-BLOCKING: start warmup in a daemon thread so readiness is NOT delayed (the startup probe
    # passes immediately; the ~11s embed-init runs in the background, not before 'ready').
    threading.Thread(target=_warmup, name="warmup", daemon=True).start()
    yield
    app.state.http.close()
    db.dispose()

app = FastAPI(lifespan=lifespan, title="msa-paperbank", version="0.1.0")

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}

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
                            session, msg, request.app.state.http, request.app.state.gcs
                        )
                        paper_loader = lambda pid: retrieval.load_served_bytes_v1(
                            session, pid, request.app.state.gcs, settings.gcs_bucket
                        )
                    else:
                        reply = pipeline.handle_message(
                            session, msg, request.app.state.http, request.app.state.gcs
                        )
                        paper_loader = lambda pid: retrieval.load_pdf_bytes(
                            session.get(db.Paper, pid), request.app.state.gcs, settings.gcs_bucket
                        )
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