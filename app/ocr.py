from google.genai import types
from app.schemas import OcrPaperExtraction
from app.llm import call_pro_vision
from app.errors import OcrError

OCR_SYSTEM_PROMPT = """You are extracting structured data from a PAU exam paper image.
Return JSON ONLY matching the provided schema.
- questions[]: each entry must contain the verbatim question text. Preserve mathematical notation as plain text.
- Preserve verbatim any section or question headers exactly as printed (e.g. "QUESTION ONE (Compulsory)", "QUESTION TWO") — do not normalise, renumber, or drop them; they mark paper/section boundaries.
- If multiple images are part of one paper, treat them as a single logical document; the user will pass them in reading order.
- If the image is unreadable, set error to a short reason and questions=[].
"""

def ocr_paper(image_bytes_list: list[bytes]) -> OcrPaperExtraction:
    parts = [types.Part.from_bytes(b, mime_type="image/png") for b in image_bytes_list]
    
    try:
        resp_text = call_pro_vision(parts, OCR_SYSTEM_PROMPT, OcrPaperExtraction)
        return OcrPaperExtraction.model_validate_json(resp_text)
    except Exception as e:
        raise OcrError("Failed to OCR paper") from e