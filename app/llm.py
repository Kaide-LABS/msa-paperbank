from google import genai
from google.genai import types
from app.config import settings
from app.schemas import RouterOutput, PageBoundaryProbe, ContributionValidation, MastheadRead
from app.errors import RouterError

client = genai.Client(
    vertexai=True, 
    project=settings.gcp_project, 
    location=settings.gcp_location
)

ROUTER_SYSTEM_PROMPT = """You are the intent router for a PAU past-paper WhatsApp bot.
Classify the user's message into exactly one intent and output JSON matching the schema.

INTENTS (choose exactly one):

- "paper_request": the user wants a specific past paper. Extract:
  * course_code: uppercase, no spaces, e.g. 'MTH102', 'CSC305', 'GST122'. ONLY when the user
    actually typed a code-like token. If they named the course in words only, leave null.
  * course_phrase: the natural-language course NAME the student typed, lowercased, e.g.
    'introduction to finance', 'organic chemistry', 'communication in english'. Strip filler
    like 'the', 'paper', 'past question', 'abeg', 'send'. null if they gave only a code.
  * year: 4-digit int if present, else null.
  * semester: 'harmattan' (first/Harmattan/dry) or 'rain' (second/Rain). null if absent.
  * exam_session: 'CA1' | 'CA2' | 'exam' if stated, else null.
  Examples: "MTH102 harmattan 2022" (code=MTH102, phrase=null),
  "you get intro to finance paper?" (code=null, phrase='intro to finance'),
  "organic chemistry 200 level" (code=null, phrase='organic chemistry'),
  "csc 201 last year", "abeg send csc201 rain", "communication in english past question".

- "greeting": a bare greeting, salutation, or thanks with NO other request in it.
  This INCLUDES Nigerian-English / Pidgin greetings used purely to say hello.
  Examples ONLY like: "hi", "hello", "salam", "asalamu alaikum", "good morning",
  "thanks", "jazakallah", "how far", "how far na", "how bodi", "wetin dey", "wassup".

- "other": ANY message that is not a paper request and not a bare greeting. This includes
  questions about the bot, small talk, and anything conversational.
  Examples: "how are you", "what's your name", "who made you", "what can you do",
  "can you help me study", "how are you and how are my people".

DECISION RULES:
- Precedence: if the message names or implies a course/year/semester, it is "paper_request"
  even if it opens with a greeting or pidgin. ("how far, you get gst122?" -> paper_request.)
- A message is "greeting" ONLY if removing the greeting/pidgin words leaves nothing meaningful.
  "hi how are you" -> "other" (a question remains). "how far" alone -> "greeting" (nothing remains).
- "what's your name", "how are you", "what can you do", "who made you" are ALWAYS "other",
  never "greeting" — they are questions, not salutations.
- Pidgin test: "how far", "how bodi", "wetin dey" used alone are greetings. The same phrases
  followed by a request are "paper_request".
- When genuinely torn between "greeting" and "other", choose "other".

confidence: your own 0..1 estimate for the chosen intent.
"""

