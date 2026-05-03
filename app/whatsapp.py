import hmac
import hashlib
from fastapi import HTTPException
from typing import Callable
import httpx
from app.config import settings
from app.schemas import Reply, TextReply, DocumentReply
from app.errors import WhatsAppError

def verify_signature(raw_body: bytes, header_value: str, app_secret: str) -> bool:
    expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_value or "")

def verify_token_match(mode: str, token: str, expected: str) -> str | None:
    if mode == "subscribe" and token == expected:
        return mode # Return mode which gets ignored? Wait, spec says returns hub.challenge if matches. 
        # Actually caller passes mode, token, expected and returns challenge.
        # Let's fix signature to just return bool or the challenge if we pass it.
        # Spec says: "def verify_token_match(mode: str, token: str, expected: str) -> str | None ... Returns the value of hub.challenge (passed in by caller) iff mode == 'subscribe' and token == expected."
        # This implies it should be: verify_token_match(mode, token, expected) -> returns bool? I will adjust main.py to handle the challenge directly.
    pass

# I will redefine verify_token_match slightly differently for clarity, or just follow spec strictly
def verify_token_match(mode: str, token: str, expected: str) -> bool:
    return mode == "subscribe" and token == expected

# Need to update main.py to pass challenge separately.

# Outbound HTTP client is injected via app.state.http in lifespan.
# We will pass the client to the functions.

def upload_media(http_client: httpx.Client, pdf_bytes: bytes, filename: str) -> str:
    url = f"https://graph.facebook.com/{settings.wa_graph_version}/{settings.wa_phone_number_id}/media"
    headers = {"Authorization": f"Bearer {settings.wa_access_token.get_secret_value()}"}
    data = {"messaging_product": "whatsapp", "type": "application/pdf"}
    files = {"file": (filename, pdf_bytes, "application/pdf")}
    
    resp = http_client.post(url, headers=headers, data=data, files=files)
    if resp.status_code >= 400:
        raise WhatsAppError(f"Failed to upload media: {resp.status_code} {resp.text}")
    return resp.json()["id"]

def send_text(http_client: httpx.Client, to: str, body: str) -> None:
    url = f"https://graph.facebook.com/{settings.wa_graph_version}/{settings.wa_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.wa_access_token.get_secret_value()}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body, "preview_url": False}
    }
    resp = http_client.post(url, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise WhatsAppError(f"Failed to send text: {resp.status_code} {resp.text}")

def send_document(http_client: httpx.Client, to: str, media_id: str, caption: str, filename: str) -> None:
    url = f"https://graph.facebook.com/{settings.wa_graph_version}/{settings.wa_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.wa_access_token.get_secret_value()}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "document",
        "document": {"id": media_id, "caption": caption, "filename": filename}
    }
    resp = http_client.post(url, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise WhatsAppError(f"Failed to send document: {resp.status_code} {resp.text}")

def send_reply(http_client: httpx.Client, to: str, reply: Reply, paper_loader: Callable[[int], tuple[bytes, str]]) -> None:
    if isinstance(reply, TextReply):
        send_text(http_client, to, reply.body)
    elif isinstance(reply, DocumentReply):
        pdf_bytes, filename = paper_loader(reply.paper_id)
        media_id = upload_media(http_client, pdf_bytes, filename)
        send_document(http_client, to, media_id, reply.caption, filename)