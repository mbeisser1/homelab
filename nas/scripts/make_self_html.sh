#!/usr/bin/env bash
set -euo pipefail

# make_self_html.sh
# Batch-convert *.html/*.htm to **self-contained** HTML for Trilium (or anywhere).
# - Uses pandoc: --standalone + --embed-resources  (replaces deprecated --self-contained)
# - Preserves SRC subfolders under DST
# - Skips files already ending in *_self.html
# - Skips up-to-date outputs unless --force
# - Resolves attachments relative to the **SRC** tree (not CWD) via --resource-path
# - Applies your /pool policy: group=hosted, dirs=2775, files=664
#
# Usage:
#   make_self_html.sh -s SRC -d DST [-j 4] [--force] [--dry-run]
#
# Example:
#   make_self_html.sh \
#     -s /pool/Archive/html \
#     -d /pool/hosted/docker/trilium/import_self \
#     -j 6

GROUP="${GROUP:-hosted}"
JOBS=1
FORCE=0
DRYRUN=0
SRC=""
DST=""

die(){ echo "ERROR: $*" >&2; exit 1; }
log(){ echo "==> $*"; }

[[ $# -gt 0 ]] || { grep -E '^# (Usage|Example):' -A6 "$0" | sed 's/^# //'; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--src) SRC="$2"; shift 2;;
    -d|--dst) DST="$2"; shift 2;;
    -j|--jobs) JOBS="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    -h|--help) grep -E '^# (Usage|Example):' -A20 "$0" | sed 's/^# //'; exit 0;;
    *) die "Unknown arg: $1";;
  esac
done

command -v pandoc >/dev/null 2>&1 || die "pandoc not found. Install: sudo apt-get install -y pandoc"
[[ -n "$SRC" && -n "$DST" ]] || die "Provide -s SRC and -d DST"
[[ -d "$SRC" ]] || die "SRC not found: $SRC"
mkdir -p "$DST"

# Normalize SRC & DST to absolute paths (helps with resource paths)
SRC="$(cd "$SRC" && pwd -P)"
DST="$(cd "$DST" && pwd -P)"

log "Renderer: pandoc (--standalone --embed-resources)"
log "Source:   $SRC"
log "Dest:     $DST"
log "Jobs:     $JOBS"
[[ $FORCE -eq 1 ]] && log "Force:    yes"
[[ $DRYRUN -eq 1 ]] && log "Dry-run:  yes"

convert_one() {
  local in="$1"
  local rel="${in#$SRC/}"

  # Skip already self-contained inputs
  [[ "$in" == *_self.html ]] && { echo "[skip] already _self: $rel" >&2; return 0; }

  # Build output path: replace extension with _self.html
  local base="${rel%.*}"
  local out="$DST/${base}_self.html"
  local out_dir
  out_dir="$(dirname "$out")"

  # Skip up-to-date output unless forcing
  if [[ $FORCE -eq 0 && -f "$out" && "$out" -nt "$in" ]]; then
    echo "[skip] up-to-date: $rel" >&2
    return 0
  fi

  if [[ $DRYRUN -eq 1 ]]; then
    echo "[dry]  $rel -> ${out#$DST/}" >&2
    return 0
  fi

  # Ensure output dir with correct perms
  install -d -m 2775 -g "$GROUP" "$out_dir"

  # Make attachments resolve from SRC (and the input file's own directory)
  local in_dir; in_dir="$(dirname "$in")"
  # Use both: the file's directory and the SRC root (covers common layouts)
  local rpath="${SRC}:${in_dir}"

  # Convert with pandoc (new flags)
  pandoc --standalone --embed-resources \
         --resource-path="$rpath" \
         "$in" -o "$out"

  # Normalize perms on output
  chgrp "$GROUP" "$out" 2>/dev/null || true
  chmod 664 "$out" 2>/dev/null || true

  echo "[ok]   $rel -> ${out#$DST/}" >&2
}

export -f convert_one
export SRC DST GROUP FORCE DRYRUN
# shellcheck disable=SC2016
find "$SRC" -type f \( -iname '*.html' -o -iname '*.htm' \) -print0 \
| xargs -0 -I{} -P "$JOBS" bash -c 'convert_one "$@"' _ {}

# final sweep on DST (idempotent)
if [[ $DRYRUN -eq 0 ]]; then
  find "$DST" -type d -exec chmod 2775 {} + 2>/dev/null || true
  find "$DST" -type f -exec chmod 664 {} + 2>/dev/null || true
  chgrp -R "$GROUP" "$DST" 2>/dev/null || true
fi

log "Done."

