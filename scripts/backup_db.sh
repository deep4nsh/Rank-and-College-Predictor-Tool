#!/usr/bin/env bash
set -e

# Online zero-downtime backup script for Physics Wallah GATE Predictor
# Uses SQLite's native online backup API (safe while WAL writes are active)

DB_PATH="${1:-./gate_predictor.db}"
BACKUP_DIR="${2:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/gate_predictor_${TIMESTAMP}.db"

mkdir -p "${BACKUP_DIR}"

if [ ! -f "${DB_PATH}" ]; then
  echo "Error: Database file not found at ${DB_PATH}"
  exit 1
fi

echo "Starting live backup of ${DB_PATH}..."

# Execute SQLite online backup
sqlite3 "${DB_PATH}" ".backup '${BACKUP_FILE}'"

# Verify backup integrity
INTEGRITY=$(sqlite3 "${BACKUP_FILE}" "PRAGMA integrity_check;")
if [ "${INTEGRITY}" != "ok" ]; then
  echo "Backup failed integrity check: ${INTEGRITY}"
  rm -f "${BACKUP_FILE}"
  exit 1
fi

SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "Backup successfully created: ${BACKUP_FILE} (${SIZE})"
echo "Integrity: OK"
