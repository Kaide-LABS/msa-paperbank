import logging
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
from app import retrieval
from app.errors import DuplicateMessage

log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    app.state.http = httpx.Client(timeout=httpx.Timeout(connect=5, read=30, write=30, pool=5))
    app.state.gcs = storage.Client(project=settings.gcp_project)
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
        log.warning("invalid_payload", extra={"err": str(e)})
        return Response(status_code=200)   # always 200 to Meta on parseable-but-unexpected

    for entry in payload.entry:
        for change in entry.changes:
            for msg in (change.value.messages or []):
                try:
                    reply = pipeline.handle_message(session, msg)
                    if not (isinstance(reply, TextReply) and reply.body == ""):
                        whatsapp.send_reply(
                            http_client=request.app.state.http,
                            to=msg.from_,
                            reply=reply,
                            paper_loader=lambda pid: retrieval.load_pdf_bytes(
                                session.get(db.Paper, pid), request.app.state.gcs, settings.gcs_bucket
                            ),
                        )
                except DuplicateMessage:
                    continue
                except Exception:
                    log.exception("handle_message_failed", extra={"wa_message_id": msg.id})
                    session.rollback()

    return Response(status_code=200)