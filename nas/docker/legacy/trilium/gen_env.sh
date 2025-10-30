#!/usr/bin/env bash
# gen_env.sh — generate .env file for Trilium container

set -euo pipefail

# Defaults
ENV_FILE=".env"
UID_VAL=$(id -u mbeisser)
GID_VAL=$(getent group hosted | cut -d: -f3)

# Generate a random API key
API_KEY=$(openssl rand -base64 32)

cat > "$ENV_FILE" <<EOF
# .env for Trilium Next
USER_UID=$UID_VAL
USER_GID=$GID_VAL

# Paths inside the container
TRILIUM_DATA_DIR=/home/node/trilium-data
TRILIUM_DOCUMENT_PATH=/home/node/trilium-data/document.db
TRILIUM_CONFIG_INI_PATH=/home/node/trilium-data/config.ini
TRILIUM_BACKUP_DIR=/home/node/trilium-backup
TRILIUM_LOG_DIR=/home/node/trilium-log

# REST API key (use in Authorization: Bearer ...)
TRILIUM_API_KEY=$API_KEY
EOF

echo "✅ Wrote $ENV_FILE with random TRILIUM_API_KEY"
echo "   API key is: $API_KEY"
