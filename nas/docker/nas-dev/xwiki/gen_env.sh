#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=".env"

cat > "$ENV_FILE" <<EOF
# XWiki version (tagged release)
XWIKI_VERSION=17.7.0

# Database settings
DB_USER=xwiki
DB_PASSWORD=$(openssl rand -base64 32)
DB_DATABASE=xwiki
POSTGRES_ROOT_PASSWORD=$(openssl rand -base64 32)
EOF

chmod 600 "$ENV_FILE"
echo ".env file created with random secrets."
