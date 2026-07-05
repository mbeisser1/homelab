#!/usr/bin/env bash
# Export named Docker volumes (and optional bind-mount dirs) to timestamped .tgz archives.
# Filenames include the backing container image tag, e.g.:
#   syncthing_config_2.1.1_2026-07-04_13-45-00.tgz
#
# Usage:
#   docker_volume_backup.sh VOLUME [VOLUME ...]
#   docker_volume_backup.sh --preset small
#   docker_volume_backup.sh -o /pool/archive/docker-volumes dockge_dockge_data
#   docker_volume_backup.sh --stop --preset small

set -euo pipefail

DEST="/pool/archive/docker-volumes"
STOP=0
PRESET=""
declare -a VOLUMES=()
declare -a BINDS=()   # entries: /path:label

usage() {
	cat <<EOF
Usage: $(basename "$0") [options] [VOLUME ...]

Export archives to \${DEST}/\${name}_\${version}_YYYY-MM-DD_HH-MM-SS.tgz

Version is read from docker inspect Config.Image on the container using the volume or bind path,
e.g. docker inspect syncthing --format '{{.Config.Image}}' | awk -F: '{print $2}'.
With --stop, versions are resolved before containers are removed.

Options:
  -o DIR        Destination directory (default: $DEST)
  --preset NAME Preset volume/bind list (see below)
  --bind PATH:LABEL
                Also tar a bind-mount directory (not a Docker volume)
  --stop        Stop/start compose projects via docker_compose_manager.sh
  -h            Show this help

Presets:
  small         dockge + nginx-proxy-manager volumes + syncthing config bind

Examples:
  $(basename "$0") dockge_dockge_data networking_nginx-proxy-manager_data
  $(basename "$0") --preset small
  $(basename "$0") --bind /opt/syncthing/config:syncthing_config

Notes:
  syncthing and obsidian-assets (nginx:alpine) use bind mounts, not named volumes.
  obsidian-assets only mounts /pool/docs (already on pool); no volume to export.
EOF
}

die() {
	echo "error: $*" >&2
	exit 1
}

preset_small() {
	VOLUMES+=(
		dockge_dockge_data
		networking_nginx-proxy-manager_data
		networking_nginx-proxy-manager_letsencrypt
	)
	BINDS+=("/opt/syncthing/config:syncthing_config")
}

parse_bind() {
	local spec="$1"
	local path="${spec%%:*}"
	local label="${spec#*:}"

	[[ "$path" != "$label" && -n "$label" ]] || die "invalid --bind (want PATH:LABEL): $spec"
	[[ -d "$path" ]] || die "bind path not found: $path"
	BINDS+=("$spec")
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	-o)
		[[ $# -ge 2 ]] || die "missing argument for -o"
		DEST="$2"
		shift 2
		;;
	--preset)
		[[ $# -ge 2 ]] || die "missing argument for --preset"
		PRESET="$2"
		shift 2
		;;
	--bind)
		[[ $# -ge 2 ]] || die "missing argument for --bind"
		parse_bind "$2"
		shift 2
		;;
	--stop)
		STOP=1
		shift
		;;
	-h|--help)
		usage
		exit 0
		;;
	-*)
		die "unknown option: $1"
		;;
	*)
		VOLUMES+=("$1")
		shift
		;;
	esac
done

if [[ -n "$PRESET" ]]; then
	case "$PRESET" in
	small) preset_small ;;
	*) die "unknown preset: $PRESET" ;;
	esac
fi

