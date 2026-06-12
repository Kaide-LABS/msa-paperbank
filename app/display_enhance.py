"""
Gentle, DIAGRAM-SAFE image enhancement for HUMAN-readable retrieval.

This is NOT the OCR path. app.preprocess.preprocess_paper_image is the OCR binarizer (adaptive
threshold -> bilevel) and stays OFF for OCR. THIS function's only audience is the human eye: the
pipeline serves IMAGES (not OCR text) to students, so the served image should be more legible
WHILE preserving diagrams, shading, hand-drawn curves and graphs.

ALLOWED (tone-preserving, diagram-safe) — and all this module does:
  - grayscale (default) OR colour-preserving (LAB-L enhancement) — caller's choice
  - illumination normalisation / deshadow: divide out a VERY-low-frequency background estimate
    (large Gaussian), mean-preserving, so only the broad phone-photo lighting gradient flattens —
    local diagram shading (finer than the kernel) is preserved
  - modest CLAHE (conservative clip ~2.0) to lift faint text without blowing out gradients
  - light EDGE-PRESERVING denoise (gentle bilateral) — smooths sensor noise without smearing strokes
  - mild deskew only when trivially safe (small angle, clear text lines)

FORBIDDEN (kills diagrams / over-processes) — this module does NONE of these:
  - NO thresholding / binarisation / bilevel output (the whole point)
  - NO aggressive sharpening / strong unsharp mask
  - NO morphological erode/dilate on the output (eats thin diagram lines)
  - NO adaptive thresholding (that's the OCR path)

Output is full-tone (8-bit grayscale or BGR colour), full resolution, PNG bytes.
"""
import io
import cv2
import numpy as np
from PIL import Image, ImageOps


