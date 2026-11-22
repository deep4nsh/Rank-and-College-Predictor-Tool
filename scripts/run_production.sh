#!/usr/bin/env bash
set -e

# Production server startup script for Physics Wallah GATE Predictor
# Configures multi-worker Uvicorn with optimized process counts

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
CPU_COUNT=$(python3 -c "import os; print(os.cpu_count() or 2)")
DEFAULT_WORKERS=$(( (2 * CPU_COUNT) + 1 ))
WORKERS="${WORKERS:-$DEFAULT_WORKERS}"

echo "============================================================"
echo "  Starting Physics Wallah GATE Predictor (Production)"
echo "============================================================"
echo "Host:       ${HOST}"
echo "Port:       ${PORT}"
echo "Workers:    ${WORKERS} (CPU Count: ${CPU_COUNT})"
echo "Database:   ${DATABASE_URL:-sqlite:///./gate_predictor.db}"
echo "------------------------------------------------------------"

exec uvicorn backend.app.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --workers "${WORKERS}" \
  --proxy-headers \
  --forwarded-allow-ips='*' \
  --access-log
