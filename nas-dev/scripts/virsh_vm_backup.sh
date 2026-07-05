#!/usr/bin/env bash
# Export a shut-off libvirt domain to a timestamped directory under /pool/archive/vm/<domain>/.
#
# Includes domain XML, OVMF NVRAM, swtpm state, disk images, and host-side config by default.
#
# Usage:
#   sudo virsh_vm_backup.sh win11
#   sudo virsh_vm_backup.sh -o /mnt/scratch/vm-backups win11
#   sudo virsh_vm_backup.sh --no-host-config win11
#
# Restore (same host, original paths):
#   sudo cp -a /pool/archive/vm/win11/<timestamp>/disks/* /var/lib/libvirt/images/
#   sudo cp -a /pool/archive/vm/win11/<timestamp>/nvram/* /var/lib/libvirt/qemu/nvram/
#   sudo cp -a /pool/archive/vm/win11/<timestamp>/tpm/<uuid> /var/lib/libvirt/swtpm/
#   sudo chown -R root:root /var/lib/libvirt/images/* /var/lib/libvirt/qemu/nvram/*
#   sudo chown -R root:root /var/lib/libvirt/swtpm/<uuid>    # or tss:tss per distro
#   sudo virsh define /pool/archive/vm/win11/<timestamp>/win11.xml
#   sudo virsh start win11
#
# Guest Looking Glass host ini is NOT backed up by this script; copy manually from:
#   C:\Program Files\Looking Glass (host)\looking-glass-host.ini
#
# On a different host, edit disk/NVRAM paths in the XML before virsh define. PCI passthrough
# and IVSHMEM entries are host-specific.

set -euo pipefail

DEST_BASE="/pool/archive/vm"
HOST_CONFIG=1
DOMAIN=""
DOMAIN_UUID=""
DISK_COUNT=0
SPACE_HEADROOM_PERCENT=5

declare -a MANIFEST_LINES=()
declare -a DISK_PATHS=()

usage() {
	cat <<EOF
Usage: $(basename "$0") [options] DOMAIN

Export a shut-off libvirt domain to:
  \${DEST_BASE}/<domain>/YYYY-MM-DD_HH-MM-SS/

Contents: domain XML, OVMF NVRAM, swtpm TPM state (if present), block device images,
and host-side config (qemu.conf, vfio modprobe, initramfs modules, GRUB IOMMU line,
Looking Glass client.ini).

The VM must already be shut off. Run as root (sudo).

Options:
  -o DIR           Base output directory (default: $DEST_BASE)
  --no-host-config Skip host-side config files
  -h               Show this help

Examples:
  sudo $(basename "$0") win11
  sudo $(basename "$0") -o /mnt/scratch/vm-backups win11
  sudo $(basename "$0") --no-host-config win11
EOF
}

die() {
	echo "error: $*" >&2
	exit 1
}

warn() {
	echo "warning: $*" >&2
}

require_root() {
	[[ "$(id -u)" -eq 0 ]] || die "must run as root (use sudo)"
}

require_commands() {
	local cmd
	for cmd in virsh cp du date find grep sed stat numfmt awk; do
		command -v "$cmd" >/dev/null 2>&1 || die "$cmd not found on PATH"
	done
}

manifest_add() {
	MANIFEST_LINES+=("$1")
}

human_size() {
	numfmt --to=iec-i --suffix=B "$1" 2>/dev/null || echo "${1}B"
}

human_size_file() {
	local bytes
	bytes=$(stat -c '%s' "$1" 2>/dev/null || echo 0)
	human_size "$bytes"
}

nvram_path_from_xml() {
	local xml="$1"
	sed -n "s/.*<nvram>\(.*\)<\/nvram>.*/\1/p" "$xml" | head -1
}

xml_has_tpm() {
	local xml="$1"
	grep -q '<tpm' "$xml"
}

domain_uuid() {
	virsh dominfo "$DOMAIN" | awk '/^UUID:/ {print $2; exit}'
}

