#!/bin/bash
set -o pipefail

# Backup script with integrated logging and emailing
# Note: Every hour backrest runs back: copies to /pool/docker_archive

#######################################
# CONFIG
#######################################

BACKUP_NAME="cron backup"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/backup_complete_${TIMESTAMP}.log"
HTML_LOG_FILE="${LOG_FILE%.log}.html"
MAIL_TO="root.nas-dev@bitrealm.dev"

EXIT_CODE=0

# Commands
RCLONE="/usr/local/bin/rclone-filen"
SNAPRAID="/usr/bin/snapraid"

# Rclone settings
RCLONE_LOG_LEVEL="INFO"   # DEBUG|INFO|NOTICE|ERROR etc.【2】【3】
#RCLONE_COMMON_OPTS=(-P "--log-level=${RCLONE_LOG_LEVEL}")
RCLONE_COMMON_OPTS=("--log-level=${RCLONE_LOG_LEVEL}")

# Remotes
REMOTE_KOOFR="koofr-remote"
REMOTE_FILEN="filen-remote"

#######################################
# UTILS
#######################################

# Simple logger
log() {
    echo "$@" | tee -a "$LOG_FILE"
}

# Run a command with description and log everything
run_and_log() {
    local description="$1"
    shift

    log "=== ${description} ==="
    # "$@" is the command + args
    "$@" 2>&1 | tee -a "$LOG_FILE"
    local cmd_exit=${PIPESTATUS[0]}
    log ""

    if [[ $cmd_exit -ne 0 ]]; then
        log "ERROR: ${description} failed with exit code ${cmd_exit}"
        EXIT_CODE=1
    fi

    return "$cmd_exit"
}

# Wrapper around rclone copy with logging options
rclone_copy() {
    local description="$1"
    local src="$2"
    local dst="$3"

    run_and_log "$description" \
        "$RCLONE" "${RCLONE_COMMON_OPTS[@]}" copy "$src" "$dst"
}

send_email() {
    local subject="$1"
    local status="$2"

    txt2html "$LOG_FILE" > "$HTML_LOG_FILE"

    if [[ $status -eq 0 ]]; then
        echo "Backup completed successfully. See attached log." |
            mailx -a "$HTML_LOG_FILE" -s "$subject - SUCCESS" "$MAIL_TO"
        rm -f "$LOG_FILE" "$HTML_LOG_FILE"
    else
        echo "Backup failed. See attached log for details." |
            mailx -a "$HTML_LOG_FILE" -s "$subject - FAILED" "$MAIL_TO"
    fi
}

fail_and_exit() {
    local msg="$1"
    log "$msg"
    send_email "$BACKUP_NAME: $msg" 1
    exit 1
}

#######################################
# MAIN
#######################################

# Initialize log file, i.e. clear it
> "$LOG_FILE"

if pgrep -x "rclone-filen" > /dev/null; then
    log "rclone-filen is already running, exiting."
    send_email "Backup already in progress" 1
    exit 0
fi

echo "Log file: $LOG_FILE"
log "Starting backup"
log "Started at: $(date)"
log ""

# Restore docs from koofr
rclone_copy \
    "Restore ${REMOTE_KOOFR}:/docs/ -> /pool/docs/" \
    "${REMOTE_KOOFR}:/docs/" \
    "/pool/docs/"

# SnapRAID status
run_and_log "SnapRAID status" "$SNAPRAID" status
if [[ $EXIT_CODE -ne 0 ]]; then
    fail_and_exit "snapraid status returned an error, skipping cron backup"
fi

# SnapRAID sync
run_and_log "SnapRAID sync" "$SNAPRAID" sync
if [[ $EXIT_CODE -ne 0 ]]; then
    fail_and_exit "snapraid sync failed, skipping all rclone copies"
fi

# Archive -> koofr
rclone_copy \
    "Copy /pool/archive -> ${REMOTE_KOOFR}:/archive/" \
    "/pool/archive/" \
    "${REMOTE_KOOFR}:/archive/"

# Docker archive copies (skipped if restic running)
if pgrep -x "restic" > /dev/null; then
    log "Restic is running (check Backrest), skipping /pool/docker_archive remote backups."
    log ""
else
    rclone_copy \
        "Copy /pool/docker_archive -> ${REMOTE_FILEN}:/docker_archive/" \
        "/pool/docker_archive/" \
        "${REMOTE_FILEN}:/docker_archive/"

    rclone_copy \
        "Copy /pool/docker_archive -> ${REMOTE_KOOFR}:/docker_archive/" \
        "/pool/docker_archive/" \
        "${REMOTE_KOOFR}:/docker_archive/"
fi

# Docs -> filen
rclone_copy \
    "Copy /pool/docs/ -> ${REMOTE_FILEN}:/docs/" \
    "/pool/docs/" \
    "${REMOTE_FILEN}:/docs/"

# Archive -> filen
rclone_copy \
    "Copy /pool/archive/ -> ${REMOTE_FILEN}:/archive/" \
    "/pool/archive/" \
    "${REMOTE_FILEN}:/archive/"

# SnapRAID scrub
run_and_log "SnapRAID scrub" "$SNAPRAID" scrub

log "Backup completed at: $(date)"

send_email "$BACKUP_NAME: status" "$EXIT_CODE"

exit "$EXIT_CODE"
