#!/usr/bin/env bash
set -euo pipefail

# Go to repo root (script lives at /pool/repo/homelab/serve.sh)
cd "$(dirname "$0")"

# Create venv if missing
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Upgrade pip quietly
pip install --upgrade pip >/dev/null

# Install or update requirements
pip install -r requirements.txt

# Run mkdocs dev server
exec mkdocs serve
