#!/usr/bin/env bash
# generate_homarr_env.sh
# Generates a .env file for Homarr in /pool/repo/docker/homarr

set -euo pipefail

TARGET_DIR="/pool/repo/docker/homarr"
ENV_FILE="$TARGET_DIR/.env"

# ensure target dir exists
mkdir -p "$TARGET_DIR"

# generate a 64-character hex key
SECRET_KEY=$(openssl rand -hex 32)

cat > "$ENV_FILE" <<EOF
# Homarr configuration
# 64-character hex string used to encrypt sensitive data
SECRET_ENCRYPTION_KEY=$SECRET_KEY
EOF

chmod 600 "$ENV_FILE"

echo ".env created at $ENV_FILE"
echo "SECRET_ENCRYPTION_KEY=$SECRET_KEY"
