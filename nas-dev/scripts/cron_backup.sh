#!/bin/bash

# Backup script with integrated logging and emailing
# Note: Every hour backrest runs back: copies to /pool/docker_archive

LOG_FILE="/tmp/backup_complete_$(date +%Y%m%d_%H%M%S).log"
MAIL_TO="root.nas-dev@bitrealm.dev"
EXIT_CODE=0

# Initialize log file, i.e. clear it
> "$LOG_FILE"

run_and_log() {
    local description="$1"
    local command="$2"

    echo "=== $description ===" | tee -a "$LOG_FILE"
    eval "$command" 2>&1 | tee -a "$LOG_FILE"
    local cmd_exit=${PIPESTATUS[0]}
    echo "" | tee -a "$LOG_FILE"

    if [[ $cmd_exit -ne 0 ]]; then
        echo "ERROR: $description failed with exit code $cmd_exit" | tee -a "$LOG_FILE"
        EXIT_CODE=1
    fi

    return $cmd_exit
}

send_email() {
    local subject="$1"
    local status="$2"

    if [[ $status -eq 0 ]]; then
        echo "Backup completed successfully. See attached log." |
            mailx -a "$LOG_FILE" -s "$subject - SUCCESS" "$MAIL_TO"
        rm -f "$LOG_FILE"
    else
        echo -e "Backup failed. See attached log for details." |
            mailx -a "$LOG_FILE" -s "$subject - FAILED" "$MAIL_TO"
    fi
}

######################################################################################################

if pgrep -x "rclone-filen" > /dev/null; then
    echo "rclone-filen is already running, exiting." | tee -a "$LOG_FILE"
    send_email "Backup Duplicate Check" 1
    exit 0
fi

echo "Starting backup" | tee "$LOG_FILE"
echo "Started at: $(date)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

run_and_log "Restore koofr-remote:/docs/ -> /pool/docs/" \
    "/usr/local/bin/rclone-filen -P copy koofr-remote:/docs/ /pool/docs/"

run_and_log "SnapRAID status" "snapraid status"
if [[ $EXIT_CODE -ne 0 ]]; then
    echo "SnapRAID status failed. Something is wrong." | tee -a "$LOG_FILE"
    send_email "cron backup: snapraid status returned an error, skipping cron backup" "$EXIT_CODE"
    exit $EXIT_CODE
fi

run_and_log "SnapRAID sync" "snapraid sync"
# If snapraid sync failed, stop here and email
if [[ $EXIT_CODE -ne 0 ]]; then
    echo "SnapRAID sync failed. Skipping all rclone copies." | tee -a "$LOG_FILE"
    send_email "cron backup: snapraid sync failed, skipping cron backup" "$EXIT_CODE"
    exit $EXIT_CODE
fi

run_and_log "Copy /pool/archive -> koofr-remote:/archive/" \
    "/usr/local/bin/rclone-filen -P copy /pool/archive/ koofr-remote:/archive/"

if pgrep -x "restic" > /dev/null; then
    echo "Restic is running (check Backrest), skipping /pool/docker_archive remote backups." | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
else
    run_and_log "Copy /pool/docker_archive -> filen-remote:/docker_archive/" \
        "/usr/local/bin/rclone-filen -P copy /pool/docker_archive/ filen-remote:/docker_archive/"

    run_and_log "Copy /pool/docker_archive -> koofr-remote:/docker_archive/" \
        "/usr/local/bin/rclone-filen -P copy /pool/docker_archive/ koofr-remote:/docker_archive/"
fi

run_and_log "Copy /pool/docs/ -> filen-remote:/docs/" \
    "/usr/local/bin/rclone-filen -P copy /pool/docs/ filen-remote:/docs/"

run_and_log "Copy /pool/archive/ -> filen-remote:/archive/" \
    "/usr/local/bin/rclone-filen -P copy /pool/archive/ filen-remote:/archive/"

run_and_log "SnapRAID scrub" \
    "snapraid scrub"

echo "Backup completed at: $(date)" | tee -a "$LOG_FILE"

send_email "cron backup: status" "$EXIT_CODE"

exit $EXIT_CODE
