"""OCR integration boundary; OCR ingest is out of scope for this service."""

def ocr_paper(*args, **kwargs):
    raise NotImplementedError("OCR ingest is not part of the self-hosted service")
