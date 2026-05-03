from typing import Literal, Annotated
from pydantic import BaseModel, Field, field_validator

class WAText(BaseModel):
    body: str

class WAMessage(BaseModel):
    id: str
    from_: str = Field(validation_alias="from")
    timestamp: str
    type: Literal["text", "image", "document", "audio", "video", "interactive", "button", "reaction", "sticker", "location", "contacts", "unknown"]
    text: WAText | None = None

class WAValue(BaseModel):
    messaging_product: Literal["whatsapp"]
    metadata: dict
    messages: list[WAMessage] | None = None
    statuses: list[dict] | None = None

class WAChange(BaseModel):
    value: WAValue
    field: str

class WAEntry(BaseModel):
    id: str
    changes: list[WAChange]

class WAWebhookPayload(BaseModel):
    object: Literal["whatsapp_business_account"]
    entry: list[WAEntry]

class RouterOutput(BaseModel):
    intent: Literal["paper_request", "greeting", "other"]
    course_code: str | None = None
    year: int | None = None
    semester: Literal["harmattan", "rain"] | None = None
    confidence: float

    @field_validator("year")
    @classmethod
    def _year_range(cls, v):
        if v is None: return v
        if not (2000 <= v <= 2100): raise ValueError("year out of range")
        return v

class TextReply(BaseModel):
    kind: Literal["text"] = "text"
    body: str

class DocumentReply(BaseModel):
    kind: Literal["document"] = "document"
    paper_id: int
    caption: str

Reply = Annotated[TextReply | DocumentReply, Field(discriminator="kind")]