def route(user_text: str) -> tuple[RouterOutput, int, int]:
    try:
        resp = client.models.generate_content(
            model=settings.model_flash,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=ROUTER_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=RouterOutput,
                temperature=0.0,
                max_output_tokens=512,
                # thinking_budget=0 is REQUIRED: on gemini-3-flash-preview the default thinking
                # budget consumes the output cap on some inputs (multi-word course-title phrases
                # like "communication in english"), so resp.text comes back None (finish=MAX_TOKENS)
                # and validation fails. Disabling thinking makes the tiny router JSON deterministic
                # and fast — same fix the OCR path documents in call_pro_vision.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        parsed = RouterOutput.model_validate_json(resp.text)
        
        in_tok = 0
        out_tok = 0
        if resp.usage_metadata:
            in_tok = getattr(resp.usage_metadata, "prompt_token_count", 0)
            out_tok = getattr(resp.usage_metadata, "candidates_token_count", 0)
            
        return parsed, in_tok, out_tok
    except Exception as e:
        raise RouterError("Failed to route message via LLM") from e

def call_pro_vision(parts: list[types.Part], system_instruction: str, response_schema: type) -> str:
    """Returns the raw resp.text. Caller does Pydantic validation.

    thinking_budget=0 is REQUIRED here, not optional. The 2026-06 OCR probe
    (c:\\tmp\\pau-probe) proved that with default thinking + max_output_tokens=4096
    every multi-page PDF failed with finish=MAX_TOKENS: the model spent the entire
    output budget on reasoning and emitted only ~315 tokens before truncating, so
    OcrPaperExtraction.model_validate_json() then raised. With thinking_budget=0 at
    the SAME 4096 cap, all multi-page conditions finished with finish=STOP. This is
    the only change that unblocks multi-page ingest (~478 PDFs, ~90% scans).
    Scope: OCR call only — the router (route()) is deliberately left untouched.
    """
    resp = client.models.generate_content(
        model=settings.model_pro,
        contents=parts,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.0,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return resp.text


PAGE_BOUNDARY_PROMPT = """You are scanning ONE page image from a bundle of PAU past-exam papers
to detect PAPER BOUNDARIES. A single PDF may contain several distinct papers scanned back-to-back
(e.g. a "First Semester CA" and a "First Semester Examination" for the same course). Look ONLY at
this one page and answer briefly. Return JSON ONLY matching the schema.

- is_new_paper_header: true if THIS page carries a PAU exam masthead that STARTS a new paper —
  e.g. "SCHOOL OF ...", "Department of ...", "ACADEMIC SESSION", a course-code line,
  "First/Second Semester (Continuous Assessment | CA | Examination)", "Time allowed". A mid-paper
  continuation page has no such masthead -> false.
- course_code: the course code printed in that header (e.g. "ACC201"), else null.
- session_hint: "CA" if the header indicates a CA / continuous assessment, "exam" if it indicates
  an Examination, else null.
- has_question_one_reset: true if this page restarts numbering at "QUESTION ONE" / "QUESTION 1"
  (especially "QUESTION ONE (Compulsory)") even though earlier pages already showed higher-numbered
  questions. Otherwise false.
"""

_VALIDATE_PROMPT = """You are the intake gate for a past-paper contribution bot. Look at ONE photo
and judge it for accepting as a page of a university EXAM or CA (continuous assessment) question
paper. Return JSON only.
- is_paper_like: true if it shows printed/handwritten EXAM or CA question content (course masthead,
  "Question 1", marks, "Time allowed", instructions, questions). false for selfies, random photos,
  screenshots of chats, memes, lecture slides/notes that are not a question paper.
- clarity_ok: false if too dark, blurry, glare-washed, or cropped so the text can't be read; true if
  a person could comfortably read the questions.
- reason: a short phrase (e.g. "exam masthead + questions", "selfie", "too dark to read").
Judge ONLY this image."""

def validate_contribution_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> ContributionValidation:
    """Cheap Flash gate: is this a legible past-paper page? thinking_budget=0 keeps it fast."""
    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    resp = client.models.generate_content(
        model=settings.model_flash, contents=[part],
        config=types.GenerateContentConfig(
            system_instruction=_VALIDATE_PROMPT, response_mime_type="application/json",
            response_schema=ContributionValidation, temperature=0.0, max_output_tokens=256,
            thinking_config=types.ThinkingConfig(thinking_budget=0)))
    return ContributionValidation.model_validate_json(resp.text)


_MASTHEAD_PROMPT = """You are reading the MASTHEAD (top header) of page 1 of a PAU past-exam paper to
file it. Extract what is printed; guess nothing you can't see. Return JSON only.
- course_code: the course code if printed (e.g. 'GST111', 'EEE321'), else null.
- course_title: the course title/name if printed, else null.
- year: the 4-digit academic/exam year if shown (use the starting year of a 2024/2025 range), else null.
- exam_session: 'CA1' | 'CA2' if it's a continuous assessment, 'exam' if it's a (semester) Examination, else null.
- doc_type: 'CA' or 'exam'.
- confidence: 0..1, your confidence in the course_code/title."""

def read_masthead(image_bytes: bytes, mime_type: str = "image/jpeg", school_hint: str | None = None) -> MastheadRead:
    """Flash masthead read for filing. Result is ALWAYS confirmed with the contributor before saving."""
    sys = _MASTHEAD_PROMPT + (f"\nContributor's school context (for disambiguation): {school_hint}." if school_hint else "")
    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    resp = client.models.generate_content(
        model=settings.model_flash, contents=[part],
        config=types.GenerateContentConfig(
            system_instruction=sys, response_mime_type="application/json",
            response_schema=MastheadRead, temperature=0.0, max_output_tokens=256,
            thinking_config=types.ThinkingConfig(thinking_budget=0)))
    return MastheadRead.model_validate_json(resp.text)


def probe_page_boundary(image_bytes: bytes) -> PageBoundaryProbe:
    """Cheap per-page boundary probe for app.paper_splitter. Mirrors call_pro_vision but uses
    settings.model_flash, a TINY schema, and a small token cap — this is a boundary signal, NOT a
    full OCR. thinking_budget=0 keeps it fast/cheap and avoids the MAX_TOKENS truncation the OCR
    probe documented. Caller does Pydantic validation via the response_schema.
    """
    part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    resp = client.models.generate_content(
        model=settings.model_flash,
        contents=[part],
        config=types.GenerateContentConfig(
            system_instruction=PAGE_BOUNDARY_PROMPT,
            response_mime_type="application/json",
            response_schema=PageBoundaryProbe,
            temperature=0.0,
            max_output_tokens=256,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return PageBoundaryProbe.model_validate_json(resp.text)