# ------------------------------------------------------------------------------------------
# AUTO-ROTATE — bring 90/180/270-rotated scans upright for the DISPLAY path. EXIF first (trusted),
# then a cheap DETERMINISTIC projection heuristic. No heavy dependency, no LLM/Vertex. If
# orientation can't be confidently determined, the image is returned UNCHANGED (never rotate on a
# guess). Order in the serve path: auto_rotate THEN enhance_for_display.
# ------------------------------------------------------------------------------------------
def _line_struct(gray):
    """High when text lines run HORIZONTALLY (upright/upside-down), low when sideways."""
    inv = 255.0 - gray.astype(np.float64)
    prof = inv.sum(axis=1)
    m = prof.mean()
    if m < 1e-6:
        return 0.0
    prof = prof / m
    k = max(11, (len(prof) // 25) | 1)
    sm = cv2.GaussianBlur(prof.reshape(-1, 1).astype(np.float32), (1, k), 0).ravel()
    return float(((prof - sm) ** 2).mean())


def _vcom(gray):
    """Vertical centre-of-mass of ink, 0 (top) .. 1 (bottom). Documents are TOP-LOADED (masthead +
    content near the top, trailing whitespace below), so the upright orientation has a smaller
    value than its upside-down flip. Robust to where the text block sits horizontally and to
    right-aligned marks (unlike a left/right cue)."""
    inv = 255.0 - gray.astype(np.float64)
    rowink = inv.sum(axis=1)
    tot = rowink.sum()
    if tot <= 0:
        return 0.5
    idx = np.arange(len(rowink), dtype=np.float64)
    return float((rowink * idx).sum() / tot / len(rowink))


def _crop_to_page(gray):
    """Crop to the bright PAGE region (paper is brighter than a desk/floor background) so the
    orientation metrics see the document, not the clutter around it. Returns gray unchanged if no
    confident page blob is found."""
    _, m = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return gray
    x, y, w, h = cv2.boundingRect(max(cnts, key=cv2.contourArea))
    if w * h < 0.15 * gray.size:        # blob too small to trust as "the page"
        return gray
    return gray[y:y + h, x:x + w]


def _detect_rotation(img):
    """Return the rotation to APPLY (0/90/270) to make the page upright, or 0 if not confident.
    180 is never returned — an upright-vs-upside-down flip can't be told apart safely here."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    s = max(gray.shape)
    if s > 1000:
        f = 1000.0 / s
        gray = cv2.resize(gray, (int(gray.shape[1] * f), int(gray.shape[0] * f)))
    gray = _crop_to_page(gray)          # focus on the paper, drop background clutter
    g = {0: gray,
         90: cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE),
         180: cv2.rotate(gray, cv2.ROTATE_180),
         270: cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)}
    ls = {a: _line_struct(g[a]) for a in g}
    portrait = max(ls[0], ls[180])      # text lines already horizontal
    landscape = max(ls[90], ls[270])    # text lines horizontal only after a quarter turn
    if landscape < portrait * 1.15:     # not clearly sideways -> leave upright as-is (no 180 guessing)
        return 0
    v = {90: _vcom(g[90]), 270: _vcom(g[270])}   # upright candidate is the more TOP-LOADED one
    if abs(v[90] - v[270]) < 0.04:      # up/down ambiguous -> don't guess
        return 0
    return 90 if v[90] < v[270] else 270


def auto_rotate(image_bytes: bytes) -> bytes:
    """Return image bytes rotated upright when confident, else the input unchanged. EXIF
    orientation is trusted first; otherwise the deterministic heuristic above decides."""
    # 1) EXIF orientation (phone cameras often record this; WhatsApp recompression usually strips it)
    try:
        im = Image.open(io.BytesIO(image_bytes))
        if im.getexif().get(0x0112, 1) not in (1, None):
            fixed = ImageOps.exif_transpose(im).convert("RGB")
            buf = io.BytesIO(); fixed.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        pass
    # 2) deterministic projection heuristic
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes
    rot = _detect_rotation(img)
    if rot == 0:
        return image_bytes
    code = {90: cv2.ROTATE_90_CLOCKWISE, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rot]
    ok, buf = cv2.imencode(".png", cv2.rotate(img, code))
    return bytes(buf.tobytes()) if ok else image_bytes


def _mild_deskew(img):
    """Correct only a small, clearly-detected skew. Skips if angle is tiny or large (unsafe)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 200,
                            minLineLength=max(50, gray.shape[1] // 3), maxLineGap=20)
    if lines is None:
        return img, 0.0
    angles = []
    for ln in lines:
        x1, y1, x2, y2 = ln[0]
        a = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if -15 < a < 15:
            angles.append(a)
    if not angles:
        return img, 0.0
    med = float(np.median(angles))
    if abs(med) < 0.5 or abs(med) > 15:   # too small to matter, or too large to trust
        return img, 0.0
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w // 2, h // 2), med, 1.0)
    out = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return out, med


def _flatfield(gray):
    """Mean-preserving illumination normalisation. Estimate the broad lighting with a large
    Gaussian (~1/8 of the short side) and divide it out; only the page-wide shadow gradient is
    flattened, finer diagram tones survive."""
    h, w = gray.shape
    k = max(31, (min(h, w) // 8) | 1)        # odd kernel ~1/8 of the smaller dimension
    bg = cv2.GaussianBlur(gray, (k, k), 0).astype(np.float32)
    bg = np.maximum(bg, 1.0)
    mean_bg = float(bg.mean())
    norm = gray.astype(np.float32) / bg * mean_bg
    return np.clip(norm, 0, 255).astype(np.uint8)


def _clahe(gray, clip=2.0, grid=8):
    return cv2.createCLAHE(clipLimit=clip, tileGridSize=(grid, grid)).apply(gray)


def enhance_for_display(image_bytes: bytes, color: bool = False, deskew: bool = True,
                        clahe_clip: float = 2.0, clahe_grid: int = 8) -> bytes:
    """Gentle, diagram-safe enhancement for human reading. Returns PNG bytes (full-tone).

    color=False -> grayscale (usually cleaner for text).
    color=True  -> colour preserved (enhance only the LAB L channel) for colour-coded diagrams.
    """
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("undecodable image")

    if deskew:
        img, _ = _mild_deskew(img)

    if color:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        L, a, b = cv2.split(lab)
        L = _flatfield(L)
        L = _clahe(L, clahe_clip, clahe_grid)
        out = cv2.cvtColor(cv2.merge([L, a, b]), cv2.COLOR_LAB2BGR)
        out = cv2.bilateralFilter(out, 5, 30, 30)        # gentle, edge-preserving
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = _flatfield(gray)
        gray = _clahe(gray, clahe_clip, clahe_grid)
        out = cv2.bilateralFilter(gray, 5, 30, 30)

    ok, buf = cv2.imencode(".png", out)
    if not ok:
        raise ValueError("encode failed")
    return bytes(buf.tobytes())
