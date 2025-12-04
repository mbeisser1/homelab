#!/bin/bash

# every hour backrest runs back: copies to /pool/archive/docker/volumes

echo "Starting backup"

echo "rclone copy koofr-remote:/docs/ -> /pool/docs/"
/usr/local/bin/rclone-filen -P copy koofr-remote:/docs/ /pool/docs/

echo "Starting snapraid sync"
/usr/local/bin/snapraid_sync.sh

echo "rclone copy /pool/archive/ -> koofr-remote:/archive/"
/usr/local/bin/rclone-filen -P copy /pool/archive/ koofr-remote:/archive/

echo "rclone copy /pool/docker_archive/ -> koofr-remote:/docker_archive/"
/usr/local/bin/rclone-filen -P copy /pool/docker_archive/ koofr-remote:/docker_archive/

# ------ Filen -----
echo "rclone copy /pool/docs/ -> filen-remote:/docs/"
/usr/local/bin/rclone-filen -P copy /pool/docs/ filen-remote:/docs/

echo "rclone copy /pool/archive/ -> filen-remote:/archive/"
/usr/local/bin/rclone-filen -P copy /pool/archive/ filen-remote:/archive/

echo "rclone copy /pool/docker_archive/ -> filen-remote:/docker_archive/"
/usr/local/bin/rclone-filen -P copy /pool/docker_archive/ filen-remote:/docker_archive/
# ------------------

echo "Starting snapraid scrub"
/usr/local/bin/snapraid_scrub.sh

echo "Backup done"

