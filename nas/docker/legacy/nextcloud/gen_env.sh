#!/usr/bin/env bash
set -euo pipefail

APP="nextcloud"
REPO_DIR="$(pwd)"   # assume we're in /pool/repo/docker/nextcloud
DATA_DIR="/pool/hosted/docker/$APP"
ENV_FILE="$REPO_DIR/.env"

APP_USER="mbeisser"
APP_GROUP="hosted"

# 1. Create .env if missing
if [[ -f "$ENV_FILE" ]]; then
  echo ".env already exists at $ENV_FILE, skipping creation."
else
  MYSQL_ROOT_PASSWORD=$(openssl rand -base64 24)
  MYSQL_PASSWORD=$(openssl rand -base64 24)
  ONLYOFFICE_JWT_SECRET=$(openssl rand -hex 64)

  cat > "$ENV_FILE" <<EOF
# Timezone
TZ=America/New_York

# WireGuard IP of NAS
WG_IP=10.0.0.2

# Database settings
MYSQL_ROOT_PASSWORD=$MYSQL_ROOT_PASSWORD
MYSQL_DATABASE=nextcloud
MYSQL_USER=nextcloud
MYSQL_PASSWORD=$MYSQL_PASSWORD

# OnlyOffice JWT
ONLYOFFICE_JWT_SECRET=$ONLYOFFICE_JWT_SECRET
EOF

  echo "✅ Created .env at $ENV_FILE"
  echo "   MYSQL_ROOT_PASSWORD=$MYSQL_ROOT_PASSWORD"
  echo "   MYSQL_PASSWORD=$MYSQL_PASSWORD"
  echo "   ONLYOFFICE_JWT_SECRET=$ONLYOFFICE_JWT_SECRET"
fi

# 2. Create required data directories
for d in db redis app; do
  sudo mkdir -p "$DATA_DIR/$d"
done

# 3. Apply ownerships & permissions
# Repo dir -> mbeisser:hosted
sudo chown -R $APP_USER:$APP_GROUP "$REPO_DIR"
sudo chmod -R 775 "$REPO_DIR"

# Data dir -> root:hosted with sticky group bit
sudo chown -R root:$APP_GROUP "$DATA_DIR"
sudo chmod -R 2775 "$DATA_DIR"

echo "✅ Repo: $REPO_DIR ($APP_USER:$APP_GROUP)"
echo "✅ Data: $DATA_DIR (root:$APP_GROUP, sticky group bit)"
