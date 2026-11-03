# syntax=docker/dockerfile:1
# SafeSpeak PES backend image (FastAPI + TAT monitor + local ML inference).
# Build context: repository root (the selected model artifact lives in ml/):
#   docker build -f backend/Dockerfile -t safespeak-backend .
# No secrets are baked in: all configuration comes from environment variables.

# ---- build stage: dependencies in a virtual environment ----
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY backend/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install -r /tmp/requirements.txt

# ---- runtime stage ----
FROM python:3.13-slim AS runtime
# Which versioned model artifact to ship (ml/artifacts/<MODEL_VERSION>; v3 = Phase-2 pipeline).
ARG MODEL_VERSION=v3
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_DIR=/app/ml/artifacts/${MODEL_VERSION} \
    REPORTS_DIR=/app/ml/reports/${MODEL_VERSION} \
    MEDIA_DIR=/app/media

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home --shell /usr/sbin/nologin app

COPY --from=build /opt/venv /opt/venv
WORKDIR /app/backend
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/seed ./seed
COPY --chmod=0755 backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# Read-only model artifact (inference only; the backend never trains) and its evaluation reports.
# deployed.json lists the two models the backend loads; their SHA-256 checksums are verified at startup.
COPY ml/artifacts/${MODEL_VERSION} /app/ml/artifacts/${MODEL_VERSION}
COPY ml/reports /app/ml/reports
# Uploaded profile photos (a named volume in Compose, so they survive rebuilds); writable by the app user only.
RUN mkdir -p /app/media && chown app:app /app/media && chmod 0750 /app/media

USER app
EXPOSE 8000
# Healthy = the API answers and the database is reachable. A missing ML model does not make the
# container unhealthy: complaints are still accepted and sent to human review, and /health reports
# "degraded" (the CI smoke test separately requires the model to be loaded).
HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=6 \
  CMD python -c "import json,sys,urllib.request; h=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)); sys.exit(0 if h['database']=='ok' else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
# One worker: exactly one automatic TAT monitor per deployment.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
