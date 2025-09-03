#!/usr/bin/env bash
# list_disks.sh — Disk inventory with partition table type and filesystem labels

set -euo pipefail
command -v lsblk >/dev/null 2>&1 || {
	echo "lsblk not found"
	exit 1
}

# Pull everything once; key="value" pairs
mapfile -t LINES < <(lsblk -P -o NAME,TYPE,PKNAME,SIZE,MODEL,SERIAL,PTTYPE,WWN,FSTYPE,LABEL,UUID,MOUNTPOINT)

declare -A DISK_MODEL DISK_SERIAL DISK_SIZE DISK_PTTYPE DISK_WWN

# Collect disk-level attributes
for line in "${LINES[@]}"; do
	# shellcheck disable=SC2086
	eval $line
	if [[ "$TYPE" == "disk" || "$TYPE" == "rom" ]]; then
		DISK_MODEL["$NAME"]="${MODEL:-}"
		DISK_SERIAL["$NAME"]="${SERIAL:-}"
		DISK_SIZE["$NAME"]="${SIZE:-}"
		DISK_PTTYPE["$NAME"]="${PTTYPE:-}"
		DISK_WWN["$NAME"]="${WWN:-}"
	fi
done

# Fallbacks via udevadm and parted if needed
udefill() {
	local disk="$1"
	[[ -r "/dev/$disk" ]] || return 0
	command -v udevadm >/dev/null 2>&1 || return 0
	local info
	if info=$(udevadm info --query=property --name="/dev/$disk" 2>/dev/null); then
		[[ -z "${DISK_SERIAL[$disk]:-}" ]] && DISK_SERIAL["$disk"]="$(grep -E '^(ID_SERIAL_SHORT|ID_SERIAL)=' <<<"$info" | head -n1 | cut -d= -f2- || true)"
		[[ -z "${DISK_MODEL[$disk]:-}" ]] && DISK_MODEL["$disk"]="$(grep -E '^ID_MODEL=' <<<"$info" | head -n1 | cut -d= -f2- || true)"
		[[ -z "${DISK_WWN[$disk]:-}" ]] && DISK_WWN["$disk"]="$(grep -E '^ID_WWN=' <<<"$info" | head -n1 | cut -d= -f2- || true)"
	fi
}

parted_fill_pttype() {
	local disk="$1"
	command -v parted >/dev/null 2>&1 || return 0
	local pt
	pt=$(sudo parted -s "/dev/$disk" print 2>/dev/null | awk -F': *' '/Partition Table:/ {print $2}' | tr '[:upper:]' '[:lower:]' || true)
	[[ -n "$pt" ]] && DISK_PTTYPE["$disk"]="$pt"
}

for d in "${!DISK_MODEL[@]}"; do
	udefill "$d"
	[[ -z "${DISK_PTTYPE[$d]:-}" ]] && parted_fill_pttype "$d"
done

# Header
printf "%-12s %-10s %-8s %-25s %-25s %-18s %-14s %-8s %-20s %-36s %-s\n" \
	"DISK" "DISK_SIZE" "PTLABEL" "MODEL" "SERIAL" "WWN" "NODE" "FSTYPE" "FS_LABEL" "UUID" "MOUNTPOINT"
printf "%-12s %-10s %-8s %-25s %-25s %-18s %-14s %-8s %-20s %-36s %-s\n" \
	"------------" "----------" "--------" "-------------------------" "-------------------------" "------------------" "--------------" "--------" "--------------------" "------------------------------------" "---------"

declare -A DISK_SEEN

# Rows for each filesystem-bearing node
for line in "${LINES[@]}"; do
	# shellcheck disable=SC2086
	eval $line
	[[ -n "${UUID:-}" ]] || continue
	parent="${PKNAME:-$NAME}"
	printf "%-12s %-10s %-8s %-25s %-25s %-18s %-14s %-8s %-20s %-36s %-s\n" \
		"$parent" \
		"${DISK_SIZE[$parent]:--}" \
		"${DISK_PTTYPE[$parent]:--}" \
		"${DISK_MODEL[$parent]:--}" \
		"${DISK_SERIAL[$parent]:--}" \
		"${DISK_WWN[$parent]:--}" \
		"$NAME" \
		"${FSTYPE:- -}" \
		"${LABEL:- -}" \
		"$UUID" \
		"${MOUNTPOINT:-}"
	DISK_SEEN["$parent"]=1
done

# Disks with no filesystems yet
for d in "${!DISK_MODEL[@]}"; do
	if [[ -z "${DISK_SEEN[$d]:-}" ]]; then
		printf "%-12s %-10s %-8s %-25s %-25s %-18s %-14s %-8s %-20s %-36s %-s\n" \
			"$d" \
			"${DISK_SIZE[$d]:--}" \
			"${DISK_PTTYPE[$d]:--}" \
			"${DISK_MODEL[$d]:--}" \
			"${DISK_SERIAL[$d]:--}" \
			"${DISK_WWN[$d]:--}" \
			"-" "-" "-" "-" "-"
	fi
done

# Notes:
# - PTLABEL = partition table type (gpt/msdos).
# - FS_LABEL = per-partition filesystem volume label.
# - Run with sudo for fuller SERIAL/WWN/PTTYPE data.
