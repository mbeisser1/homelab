#!/usr/bin/env bash
# generate_wikijs_env.sh
# Run this script from inside /pool/repo/docker/wikijs

set -euo pipefail

ENV_FILE=".env"

# Generate a safe Postgres password (24 chars, avoid symbols that break URLs)
POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '\n' | sed 's/[\/:=]/_/g')

cat > "$ENV_FILE" <<EOF
# Wiki.js environment configuration

POSTGRES_PASSWORD=$POSTGRES_PASSWORD
TZ=America/New_York
EOF

chmod 600 "$ENV_FILE"

echo ".env created in $(pwd)"
echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
