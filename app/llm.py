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
The bot only serves the course MTH102 (General Mathematics II) in Phase 1.
Given the user's WhatsApp text, output JSON matching the provided schema.
- If the user is asking for an MTH102 past paper, set intent='paper_request',
  course_code='MTH102', and extract year (4 digits) and semester
  ('harmattan' for Harmattan/first semester, 'rain' for Rain/second semester).
- If the user greets or thanks, set intent='greeting'.
- Otherwise intent='other'.
- confidence is your own 0..1 estimate.
Never invent a course code other than MTH102.
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