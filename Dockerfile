# syntax=docker/dockerfile:1
# Multi-stage build for the self-hosted, no-GPU school deployment (Phase 5).
#
# The embedding model is BAKED INTO THE IMAGE (builder stage pre-downloads it into
# the Hugging Face cache; the final stage copies that cache and sets HF_HUB_OFFLINE=1)
# so the container boots and encodes with NO network fetch — the school server may
# have no outbound internet at container start. The model is still loaded lazily at
# first encode, from the baked local cache.
#
# The image contains no secret and no GCP credential; it runs as a non-root user.

# ---- Builder: install deps into a venv and pre-download the CPU model ----
FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the local CPU embedding model into the image's Hugging Face cache so the
# final stage can run fully offline. This is the ONLY network access in the build;
# at container run time HF_HUB_OFFLINE=1 forbids any fetch.
ENV HF_HOME=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-mpnet-base-v2')"

# ---- Final: slim runtime, offline, non-root ----
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# Copy the populated venv and the baked model cache from the builder.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf-cache /opt/hf-cache

WORKDIR /app
# Application trees only — no .env, no credentials (see .dockerignore).
COPY app ./app
COPY admin ./admin
COPY migrations ./migrations
COPY apply_migrations.py ./apply_migrations.py

# Run as a non-root user; it owns only what it needs to read.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app /opt/hf-cache
USER appuser

EXPOSE 8080
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "60"]
