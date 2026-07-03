#!/usr/bin/env bash
# Rename media files to {prefix}-YYYY-mm-DD__HH-MM-SS.{ext} using EXIF dates.
# Dry run by default; pass --execute to apply renames.
#
# Usage:
#   ./scripts/rename_by_exif.sh Ava
#   ./scripts/rename_by_exif.sh Ava /path/to/photos
#   ./scripts/rename_by_exif.sh --execute Ava /path/to/photos
#   ./scripts/rename_by_exif.sh --debug Ava /path/to/photos

set -euo pipefail

EXECUTE=0
DEBUG=0
PREFIX=""
DIR="."

usage() {
    cat <<'EOF'
Rename files from EXIF capture time.

  rename_by_exif.sh [--execute|-x] [--debug] PREFIX [DIR]

Format:
  {PREFIX}-YYYY-mm-DD__HH-MM-SS.{ext}

Duplicate timestamps bump the seconds field (00, 01, 02, ...).

Date tags tried in order: DateTimeOriginal, CreateDate, ModifyDate.

Options:
  --execute, -x   Apply renames (default is dry run)
  --debug         Show raw EXIF values and parsed datetime
  --help, -h      Show this help

Requires: exiftool
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

debug() {
    (( DEBUG )) && echo "DEBUG: $*" >&2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --execute|-x)
            EXECUTE=1
            shift
            ;;
        --debug)
            DEBUG=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            die "Unknown option: $1 (try --help)"
            ;;
        *)
            if [[ -z "$PREFIX" ]]; then
                PREFIX="$1"
            elif [[ "$DIR" == "." ]]; then
                DIR="$1"
            else
                die "Too many arguments (try --help)"
            fi
            shift
            ;;
    esac
done

[[ -n "$PREFIX" ]] || { usage; exit 1; }
command -v exiftool >/dev/null 2>&1 || die "exiftool not found on PATH"
[[ -d "$DIR" ]] || die "Not a directory: $DIR"

shopt -s nullglob nocaseglob

extensions=(jpg jpeg png tif tiff heic heif webp gif mp4 mov avi mkv m4v mpg mpeg 3gp)

# Parse EXIF date strings ourselves — exiftool -d can emit "…__HH-MM-" when
# seconds are missing, which breaks naive splitting.
parse_exif_raw() {
    local raw="$1"
    raw=${raw//$'\r'/}
    raw=${raw#"${raw%%[![:space:]]*}"}
    raw=${raw%"${raw##*[![:space:]]}"}
    [[ -n "$raw" && "$raw" != "-" ]] || return 1

    if [[ "$raw" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})\ ([0-9]{2}):([0-9]{2}):([0-9]{2})$ ]]; then
        printf '%04d-%02d-%02d__%02d-%02d-%02d' \
            "$((10#${BASH_REMATCH[1]}))" "$((10#${BASH_REMATCH[2]}))" "$((10#${BASH_REMATCH[3]}))" \
            "$((10#${BASH_REMATCH[4]}))" "$((10#${BASH_REMATCH[5]}))" "$((10#${BASH_REMATCH[6]}))"
        return 0
    fi

    if [[ "$raw" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})\ ([0-9]{2}):([0-9]{2})$ ]]; then
        printf '%04d-%02d-%02d__%02d-%02d-00' \
            "$((10#${BASH_REMATCH[1]}))" "$((10#${BASH_REMATCH[2]}))" "$((10#${BASH_REMATCH[3]}))" \
            "$((10#${BASH_REMATCH[4]}))" "$((10#${BASH_REMATCH[5]}))"
        return 0
    fi

    if [[ "$raw" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})$ ]]; then
        printf '%04d-%02d-%02d__00-00-00' \
            "$((10#${BASH_REMATCH[1]}))" "$((10#${BASH_REMATCH[2]}))" "$((10#${BASH_REMATCH[3]}))"
        return 0
    fi

    return 1
}

read_exif_datetime() {
    local file="$1"
    local tag raw parsed
    for tag in DateTimeOriginal CreateDate ModifyDate; do
        raw=$(exiftool -s3 "-$tag" "$file" 2>/dev/null || true)
        debug "$file $tag raw=[$raw]"
        parsed=$(parse_exif_raw "$raw" || true)
        if [[ -n "$parsed" ]]; then
            debug "$file parsed=[$parsed]"
            printf '%s' "$parsed"
            return 0
        fi
    done
    return 1
}

already_renamed() {
    local base="$1"
    [[ "$base" =~ ^${PREFIX}-[0-9]{4}-[0-9]{2}-[0-9]{2}__[0-9]{2}-[0-9]{2}-[0-9]{2}\.[^.]+$ ]]
}

name_in_use() {
    local candidate="$1"
    [[ -n "${claimed[$candidate]:-}" || -e "$DIR/$candidate" ]]
}

next_available_name() {
    local dt="$1"
    local ext="$2"
    local hh mm ss_base n=0 ss candidate

    [[ "$dt" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}__([0-9]{2})-([0-9]{2})-([0-9]{2})$ ]] \
        || die "Internal error: bad normalized datetime '$dt'"

    hh="${BASH_REMATCH[1]}"
    mm="${BASH_REMATCH[2]}"
    ss_base="${BASH_REMATCH[3]}"

    while :; do
        ss=$(printf '%02d' $((10#ss_base + n)))
        candidate="${PREFIX}-${dt%%__*}__${hh}-${mm}-${ss}.${ext}"
        if ! name_in_use "$candidate"; then
            printf '%s' "$candidate"
            return 0
        fi
        ((n++))
        if (( n > 59 )); then
            die "Too many collisions for datetime $dt in $DIR"
        fi
    done
}

declare -A claimed=()
renamed=0
skipped=0

for ext in "${extensions[@]}"; do
    for file in "$DIR"/*."$ext"; do
        [[ -f "$file" ]] || continue

        base=$(basename "$file")
        if already_renamed "$base"; then
            echo "SKIP (already renamed): $base"
            ((skipped++)) || true
            continue
        fi

        dt=$(read_exif_datetime "$file") || {
            echo "SKIP (no EXIF date): $base"
            ((skipped++)) || true
            continue
        }

        file_ext_lower=$(printf '%s' "${base##*.}" | tr '[:upper:]' '[:lower:]')
        new_base=$(next_available_name "$dt" "$file_ext_lower")
        claimed[$new_base]="$file"

        if [[ "$base" == "$new_base" ]]; then
            echo "OK (unchanged): $base"
            continue
        fi

        if (( EXECUTE )); then
            mv -- "$file" "$DIR/$new_base"
            echo "RENAMED: $base -> $new_base"
        else
            echo "WOULD RENAME: $base -> $new_base"
        fi
        ((renamed++)) || true
    done
done

if (( EXECUTE )); then
    echo
    echo "Done. Renamed: $renamed, skipped: $skipped"
else
    echo
    echo "Dry run. Would rename: $renamed, skipped: $skipped"
    echo "Re-run with --execute to apply."
fi

