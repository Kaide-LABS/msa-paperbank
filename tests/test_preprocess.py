import pytest
import cv2
import numpy as np
from app.preprocess import preprocess_paper_image
from app.errors import PreprocessError

def create_synthetic_jpeg(width, height):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    return bytes(buf.tobytes())

def test_preprocess_decodes_png_jpg():
    b = create_synthetic_jpeg(400, 400)
    out = preprocess_paper_image(b)
    assert isinstance(out, bytes)
    decoded = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[0] == 400
    assert decoded.shape[1] == 400

def test_preprocess_rejects_tiny_image():
    b = create_synthetic_jpeg(50, 50)
    with pytest.raises(PreprocessError, match="image too small"):
        preprocess_paper_image(b)

def test_preprocess_rejects_garbage():
    with pytest.raises(PreprocessError, match="undecodable image"):
        preprocess_paper_image(b"\x00\x01\x02")


# --- Decision 2: prepare_images_for_ocr chokepoint (preprocess off by default) ---

def test_prepare_images_for_ocr_off_by_default_returns_raw():
    from app.preprocess import prepare_images_for_ocr
    from app.config import settings
    assert settings.ocr_preprocess_enabled is False  # Decision 2 default
    raw = [b"img-a", b"img-b"]
    out = prepare_images_for_ocr(raw)
    assert out == raw                # bytes unchanged — straight to OCR
    assert out is not raw            # returns a fresh list, not the same object

def test_prepare_images_for_ocr_enabled_runs_preprocess(monkeypatch):
    import app.preprocess as pp
    from app.config import settings
    seen = []
    monkeypatch.setattr(pp, "preprocess_paper_image", lambda b: seen.append(b) or (b + b"!"))
    monkeypatch.setattr(settings, "ocr_preprocess_enabled", True)
    out = pp.prepare_images_for_ocr([b"x", b"y"])
    assert out == [b"x!", b"y!"]     # each image passed through preprocess_paper_image
    assert seen == [b"x", b"y"]