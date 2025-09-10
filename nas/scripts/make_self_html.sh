#!/usr/bin/env bash
set -euo pipefail

# make_self_html.sh (juice-only, with CSS injection)
# - Pandoc:  --standalone --embed-resources
# - CSS:     inject style.css and <stem>.css (if present) from the input dir,
#            then inline with `juice` (Node >= 20)
# - Preserves SRC subfolders under DST
# - Skips *_self.html inputs and up-to-date outputs unless --force
# - Handles spaces in paths; prints per-file status

GROUP="${GROUP:-hosted}"
JOBS=1
FORCE=0
DRYRUN=0
DEBUG=0
SRC=""
DST=""

die(){ echo "ERROR: $*" >&2; exit 1; }
log(){ echo "==> $*"; }

[[ $# -gt 0 ]] || { echo "Usage: $0 -s SRC -d DST [-j 4] [--force] [--dry-run] [--debug]"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--src) SRC="$2"; shift 2;;
    -d|--dst) DST="$2"; shift 2;;
    -j|--jobs) JOBS="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --debug) DEBUG=1; shift;;
    -h|--help) exec sed -n '1,220p' "$0";;
    *) die "Unknown arg: $1";;
  esac
done

[[ $DEBUG -eq 1 ]] && set -x

# Requirements
command -v pandoc >/dev/null 2>&1 || die "pandoc not found. Install: sudo apt-get install -y pandoc"
command -v juice  >/dev/null 2>&1 || die "juice not found. Install under Node >= 20: npm i -g juice"
NODE_VER="$(node -v 2>/dev/null || echo 'none')"
NODE_MAJ="$(echo "$NODE_VER" | sed -E 's/^v([0-9]+).*/\1/' || echo 0)"
case "$NODE_MAJ" in (''|*[!0-9]*) NODE_MAJ=0;; esac
if [ "$NODE_MAJ" -lt 20 ]; then die "Node >= 20 required for juice. Current: $NODE_VER"; fi

[[ -n "$SRC" && -n "$DST" ]] || die "Provide -s SRC and -d DST"
[[ -d "$SRC" ]] || die "SRC not found: $SRC"
mkdir -p "$DST"

# Normalize to absolute paths
SRC="$(cd "$SRC" && pwd -P)"
DST="$(cd "$DST" && pwd -P)"

# Header
log "Pandoc:   $(pandoc -v | head -1)"
log "Node:     $NODE_VER"
log "Juice:    $(juice --version 2>/dev/null || echo 'ok')"
log "Source:   $SRC"
log "Dest:     $DST"
log "Jobs:     $JOBS"
log "Force:    $([[ $FORCE -eq 1 ]] && echo yes || echo no)"
log "Dry-run:  $([[ $DRYRUN -eq 1 ]] && echo yes || echo no)"

convert_one() {
  local in="$1"
  local rel="${in#$SRC/}"

  [[ "$in" == *_self.html ]] && { echo "[skip] already _self: $rel" >&2; return 0; }

  local basefile; basefile="$(basename "$in")"
  local stem="${basefile%.*}"
  local out="$DST/${rel%.*}_self.html"
  local out_dir; out_dir="$(dirname "$out")"
  local in_dir;  in_dir="$(dirname "$in")"

  if [[ $FORCE -eq 0 && -f "$out" && "$out" -nt "$in" ]]; then
    echo "[skip] up-to-date: $rel" >&2
    return 0
  fi
  if [[ $DRYRUN -eq 1 ]]; then
    echo "[dry]  $rel -> ${out#$DST/}" >&2
    return 0
  fi

  install -d -m 2775 -g "$GROUP" "$out_dir"

  # resource-path: file dir, SRC, and common sidecar dirs from browser exports
  declare -a paths=("$in_dir" "$SRC")
  for side in "${stem}_files" "${stem}_resources" "${stem}.assets" "${stem}_assets"; do
    [[ -d "$in_dir/$side" ]] && paths+=("$in_dir/$side")
  done
  local rpath="${paths[0]}"; for ((i=1;i<${#paths[@]};i++)); do rpath="$rpath:${paths[$i]}"; done

  # Build to temp
  local tmp; tmp="$(mktemp --suffix .html -p "$out_dir" ".${stem}_XXXXXX")"
  trap 'rm -f "$tmp" "$tmp.inj" "$tmp.css"' RETURN

  pandoc --standalone --embed-resources --resource-path="$rpath" "$in" -o "$tmp"

  # --- Inject local CSS (style.css and <stem>.css) if present next to input ---
  # This ensures your theme is present even if pandoc didn't embed it.
  css_list=()
  [[ -f "$in_dir/style.css" ]]    && css_list+=("$in_dir/style.css")
  [[ -f "$in_dir/${stem}.css" ]]  && css_list+=("$in_dir/${stem}.css")
  if (( ${#css_list[@]} )); then
    tmp_css="$(mktemp -p "$out_dir" ".${stem}_css_XXXXXX")"
    for cssf in "${css_list[@]}"; do
      {
        echo "<style>"
        cat "$cssf"
        echo "</style>"
      } >> "$tmp_css"
    done
    if grep -qi '</head>' "$tmp"; then
      # Insert before first </head> (case-insensitive)
      sed -e "/<\/[Hh][Ee][Aa][Dd]>/{
r $tmp_css
}" "$tmp" > "$tmp.inj"
    else
      # No </head>: prepend styles
      cat "$tmp_css" "$tmp" > "$tmp.inj"
    fi
    mv -f "$tmp.inj" "$tmp"
  fi
  # ---------------------------------------------------------------------------

  # Inline CSS to element style="" attributes (juice writes to final)
  juice "$tmp" "$out"

  chgrp "$GROUP" "$out" 2>/dev/null || true
  chmod 664 "$out" 2>/dev/null || true

  echo "[ok]   $rel -> ${out#$DST/}" >&2
}

# Collect files
mapfile -d '' FILES < <(find "$SRC" -type f \( -iname '*.html' -o -iname '*.htm' \) -print0)
COUNT="${#FILES[@]}"
if [[ "$COUNT" -eq 0 ]]; then
  echo "No .html/.htm files found under: $SRC"
  exit 0
fi
log "Found $COUNT HTML file(s). Processing..."

# Simple job pool for -j
if [[ "$JOBS" -le 1 ]]; then
  for f in "${FILES[@]}"; do convert_one "$f"; done
else
  running=0
  for f in "${FILES[@]}"; do
    convert_one "$f" &
    running=$((running+1))
    if (( running >= JOBS )); then
      wait -n || true
      running=$((running-1))
    fi
  done
  wait || true
fi

# Final sweep (idempotent)
find "$DST" -type d -exec chmod 2775 {} + 2>/dev/null || true
find "$DST" -type f -exec chmod 664 {} + 2>/dev/null || true
chgrp -R "$GROUP" "$DST" 2>/dev/null || true

log "Done."

