"""Removed model-provider integration."""

def route(*args, **kwargs):
    raise NotImplementedError("LLM routing is not part of the self-hosted service")

def probe_page_boundary(*args, **kwargs):
    raise NotImplementedError("OCR ingest is not part of the self-hosted service")
