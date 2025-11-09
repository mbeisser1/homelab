#!/usr/bin/env bash
set -euo pipefail

# Configurable:
: "${QUALITY:=80}"      # webp quality 0-100
: "${MAX:=1024}"           # max dimension (pixels)
: "${JOBS:=$(7)}"     # parallel jobs (defaults to CPU count)
: "${DRY_RUN:=0}"      # set to 1 for dry-run (no writes)
: "${VERBOSE:=1}"      # 0 = quiet, 1 = verbose

export MAX QUALITY JOBS DRY_RUN VERBOSE

# Helper checks
have_cmd() { command -v "$1" >/dev/null 2>&1; }

# Convert/identify are ImageMagick v6 names; prefer cwebp/gif2webp where possible
if ! have_cmd identify && have_cmd convert; then
  echo "Note: using ImageMagick v6 'identify'/'convert' -- ensure they're in PATH."
fi

process_file() {
  local file="$1"
  local ext="${file##*.}"
  local ext_l="${ext,,}"
  local out="${file%.*}.webp"

  # avoid clobber
  if [[ -f "$out" ]]; then
    local base="${file%.*}"
    local suffix=1
    while [[ -f "${base}_${suffix}.webp" ]]; do suffix=$((suffix+1)); done
    out="${base}_${suffix}.webp"
  fi

  # Try to get dimensions via identify; if it fails, we'll still try cwebp directly later
  local dims=""
  if have_cmd identify; then
    dims=$(identify -format "%w %h" -- "$file" 2>/dev/null || true)
  fi

  local width height need_resize=0
  if [[ -n "$dims" ]]; then
    read -r width height <<<"$dims"
    if [[ "$width" =~ ^[0-9]+$ && "$height" =~ ^[0-9]+$ ]]; then
      if (( width > MAX || height > MAX )); then
        need_resize=1
      fi
    else
      width="?"
      height="?"
    fi
  else
    width="?"
    height="?"
  fi

  [[ "$VERBOSE" -eq 1 ]] && printf 'PROCESS: %s -> %s (w=%s h=%s resize=%s)\n' "$file" "$out" "$width" "$height" "$need_resize"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi

  local tmp="${out}.tmp.$$"

  case "$ext_l" in
    gif)
      # Prefer gif2webp for animated GIFs
      if have_cmd gif2webp; then
        if (( need_resize )); then
          # gif2webp -resize width height (use MAX and 0 to keep aspect)
          gif2webp -q "$QUALITY" -resize "$MAX" 0 "$file" -o "$tmp" >/dev/null 2>&1 \
            || { echo "WARN: gif2webp failed for $file; falling back to convert."; convert "$file" -coalesce -resize "${MAX}x${MAX}>" -quality "$QUALITY" "$tmp"; }
        else
          gif2webp -q "$QUALITY" "$file" -o "$tmp" >/dev/null 2>&1 \
            || { echo "WARN: gif2webp failed for $file; falling back to convert."; convert "$file" -coalesce -resize "${MAX}x${MAX}>" -quality "$QUALITY" "$tmp"; }
        fi
      else
        # convert fallback (may not preserve animation perfectly)
        convert "$file" -coalesce -resize "${MAX}x${MAX}>" -quality "$QUALITY" "$tmp"
      fi
      ;;
    *)
      # Still images: prefer cwebp, fall back to convert
      if have_cmd cwebp; then
        if (( need_resize )); then
          # resize with convert first to ensure correct resizing, then feed to cwebp
          local resized_tmp="${file%.*}.resized.$$.$ext_l"
          convert "$file" -resize "${MAX}x${MAX}>" "$resized_tmp" >/dev/null 2>&1 \
            || { echo "WARN: convert resize failed for $file; trying cwebp directly."; cwebp -q "$QUALITY" "$file" -o "$tmp" >/dev/null 2>&1 || true; }
          # If resized_tmp exists, use it; otherwise, cwebp may have tried above
          if [[ -f "$resized_tmp" ]]; then
            cwebp -q "$QUALITY" "$resized_tmp" -o "$tmp" >/dev/null 2>&1 \
              || convert "$resized_tmp" -quality "$QUALITY" "$tmp"
            rm -f "$resized_tmp"
          fi
        else
          cwebp -q "$QUALITY" "$file" -o "$tmp" >/dev/null 2>&1 \
            || convert "$file" -quality "$QUALITY" "$tmp"
        fi
      else
        # no cwebp: use convert directly
        if (( need_resize )); then
          convert "$file" -resize "${MAX}x${MAX}>" -quality "$QUALITY" "$tmp"
        else
          convert "$file" -quality "$QUALITY" "$tmp"
        fi
      fi
      ;;
  esac

  if [[ -f "$tmp" ]]; then
    mv -f "$tmp" "$out"
    [[ "$VERBOSE" -eq 1 ]] && printf 'OK: %s\n' "$out"
  else
    # final fallback: try direct cwebp even if identify failed earlier
    if [[ ! -f "$out" && -f "$file" && "$(basename "$file")" != *.webp ]]; then
      if have_cmd cwebp; then
        cwebp -q "$QUALITY" "$file" -o "$tmp" >/dev/null 2>&1 || true
        if [[ -f "$tmp" ]]; then
          mv -f "$tmp" "$out"
          [[ "$VERBOSE" -eq 1 ]] && printf 'OK-fallback: %s\n' "$out"
          return 0
        fi
      fi
    fi

    echo "FAILED: conversion failed for $file"
    rm -f "$tmp"
  fi
}

export -f process_file have_cmd

# Find files and run in parallel
find . -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' -o -iname '*.bmp' -o -iname '*.tif' -o -iname '*.tiff' \) -print0 \
  | parallel --will-cite -0 -j "$JOBS" process_file {}
