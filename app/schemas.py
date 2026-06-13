from typing import Literal, Annotated
from pydantic import BaseModel, Field, field_validator

class WAText(BaseModel):
    body: str

class WAImage(BaseModel):
    id: str
    mime_type: str
    sha256: str | None = None
    caption: str | None = None

class WAMessage(BaseModel):
    id: str
    from_: str = Field(validation_alias="from")
    timestamp: str
    type: Literal["text", "image", "document", "audio", "video", "interactive", "button", "reaction", "sticker", "location", "contacts", "unknown"]
    text: WAText | None = None
    image: WAImage | None = None

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
    course_phrase: str | None = None    # natural-language course NAME the student typed, for fuzzy title match
    year: int | None = None
    semester: Literal["harmattan", "rain"] | None = None
    exam_session: Literal["CA1", "CA2", "exam"] | None = None
    confidence: float

    @field_validator("year")
    @classmethod
    def _year_range(cls, v):
        if v is None: return v
        if not (2000 <= v <= 2100): raise ValueError("year out of range")
        return v

class OcrQuestion(BaseModel):
    number: int
    text: str

class OcrPaperExtraction(BaseModel):
    course_code: str | None = None
    course_title: str | None = None
    exam_year: int | None = None
    exam_session: Literal["CA1", "CA2", "exam", "first", "second"] | None = None
    questions: list[OcrQuestion]
    error: str | None = None

    @field_validator("exam_year")
    @classmethod
    def _year_range(cls, v):
        if v is None: return v
        if not (2000 <= v <= 2100): raise ValueError("year out of range")
        return v

class PageBoundaryProbe(BaseModel):
    """Tiny per-page signal used by app.paper_splitter to split multi-paper PDF bundles
    BEFORE OCR. Returned by a cheap Flash call (thinking_budget=0, small token cap) — this is
    deliberately NOT a full OCR. A bundle scans several distinct papers back-to-back; these
    flags mark where one paper ends and the next begins."""
    is_new_paper_header: bool = False   # page carries a fresh PAU exam masthead -> THE split signal
    course_code: str | None = None      # course code printed in that header, if any
    session_hint: Literal["CA", "exam"] | None = None  # header says CA vs Examination
    # CAPTURED-BUT-UNUSED diagnostic hint — NOT a split signal. The real-data diagnostic showed a
    # single-page probe returns this True for ANY page beginning at "Question 1" (every paper's
    # first page included), not for a genuine "restart after higher question numbers", so the
    # splitter ignores it (see app.paper_splitter). Kept on the schema so the probe still records
    # it: a FUTURE deterministic check — restart-after-higher-numbers computed ACROSS pages from
    # real extracted question numbers (not asked of a single-page probe) — could use it as a
    # corroborated backstop if a corpus trial ever surfaces a genuine masthead miss.
    has_question_one_reset: bool = False

class ContributionValidation(BaseModel):
    """Layer-1 cheap vision gate for a contributed image (Flash)."""
    is_paper_like: bool          # reads as an exam/CA question paper (vs selfie/screenshot/random)
    clarity_ok: bool             # legible enough (not too dark/blurry)
    reason: str | None = None    # short why, for the reject message / audit

class MastheadRead(BaseModel):
    """Filing guess read off page 1's masthead (Flash). ALWAYS confirmed before saving."""
    course_code: str | None = None
    course_title: str | None = None
    year: int | None = None
    exam_session: Literal["CA1", "CA2", "exam"] | None = None
    doc_type: Literal["exam", "CA"] | None = None
    confidence: float = 0.0

    @field_validator("year")
    @classmethod
    def _yr(cls, v):
        if v is None: return v
        if not (2000 <= v <= 2100): return None
        return v

class TextReply(BaseModel):
    kind: Literal["text"] = "text"
    body: str

class DocumentReply(BaseModel):
    kind: Literal["document"] = "document"
    paper_id: int
    caption: str
    followup_text: str | None = None

Reply = Annotated[TextReply | DocumentReply, Field(discriminator="kind")]