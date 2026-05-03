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