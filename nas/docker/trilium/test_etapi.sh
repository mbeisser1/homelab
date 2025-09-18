#!/usr/bin/env bash
# test_etapi.sh — sanity check for Trilium Next ETAPI (0.98.1)

set -euo pipefail

# Put your GUI-generated ETAPI token here (from Options → API Tokens in the UI)
ETAPI_TOKEN="PASTE_YOUR_TOKEN_HERE"

BASE_URL="http://127.0.0.1:8180/etapi"

echo "🔎 Checking ETAPI health..."
curl -s -H "Authorization: $ETAPI_TOKEN" "$BASE_URL/ping" | jq .

echo
echo "📝 Creating test note under root..."
CREATE_RESP=$(curl -s -X POST \
  -H "Authorization: $ETAPI_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"parentNoteId":"root","title":"ETAPI Test Note","type":"text","content":"Hello from ETAPI!"}' \
  "$BASE_URL/notes")

echo "$CREATE_RESP" | jq .

NOTE_ID=$(echo "$CREATE_RESP" | jq -r '.noteId // empty')

if [[ -z "$NOTE_ID" ]]; then
  echo "❌ Failed to create note"
  exit 1
fi

echo
echo "📖 Fetching the note back..."
curl -s -H "Authorization: $ETAPI_TOKEN" "$BASE_URL/notes/$NOTE_ID" | jq .
