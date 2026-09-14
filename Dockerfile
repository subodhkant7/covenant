# ==============================================================================
# Stage 1: Build React/Vite Frontend
# ==============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy frontend manifests for efficient build caching
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy frontend source and build production bundle
COPY frontend/ ./
RUN npm run build

# ==============================================================================
# Stage 2: Runtime Image with Python & Covenant
# ==============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Set production environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    COVENANT_MODEL_PROVIDER=deterministic

# Install curl for container health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 covenant

# Copy project package manifests and source code
COPY pyproject.toml README.md ./
COPY covenant/ ./covenant/
COPY agent_runtime/ ./agent_runtime/
COPY covenant_runtime_bridge/ ./covenant_runtime_bridge/

# Install the Covenant package in runtime environment
RUN pip install --no-cache-dir .

# Copy production frontend build from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Set directory ownership so SQLite can initialize at runtime
RUN chown -R covenant:covenant /app

USER covenant

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8000}/api/health || exit 1

CMD ["sh", "-c", "exec uvicorn covenant.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
