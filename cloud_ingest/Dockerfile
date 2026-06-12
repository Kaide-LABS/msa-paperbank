# Cloud Run Job image — corpus ingest test batch.
# pypdfium2 is a self-contained wheel (NO poppler system binary), which is the whole point of the
# pre-build fix; opencv-python-headless + pillow-heif ship their native libs in the wheels, so no
# apt packages are required.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY cloud_ingest/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY app/ ./app/
COPY cloud_ingest/ ./cloud_ingest/

# Batch task: run once and exit (Cloud Run JOB, not a Service).
ENTRYPOINT ["python", "-m", "cloud_ingest.main"]
