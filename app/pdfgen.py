from io import BytesIO
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from app.ports import ObjectStore

def stitch_images_to_pdf(image_bytes_list: list[bytes]) -> bytes:
    out = BytesIO()
    c = canvas.Canvas(out)
    
    max_diag_sq = (A4[0]**2 + A4[1]**2) * 4
    
    for b in image_bytes_list:
        image = Image.open(BytesIO(b))
        if image.mode != "RGB":
            image = image.convert("RGB")
            
        w, h = image.width, image.height
        
        # sanity cap
        if w**2 + h**2 > max_diag_sq:
            scale = (max_diag_sq / (w**2 + h**2)) ** 0.5
            w = int(w * scale)
            h = int(h * scale)
            
        c.setPageSize((w, h))
        c.drawImage(ImageReader(image), 0, 0, width=w, height=h)
        c.showPage()
        
    c.save()
    return out.getvalue()

def upload_pdf(store: ObjectStore, gcs_object: str, pdf_bytes: bytes) -> None:
    store.upload_bytes(gcs_object, pdf_bytes, content_type="application/pdf")