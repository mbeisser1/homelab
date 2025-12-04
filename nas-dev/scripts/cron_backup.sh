#!/bin/bash

# Every hour backrest runs back: copies to /pool/docker_archive

if pgrep "rclone-filen" > /dev/null; then
    echo "Is a backup still running? rclone-filen is already running, exiting."
    exit 0
fi

echo "Starting backup"

echo "rclone copy koofr-remote:/docs/ -> /pool/docs/"
/usr/local/bin/rclone-filen -P copy koofr-remote:/docs/ /pool/docs/

echo "Starting snapraid sync"
/usr/local/bin/snapraid_sync.sh

echo "rclone copy /pool/archive/ -> koofr-remote:/archive/"
/usr/local/bin/rclone-filen -P copy /pool/archive/ koofr-remote:/archive/

if pgrep "restic" > /dev/null; then
    echo "Is Backrest copying files because restic is running. Skipping /pool/docker_archive -> remote backups"
else
    echo "rclone copy /pool/docker_archive/ -> filen-remote:/docker_archive/"
    /usr/local/bin/rclone-filen -P copy /pool/docker_archive/ filen-remote:/docker_archive/

    echo "rclone copy /pool/docker_archive/ -> koofr-remote:/docker_archive/"
    /usr/local/bin/rclone-filen -P copy /pool/docker_archive/ koofr-remote:/docker_archive/
fi

# ------ Filen -----
echo "rclone copy /pool/docs/ -> filen-remote:/docs/"
/usr/local/bin/rclone-filen -P copy /pool/docs/ filen-remote:/docs/

echo "rclone copy /pool/archive/ -> filen-remote:/archive/"
/usr/local/bin/rclone-filen -P copy /pool/archive/ filen-remote:/archive/
# ------------------

echo "Starting snapraid scrub"
/usr/local/bin/snapraid_scrub.sh

echo "Backup done"

