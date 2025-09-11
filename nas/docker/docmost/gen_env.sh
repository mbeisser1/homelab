#!/bin/bash
APP_SECRET=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '\n' | sed 's/[\/:=]/_/g')

cat > .env <<EOF
APP_URL=https://docmost.lan.bitrealm.dev
APP_SECRET=${APP_SECRET}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
TZ=America/New_York
DOCMOST_BIND=127.0.0.1
DOCMOST_PORT=3090
EOF

chmod 600 .env
