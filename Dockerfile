# Multi-stage, production-ready, zero-license Dockerfile
# Optimized for Python 3.12, non-root user execution, and fast layer caching

FROM python:3.12-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment in /opt/venv for clean non-root permissions
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Final runtime image
FROM python:3.12-slim as runtime

WORKDIR /app

# Install runtime tools (curl for healthcheck, sqlite3 for backups)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed virtualenv from builder into world-accessible /opt/venv
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create unprivileged application user
RUN useradd -m -u 1001 pwuser && \
    mkdir -p /app/data /app/db_data /app/reports && \
    chown -R pwuser:pwuser /app /opt/venv

# Copy application source code and data assets
COPY --chown=pwuser:pwuser backend/ /app/backend/
COPY --chown=pwuser:pwuser data/ /app/data/
COPY --chown=pwuser:pwuser scripts/ /app/scripts/

RUN chmod +x /app/scripts/*.sh 2>/dev/null || true

USER pwuser

# Default SQLite database path mounted to persistent volume
ENV DATABASE_URL=sqlite:////app/db_data/gate_predictor.db
ENV WORKERS=4
ENV PORT=8000

EXPOSE 8000

# Container healthcheck on FastAPI JSON health endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Production multi-worker entrypoint
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --proxy-headers --forwarded-allow-ips='*'"]
