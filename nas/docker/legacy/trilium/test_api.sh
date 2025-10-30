#!/usr/bin/env bash
# test_api.sh — sanity check for Trilium Next REST API

set -euo pipefail

# Load .env so we get TRILIUM_API_KEY
if [[ -f .env ]]; then
  export $(grep -v '^#' .env | xargs)
else
  echo "❌ .env file not found"
  exit 1
fi

BASE_URL="http://127.0.0.1:8180/api"

echo "🔎 Checking health endpoint..."
curl -s -H "Authorization: Bearer $TRILIUM_API_KEY" "$BASE_URL/health-check" | jq .

echo
echo "📝 Creating test note..."
CREATE_RESP=$(curl -s -X POST \
  -H "Authorization: Bearer $TRILIUM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"parentNoteId":"root","title":"API Test Note","type":"text","content":"Hello from API!"}' \
  "$BASE_URL/notes")

echo "$CREATE_RESP" | jq .

NOTE_ID=$(echo "$CREATE_RESP" | jq -r '.noteId // empty')

if [[ -z "$NOTE_ID" ]]; then
  echo "❌ Failed to create note"
  exit 1
fi

echo
echo "📖 Fetching the note back..."
curl -s -H "Authorization: Bearer $TRILIUM_API_KEY" "$BASE_URL/notes/$NOTE_ID" | jq .
