FROM python:3.11-slim

# Cache bust: force fresh install
ARG CACHE_BUST=3

# git is needed by PyDriller for local repo operations
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (not data/cache or .venv)
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY eval/ ./eval/
COPY config/ ./config/

# Render injects $PORT; default to 8000 locally
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
