#!/usr/bin/env bash
set -euo pipefail

# -------- Config (adjust if you change layout) --------
APP_NAME="trilium"
DATA_DIR="/pool/hosted/docker/trilium/data"
BACKUP_DIR="/pool/hosted/docker/trilium/backup"
GROUP_NAME="hosted"
HOSTED_GID="20250"
# ------------------------------------------------------

usage() {
  cat <<EOF
Usage: $0 [--online]

Backs up Trilium database and config to:
  ${BACKUP_DIR}/trilium-db_YYYYMMDD_HHMMSS.tgz

Modes:
  (default) Stop-copy-start  : brief downtime, smallest archive
  --online                   : no stop; copies document.db + wal/shm

Assumes: docker compose context is the current working directory.
Tip: run from the folder containing your docker-compose.yml.
EOF
}

ONLINE=0
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then usage; exit 0; fi
if [[ "${1:-}" == "--online" ]]; then ONLINE=1; fi

timestamp() { date +"%Y%m%d_%H%M%S"; }
TS="$(timestamp)"
SNAP_DIR="${BACKUP_DIR}/snapshots/${TS}"
ARCHIVE="${BACKUP_DIR}/trilium-db_${TS}.tgz"

echo "==> Trilium pre-backup started at ${TS}"
echo "    Mode: $([[ $ONLINE -eq 1 ]] && echo 'ONLINE' || echo 'STOP-COPY-START')"
echo "    Data dir:    ${DATA_DIR}"
echo "    Backup dir:  ${BACKUP_DIR}"

# Ensure dirs exist and perms are consistent with your policy
mkdir -p "${SNAP_DIR}"
chgrp -R "${GROUP_NAME}" "${BACKUP_DIR}"
find "${BACKUP_DIR}" -type d -exec chmod 2775 {} +
find "${BACKUP_DIR}" -type f -exec chmod 664 {} + || true

# Detect whether the service is up
SERVICE_ID="$(docker compose ps -q "${APP_NAME}" || true)"
RUNNING=0
if [[ -n "${SERVICE_ID}" ]]; then
  STATE="$(docker inspect -f '{{.State.Status}}' "${SERVICE_ID}" || echo "unknown")"
  [[ "${STATE}" == "running" ]] && RUNNING=1
fi

if [[ $ONLINE -eq 0 && $RUNNING -eq 1 ]]; then
  echo "==> Stopping ${APP_NAME}..."
  docker compose stop -t 20 "${APP_NAME}"
fi

# Copy DB & config (include WAL/SHM if present)
echo "==> Copying database & config..."
cp -a "${DATA_DIR}/document.db" "${SNAP_DIR}/" 2>/dev/null || {
  echo "ERROR: ${DATA_DIR}/document.db not found"; exit 1;
}
# WAL/SHM only exist if the DB is (or was) in WAL mode and currently active
[[ -f "${DATA_DIR}/document.db-wal" ]] && cp -a "${DATA_DIR}/document.db-wal" "${SNAP_DIR}/"
[[ -f "${DATA_DIR}/document.db-shm" ]] && cp -a "${DATA_DIR}/document.db-shm" "${SNAP_DIR}/"
# Config is nice-to-have
[[ -f "${DATA_DIR}/config.ini" ]] && cp -a "${DATA_DIR}/config.ini" "${SNAP_DIR}/" || true

# Package the snapshot
echo "==> Creating archive ${ARCHIVE} ..."
tar -C "${SNAP_DIR}" -czf "${ARCHIVE}" .

# Normalize perms on the result
chgrp -R "${GROUP_NAME}" "${ARCHIVE}" "${SNAP_DIR}" || true
chmod 664 "${ARCHIVE}" || true

if [[ $ONLINE -eq 0 && $RUNNING -eq 1 ]]; then
  echo "==> Starting ${APP_NAME}..."
  docker compose start "${APP_NAME}"
fi

echo "==> Done. Wrote ${ARCHIVE}"

