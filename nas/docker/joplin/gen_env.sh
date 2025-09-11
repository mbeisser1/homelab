#!/usr/bin/env bash
set -euo pipefail

APP="joplin"
REPO_DIR="/pool/repo/docker/$APP"
DATA_DIR="/pool/hosted/docker/$APP"
ENV_FILE="$REPO_DIR/.env"

# Users / groups
APP_USER="mbeisser"
APP_GROUP="hosted"

# 1. Create the .env file if missing
if [[ -f "$ENV_FILE" ]]; then
  echo ".env already exists at $ENV_FILE, skipping creation."
else
  POSTGRES_PASSWORD=$(openssl rand -base64 24)
  cat > "$ENV_FILE" <<EOF
# Timezone
TZ=America/New_York

# Database settings
POSTGRES_USER=joplin
POSTGRES_PASSWORD=$POSTGRES_PASSWORD

# Joplin Server base URL
APP_BASE_URL=https://joplin.lan.bitrealm.dev
EOF
  echo "✅ Created .env with defaults at $ENV_FILE"
  echo "   POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
fi

# 2. Make sure data directories exist
for d in postgres data; do
  mkdir -p "$DATA_DIR/$d"
done

# 3. Fix ownerships
# repo folder -> root:hosted
sudo chown -R root:$APP_GROUP "$REPO_DIR"
sudo chmod -R 775 "$REPO_DIR"

# data folder -> mbeisser:hosted with sticky bit
sudo chown -R $APP_USER:$APP_GROUP "$DATA_DIR"
sudo chmod -R 2775 "$DATA_DIR"

echo "✅ Environment, repo, and data directories prepared."
echo "   Repo:  $REPO_DIR (root:$APP_GROUP)"
echo "   Data:  $DATA_DIR ($APP_USER:$APP_GROUP, sticky group bit)"
