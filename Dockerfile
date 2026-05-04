# SolarSTATA v3 - backend container
# Phase 1: backend only. Frontend will be added in Phase 2 (multi-stage build).

FROM python:3.11-slim

WORKDIR /app

# System deps for pyreadstat (.dta I/O) and scientific Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/README.md /app/backend/README.md
RUN pip install --no-cache-dir --upgrade pip
RUN cd /app/backend && pip install --no-cache-dir -e .

# Copy application source
COPY backend/src /app/backend/src

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SOLARSTATA_HOST=0.0.0.0 \
    SOLARSTATA_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz').read()" || exit 1

CMD ["uvicorn", "solarstata.main:app", "--host", "0.0.0.0", "--port", "8000"]
