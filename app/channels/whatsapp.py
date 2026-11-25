"""WhatsApp thin adapter (Phase 2).

Maps the Meta WhatsApp Cloud API webhook payload (`WAMessage`) onto the channel-neutral
`InboundMessage`, and maps outbound replies back. The handler core (`app.inbound`) imports no
WhatsApp wire types; this edge module is the one place WhatsApp-specific types meet the neutral
envelope. The send-side / media download still lives in `app.whatsapp`; this adapter only
translates the inbound envelope and names the outbound seam so Phase 3+ can diverge.
"""
from app.inbound import InboundMessage
from app.schemas import WAMessage, Reply

CHANNEL = "whatsapp"


def to_inbound(wa: WAMessage) -> InboundMessage:
    """Translate a WhatsApp `WAMessage` into the channel-neutral `InboundMessage`.

    `type` collapses to `kind`: `"text"`/`"image"` pass through, everything else → `"other"`.
    The original payload is stashed under `raw` as an opaque passthrough."""
    kind = wa.type if wa.type in ("text", "image") else "other"
    return InboundMessage(
        channel=CHANNEL,
        sender=wa.from_,
        message_id=wa.id,
        kind=kind,
        text=wa.text.body if wa.text else None,
        media_id=wa.image.id if wa.image else None,
        raw=wa.model_dump(),
    )


def from_reply(reply: Reply) -> Reply:
    """Map a neutral outbound reply back to the WhatsApp-facing reply. Identity this phase
    (replies are already channel-neutral); it exists so the seam is named and Phase 3+ can
    diverge per channel. Delivery itself is done by `app.whatsapp.send_reply`."""
    return reply
