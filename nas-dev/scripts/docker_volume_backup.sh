#!/bin/bash
# Create timestamp in format: YYYY-MM-DD_HH-MM
timestamp=$(date +"%Y-%m-%d_%I-%M")

# Set destination path - default to current directory if not provided
DEST_PATH="${1:-.}"

# Check if docker_compose_manager.sh is in PATH
if ! DOCKER_MANAGER_SCRIPT=$(command -v docker_compose_manager.sh); then
    echo "ERROR: docker_compose_manager.sh not found in PATH" 
    echo "Please add the directory containing docker_compose_manager.sh to your PATH" 
    exit 1
fi

# Ensure destination directory exists
if [[ ! -d "$DEST_PATH" ]]; then
    echo "ERROR: Destination directory does not exist: $DEST_PATH" 
    exit 1
fi

# Stop all Docker containers first
echo "Stopping all Docker containers..."
if ! "$DOCKER_MANAGER_SCRIPT" stop; then
    echo "ERROR: Failed to stop Docker containers. Aborting backup." 
    exit 1
fi

# Proceed with backups
volumes=(
  "dockge_dockge_data"
  "immich_immich-db"
  "networking_nginx-proxy-manager_data"
  "networking_nginx-proxy-manager_letsencrypt"
  "xwiki_mariadb-data"
  "xwiki_xwiki-data"
)

backup_failed=0
for volume in "${volumes[@]}"; do
  echo "Backing up $volume to $DEST_PATH..."
  if ! vackup export "$volume" "${DEST_PATH}/${volume}_${timestamp}.tar.gz"; then
    echo "WARNING: Failed to backup $volume" 
    ((backup_failed++))
  fi
done

# Start all Docker containers again
if ! "$DOCKER_MANAGER_SCRIPT" start; then
    exit 1
fi

# Report final status
if [[ $backup_failed -eq 0 ]]; then
    echo "All backups completed successfully! Backups saved to: $(realpath "$DEST_PATH")"
    exit 0
else
    echo "WARNING: $backup_failed volume(s) failed to backup. Backups saved to: $(realpath "$DEST_PATH")"
    exit 1
fi