# ==============================================================================
# Dockerfile for CBT Backend (AI Tutor & Licensing Server)
# Compatible with Docker, Docker Compose, and Serverless Container Platforms
# (Google Cloud Run, Render, AWS App Runner, Fly.io, Railway, Koyeb)
# ==============================================================================

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies (curl for healthchecks, build essentials if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first to leverage Docker layer caching
COPY pyproject.toml .

# Install dependencies directly using pip
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    "fastapi[standard]>=0.110.0" \
    "uvicorn[standard]>=0.28.0" \
    "pydantic>=2.6.0" \
    "sqlalchemy>=2.0.0" \
    "cryptography>=41.0.0" \
    "google-genai>=2.19.0" \
    "httpx>=0.28.1" \
    "python-dotenv>=1.0.0" \
    "requests>=2.31.0"

# Copy application source code and data
COPY app/ ./app/
COPY data/ ./data/
COPY create_tables.py .
COPY seed_exam.py .

# Create directory for persistent SQLite database and license keys
RUN mkdir -p /app/data /app/storage

# Expose default port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# Start the server (dynamically binds to $PORT supplied by serverless hosts like Cloud Run/Render)
CMD ["sh", "-c", "uvicorn app.ai_tutor.main:app --host 0.0.0.0 --port ${PORT}"]
