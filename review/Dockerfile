# paperbank-review — internal review panel. Separate service; reuses app/ (db, whatsapp, config).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY review ./review
EXPOSE 8080
CMD ["gunicorn", "review.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "60"]
