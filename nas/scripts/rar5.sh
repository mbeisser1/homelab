#!/usr/bin/env bash
# rar_backup.sh - Create a RAR5 archive with recovery record from a folder
#
# RAR options used:
#   -ma5    → RAR5 archive format
#   -m4     → Compression method “Good”
#   -md128m → 128 MB dictionary size
#   -v10g   → Split into 10 GB volumes
#   -rr10%  → 10% recovery record
#   -htb    → Use BLAKE2 checksums for file names (RAR5 feature)
#   -r      → Recurse subdirectories

set -euo pipefail

if [[ $# -lt 1 ]]; then
	echo "Usage: $0 <folder-to-archive>"
	exit 1
fi

INPUT_DIR="$1"
# Remove trailing slash, get just folder name
BASENAME=$(basename "${INPUT_DIR%/}")

# Create archive name: YYYY-MM-DD <foldername>.rar
#DATESTAMP=$(date +%Y-%m-%d)
ARCHIVE_NAME="${BASENAME}.rar"

# Run rar command with chosen options
rar a -ma5 -m4 -md128m -v10g -rr10% -htb -r "${ARCHIVE_NAME}" "${INPUT_DIR}"

# Test archive after creation
echo "Testing archive integrity..."
rar t "${ARCHIVE_NAME}"

echo "✅ Archive created and tested: ${ARCHIVE_NAME}"