[[ ${#VOLUMES[@]} -gt 0 || ${#BINDS[@]} -gt 0 ]] || {
	usage
	exit 1
}

command -v vackup >/dev/null 2>&1 || die "vackup not found on PATH"

mkdir -p "$DEST"
[[ -d "$DEST" ]] || die "destination not writable: $DEST"

timestamp=$(date +"%Y-%m-%d_%H-%M-%S")
failed=0
declare -A VERSION_CACHE=()

sanitize_version() {
	local v="$1"
	v="${v//\//-}"
	v="${v//:/-}"
	v="${v//@/-}"
	printf '%s' "$v"
}

image_version_from_container() {
	local target="$1"
	local ref tag

	[[ -n "$target" ]] || { echo "unknown"; return; }

	ref=$(docker inspect "$target" --format '{{.Config.Image}}' 2>/dev/null) || {
		echo "unknown"
		return
	}

	ref="${ref%%@*}"
	tag=$(printf '%s\n' "$ref" | awk -F: '{print $2}')
	[[ -n "$tag" ]] || tag="latest"
	sanitize_version "$tag"
}

container_for_volume() {
	docker ps -a --filter "volume=${1}" --format '{{.Names}}' | head -1
}

container_for_bind() {
	local path="$1"
	local resolved cid src

	resolved=$(realpath "$path" 2>/dev/null || echo "$path")

	while IFS= read -r cid; do
		[[ -n "$cid" ]] || continue
		while IFS= read -r src; do
			[[ -n "$src" ]] || continue
			if [[ "$(realpath "$src" 2>/dev/null || echo "$src")" == "$resolved" ]]; then
				docker inspect "$cid" --format '{{.Name}}' | sed 's|^/||'
				return 0
			fi
		done < <(docker inspect "$cid" --format '{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}}{{"\n"}}{{end}}{{end}}')
	done < <(docker ps -aq)

	return 1
}

image_for_volume() {
	local vol="$1"
	local container

	container=$(container_for_volume "$vol")
	image_version_from_container "$container"
}

image_for_bind() {
	local path="$1"
	local container

	container=$(container_for_bind "$path") || true
	image_version_from_container "$container"
}

cache_versions() {
	local vol spec path label

	for vol in "${VOLUMES[@]}"; do
		VERSION_CACHE["volume:${vol}"]=$(image_for_volume "$vol")
	done
	for spec in "${BINDS[@]}"; do
		path="${spec%%:*}"
		label="${spec#*:}"
		VERSION_CACHE["bind:${label}"]=$(image_for_bind "$path")
	done
}

cached_version_for_volume() {
	local vol="$1"
	local version

	version="${VERSION_CACHE["volume:${vol}"]:-$(image_for_volume "$vol")}"
	printf '%s' "$version"
}

cached_version_for_bind() {
	local label="$1"
	local path="$2"
	local version

	version="${VERSION_CACHE["bind:${label}"]:-$(image_for_bind "$path")}"
	printf '%s' "$version"
}

archive_name() {
	local base="$1"
	local version="$2"
	printf '%s_%s_%s.tgz' "$base" "$(sanitize_version "$version")" "$timestamp"
}

stop_containers() {
	local mgr
	mgr=$(command -v docker_compose_manager.sh) || die "docker_compose_manager.sh not found (required for --stop)"
	echo "Stopping compose projects..."
	"$mgr" stop || die "failed to stop compose projects"
}

start_containers() {
	local mgr
	mgr=$(command -v docker_compose_manager.sh) || return 1
	echo "Starting compose projects..."
	"$mgr" start
}

backup_volume() {
	local volume="$1"
	local version outfile

	version=$(cached_version_for_volume "$volume")
	outfile="${DEST}/$(archive_name "$volume" "$version")"

	if ! docker volume inspect "$volume" >/dev/null 2>&1; then
		echo "ERROR: Docker volume not found: $volume" >&2
		return 1
	fi

	echo "Backing up volume $volume (image tag: $version) -> $outfile"
	if vackup export "$volume" "$outfile"; then
		echo "OK: $volume"
	else
		echo "ERROR: failed to export $volume" >&2
		return 1
	fi
}

backup_bind() {
	local path="$1"
	local label="$2"
	local parent base version outfile

	parent=$(dirname "$path")
	base=$(basename "$path")
	version=$(cached_version_for_bind "$label" "$path")
	outfile="${DEST}/$(archive_name "$label" "$version")"

	echo "Backing up bind $path (image tag: $version) -> $outfile"
	if tar -czf "$outfile" -C "$parent" "$base"; then
		echo "OK: $label"
	else
		echo "ERROR: failed to tar $path" >&2
		return 1
	fi
}

if (( STOP )); then
	cache_versions
	stop_containers
	trap 'start_containers || true' EXIT
else
	cache_versions
fi

for volume in "${VOLUMES[@]}"; do
	backup_volume "$volume" || ((failed++)) || true
done

for spec in "${BINDS[@]}"; do
	backup_bind "${spec%%:*}" "${spec#*:}" || ((failed++)) || true
done

if (( STOP )); then
	trap - EXIT
	start_containers || ((failed++)) || true
fi

echo
if [[ $failed -eq 0 ]]; then
	echo "All backups completed. Archives in: $(realpath "$DEST")"
	exit 0
fi

echo "WARNING: $failed backup(s) failed. Partial archives in: $(realpath "$DEST")" >&2
exit 1
