#!/usr/bin/env bash
set -euo pipefail

APP_NAME="xwiki"
DATA_DIR="/pool/hosted/docker/${APP_NAME}"

mkdir -p "$DATA_DIR/web"
mkdir -p "$DATA_DIR/db"

# Default ownership model: root:hosted
chown -R root:hosted "$DATA_DIR"
chmod -R 2775 "$DATA_DIR"

echo "Directories for $APP_NAME created at $DATA_DIR"
