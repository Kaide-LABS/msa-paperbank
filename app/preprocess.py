import cv2
import numpy as np
from app.errors import PreprocessError


def prepare_images_for_ocr(image_bytes_list: list[bytes]) -> list[bytes]:
    """Single chokepoint for getting images ready to hand to OCR.

    Decision 2 (2026-06 OCR probe, c:\\tmp\\pau-probe): preprocessing is OFF by default.
    The probe found cv2 deskew/denoise/threshold improved 0/12 sampled files, was neutral
    on clean inputs, and net-negative on degraded ones — it turned a Flash success into a
    hard MAX_TOKENS failure (file 11) and caused a question mis-numbering (file 3). So by
    default raw image bytes (and rasterized PDF pages) flow straight to OCR with no
    preprocessing.

    preprocess_paper_image() is intentionally NOT deleted — flip settings.ocr_preprocess_enabled
    to True to re-enable it for an explicit A/B. settings is imported lazily to avoid a
    config import at module load (preprocess.py is imported by lightweight call sites).
    """
    from app.config import settings

    if not settings.ocr_preprocess_enabled:
        return list(image_bytes_list)
    return [preprocess_paper_image(b) for b in image_bytes_list]


def preprocess_paper_image(image_bytes: bytes) -> bytes:
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise PreprocessError("undecodable image")
    
    if img.shape[0] < 200 or img.shape[1] < 200:
        raise PreprocessError("image too small")
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
    
    edges = cv2.Canny(denoised, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 200, minLineLength=denoised.shape[1]//4, maxLineGap=20)
    
    rotated = denoised
    if lines is not None and len(lines) > 0:
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.arctan2(y2 - y1, x2 - x1)
            if -np.pi/4 <= angle <= np.pi/4:
                angles.append(angle)
        
        if angles:
            median_angle = np.median(angles)
            degrees = np.degrees(median_angle)
            if abs(degrees) > 0.5:
                center = (denoised.shape[1] // 2, denoised.shape[0] // 2)
                m = cv2.getRotationMatrix2D(center, -degrees, 1.0)
                rotated = cv2.warpAffine(denoised, m, (denoised.shape[1], denoised.shape[0]), borderMode=cv2.BORDER_REPLICATE)
                
    thresh = cv2.adaptiveThreshold(rotated, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, blockSize=31, C=10)
    ok, buf = cv2.imencode(".png", thresh)
    if not ok:
        raise PreprocessError("encode failed")
        
    return bytes(buf.tobytes())