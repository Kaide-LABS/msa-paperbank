from google import genai
from google.genai import types
from app.config import settings
from app.schemas import RouterOutput
from app.errors import RouterError

client = genai.Client(
    vertexai=True, 
    project=settings.gcp_project, 
    location=settings.gcp_location
)

ROUTER_SYSTEM_PROMPT = """You are the router for a PAU past-paper WhatsApp bot.
Given the user's WhatsApp text, output JSON matching the provided schema.

- If the user is asking for a past paper, set intent='paper_request' and:
  * course_code: the requested course as a single uppercase token without spaces, e.g. 'MTH102', 'CSC305', 'GST122'. If unsure, set to your best guess; the server will check membership.
  * year: 4-digit integer if mentioned, else null.
  * semester: 'harmattan' for first/Harmattan/dry-season requests, 'rain' for second/Rain/Harmattan terms's counterpart. Null if absent.
  * exam_session: 'CA1' | 'CA2' | 'exam' if obvious, else null. (Add as schema field; see schemas.py.)
- If the user greets or thanks, set intent='greeting'.
- Otherwise intent='other'.
- confidence: your own 0..1 estimate.
Do not invent course codes when the request is plainly off-topic.
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
                max_output_tokens=256,
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
    """Returns the raw resp.text. Caller does Pydantic validation."""
    resp = client.models.generate_content(
        model=settings.model_pro,
        contents=parts,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.0,
            max_output_tokens=4096,
        ),
    )
    return resp.text