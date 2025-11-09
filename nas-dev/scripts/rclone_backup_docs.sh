#!/bin/bash

echo "Starting rclone copy..."

echo "rclone copy koofr-remote:/docs/ -> /pool/docs/"
/usr/local/bin/rclone-filen copy koofr-remote:/docs/ /pool/docs/

echo "rclone copy /pool/archive/ -> koofr-remote:/archive/"
/usr/local/bin/rclone-filen copy /pool/archive/ koofr-remote:/archive/

echo "Done"