collect_disk_paths() {
	local type device target path

	DISK_PATHS=()
	while read -r type device target path; do
		[[ "$type" == Type* ]] && continue
		[[ -z "$target" ]] && continue
		[[ "$device" != disk ]] && continue
		[[ "$path" == "-" || -z "$path" ]] && continue
		[[ -f "$path" ]] || die "disk image not found: $path (target $target)"
		DISK_PATHS+=("$path")
	done < <(virsh domblklist "$DOMAIN" --details)

	[[ ${#DISK_PATHS[@]} -gt 0 ]] || die "no file-backed disk images found for $DOMAIN"
}

disk_bytes_total() {
	local path total=0

	for path in "${DISK_PATHS[@]}"; do
		total=$((total + $(stat -c '%s' "$path")))
	done
	echo "$total"
}

check_disk_space() {
	local need avail headroom dest_parent

	need=$(disk_bytes_total)
	headroom=$((need * SPACE_HEADROOM_PERCENT / 100))
	need=$((need + headroom))

	dest_parent="${DEST_BASE%/}/${DOMAIN}"
	mkdir -p "$dest_parent"
	avail=$(df -B1 --output=avail "$dest_parent" | tail -1 | tr -d ' ')

	if [[ "$avail" -lt "$need" ]]; then
		die "insufficient space on $(df -P "$dest_parent" | tail -1 | awk '{print $1}'): need $(human_size "$need") (disks + ${SPACE_HEADROOM_PERCENT}% headroom), have $(human_size "$avail")"
	fi

	echo "Disk space OK: need $(human_size "$need"), available $(human_size "$avail")"
}

warn_managedsave() {
	local save="/var/lib/libvirt/qemu/save/${DOMAIN}.img"

	if [[ -f "$save" ]]; then
		warn "managedsave state exists ($save) and was not backed up; remove with: virsh managedsave-remove $DOMAIN"
	fi
}

copy_file() {
	local src="$1"
	local dest="$2"

	[[ -f "$src" ]] || die "file not found: $src"
	mkdir -p "$(dirname "$dest")"
	cp -a "$src" "$dest"
	manifest_add "file: $dest <- $src ($(human_size_file "$dest"))"
}

copy_tree() {
	local src="$1"
	local dest="$2"

	[[ -e "$src" ]] || die "path not found: $src"
	mkdir -p "$(dirname "$dest")"
	cp -a "$src" "$dest"
	manifest_add "tree: $dest <- $src ($(du -sh "$dest" 2>/dev/null | awk '{print $1}'))"
}

copy_host_file() {
	local src="$1"
	local name="$2"
	local dest="$DEST/host-config/$name"

	if [[ -f "$src" ]]; then
		mkdir -p "$DEST/host-config"
		cp -a "$src" "$dest"
		manifest_add "host-config: $dest <- $src ($(human_size_file "$dest"))"
	else
		warn "host config not found, skipping: $src"
	fi
}

copy_host_config() {
	local lg_user="${SUDO_USER:-${USER:-root}}"
	local lg_ini="/home/$lg_user/.config/looking-glass/client.ini"

	copy_host_file /etc/libvirt/qemu.conf qemu.conf
	copy_host_file /etc/modprobe.d/vfio.conf vfio.conf
	copy_host_file /etc/modprobe.d/blacklist-nvidia.conf blacklist-nvidia.conf
	copy_host_file /etc/initramfs-tools/modules initramfs-modules

	if [[ -f /etc/default/grub ]]; then
		mkdir -p "$DEST/host-config"
		grep '^GRUB_CMDLINE' /etc/default/grub >"$DEST/host-config/grub-kernel-params.txt" || true
		if [[ -s "$DEST/host-config/grub-kernel-params.txt" ]]; then
			manifest_add "host-config: $DEST/host-config/grub-kernel-params.txt <- /etc/default/grub"
		else
			warn "no GRUB_CMDLINE entries in /etc/default/grub"
			rm -f "$DEST/host-config/grub-kernel-params.txt"
		fi
	fi

	copy_host_file "$lg_ini" looking-glass-client.ini
}

backup_nvram() {
	local xml="$1"
	local nvram_src

	nvram_src=$(nvram_path_from_xml "$xml")
	[[ -n "$nvram_src" ]] || {
		warn "no <nvram> in domain XML; skipping NVRAM"
		return 0
	}
	[[ -f "$nvram_src" ]] || die "NVRAM file not found: $nvram_src"

	mkdir -p "$DEST/nvram"
	copy_file "$nvram_src" "$DEST/nvram/$(basename "$nvram_src")"
}

backup_tpm() {
	local xml="$1"
	local swtpm_dir="/var/lib/libvirt/swtpm/${DOMAIN_UUID}"

	if ! xml_has_tpm "$xml"; then
		return 0
	fi

	[[ -d "$swtpm_dir" ]] || die "domain has TPM but swtpm state not found: $swtpm_dir"

	copy_tree "$swtpm_dir" "$DEST/tpm/${DOMAIN_UUID}"
}

backup_disks() {
	local path name target type device

	mkdir -p "$DEST/disks"
	DISK_COUNT=0

	while read -r type device target path; do
		[[ "$type" == Type* ]] && continue
		[[ -z "$target" ]] && continue
		[[ "$device" != disk ]] && continue
		[[ "$path" == "-" || -z "$path" ]] && continue
		[[ -f "$path" ]] || die "disk image not found: $path (target $target)"

		name=$(basename "$path")
		echo "Copying disk $target: $path -> $DEST/disks/$name"
		cp -a --reflink=auto "$path" "$DEST/disks/$name"
		DISK_COUNT=$((DISK_COUNT + 1))
		manifest_add "disk: $DEST/disks/$name <- $path (target $target, type $type, $(human_size_file "$DEST/disks/$name"))"
	done < <(virsh domblklist "$DOMAIN" --details)

	[[ "$DISK_COUNT" -gt 0 ]] || die "no disk images copied for $DOMAIN"
}

write_manifest() {
	local manifest="$DEST/manifest.txt"
	local line

	{
		echo "domain: $DOMAIN"
		echo "domain-uuid: $DOMAIN_UUID"
		echo "timestamp: $TIMESTAMP"
		echo "destination: $DEST"
		echo "host-config: $([[ $HOST_CONFIG -eq 1 ]] && echo yes || echo no)"
		echo
		echo "restore-notes:"
		echo "  - Copy disks, nvram, and tpm back to original paths (see artifacts below)"
		echo "  - chown restored files to match qemu.conf user/group (root:root on this host)"
		echo "  - virsh define ${DOMAIN}.xml && virsh start $DOMAIN"
		echo "  - Guest Looking Glass host ini is NOT in this backup; copy manually from:"
		echo "    C:\\Program Files\\Looking Glass (host)\\looking-glass-host.ini"
		echo "  - PCI passthrough and IVSHMEM XML entries are host-specific on migration"
		echo
		echo "libvirt version:"
		virsh version | sed 's/^/  /'
		echo
		echo "artifacts:"
		for line in "${MANIFEST_LINES[@]}"; do
			echo "  $line"
		done
	} >"$manifest"

	echo "Wrote $manifest"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	-o)
		[[ $# -ge 2 ]] || die "missing argument for -o"
		DEST_BASE="$2"
		shift 2
		;;
	--no-host-config)
		HOST_CONFIG=0
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	-*)
		die "unknown option: $1"
		;;
	*)
		[[ -z "$DOMAIN" ]] || die "unexpected extra argument: $1"
		DOMAIN="$1"
		shift
		;;
	esac
done

[[ -n "$DOMAIN" ]] || {
	usage
	exit 1
}

require_root
require_commands

virsh dominfo "$DOMAIN" >/dev/null 2>&1 || die "libvirt domain not found: $DOMAIN"

state=$(virsh domstate "$DOMAIN" 2>/dev/null || true)
if [[ "$state" != "shut off" ]]; then
	die "domain $DOMAIN is '$state' (must be shut off). Run: virsh shutdown $DOMAIN"
fi

DOMAIN_UUID=$(domain_uuid)
[[ -n "$DOMAIN_UUID" ]] || die "could not read UUID for $DOMAIN"

warn_managedsave
collect_disk_paths
check_disk_space

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
DEST="${DEST_BASE%/}/${DOMAIN}/${TIMESTAMP}"

mkdir -p "$DEST"
[[ -d "$DEST" ]] || die "destination not writable: $DEST"

echo "Backing up $DOMAIN (UUID $DOMAIN_UUID) -> $DEST"

XML="$DEST/${DOMAIN}.xml"
virsh dumpxml --inactive "$DOMAIN" >"$XML"
manifest_add "xml: $XML"

backup_nvram "$XML"
backup_tpm "$XML"
backup_disks

if ((HOST_CONFIG)); then
	echo "Copying host-side config..."
	copy_host_config
fi

write_manifest

echo
echo "Backup completed: $(realpath "$DEST")"
