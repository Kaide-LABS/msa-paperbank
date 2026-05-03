from io import BytesIO
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from google.cloud import storage

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

def upload_pdf(gcs_client: storage.Client, bucket_name: str, gcs_object: str, pdf_bytes: bytes) -> None:
    bucket = gcs_client.bucket(bucket_name)
    bucket.blob(gcs_object).upload_from_string(pdf_bytes, content_type="application/pdf")