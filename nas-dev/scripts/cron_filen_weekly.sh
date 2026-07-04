#!/bin/bash
set -o pipefail

# Weekly Filen backup: archive dry-run report + dated Obsidian vault copy.
# Koofr desktop app handles /pool 2-way sync; this script only targets filen-remote.

#######################################
# CONFIG
#######################################

BACKUP_NAME="Filen weekly backup"
LOCK_FILE="/var/lock/cron_filen_weekly.lock"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/filen_weekly_${TIMESTAMP}.log"
HTML_LOG_FILE="${LOG_FILE%.log}.html"
MAIL_TO="nas-dev@bitrealm.dev"

EXIT_CODE=0

RCLONE="/usr/bin/rclone"
REMOTE_FILEN="filen-remote"
DOCS_DEST="${REMOTE_FILEN}:/docs-$(date +%Y-%m-%d)-obsidian-vault"
MAILX="/usr/bin/mailx"

export RCLONE_DISABLE_HTTP2=true
export RCLONE_TRANSFERS=16
RCLONE_LOG_LEVEL="INFO"
RCLONE_COMMON_OPTS=("--log-level=${RCLONE_LOG_LEVEL}")

#######################################
# UTILS
#######################################

log() {
    echo "$@" | tee -a "$LOG_FILE"
}

run_and_log() {
    local description="$1"
    shift

    log "=== ${description} ==="
    "$@" 2>&1 | tee -a "$LOG_FILE"
    local cmd_exit=${PIPESTATUS[0]}
    log ""

    if [[ $cmd_exit -ne 0 ]]; then
        log "ERROR: ${description} failed with exit code ${cmd_exit}"
        EXIT_CODE=1
    fi

    return "$cmd_exit"
}

send_email() {
    local subject="$1"
    local status="$2"

    /usr/bin/txt2html "$LOG_FILE" > "$HTML_LOG_FILE"

    if [[ $status -eq 0 ]]; then
        echo "Filen weekly backup completed successfully. See attached log." |
            "$MAILX" -A "$HTML_LOG_FILE" -s "$subject - SUCCESS" "$MAIL_TO"
        rm -f "$LOG_FILE" "$HTML_LOG_FILE"
    else
        echo "Filen weekly backup failed. See attached log for details." |
            "$MAILX" -A "$HTML_LOG_FILE" -s "$subject - FAILED" "$MAIL_TO"
    fi
}

#######################################
# MAIN
#######################################

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "cron_filen_weekly.sh is already running, exiting."
    exit 0
fi

> "$LOG_FILE"

echo "Log file: $LOG_FILE"
log "Starting Filen weekly backup"
log "Started at: $(date)"
log "Docs destination: ${DOCS_DEST}"
log ""

run_and_log \
    "Archive dry-run: /pool/archive/ -> ${REMOTE_FILEN}:/archive/" \
    "$RCLONE" "${RCLONE_COMMON_OPTS[@]}" sync --dry-run \
    "/pool/archive/" "${REMOTE_FILEN}:/archive/"

run_and_log \
    "Copy /pool/docs/ -> ${DOCS_DEST}" \
    "$RCLONE" "${RCLONE_COMMON_OPTS[@]}" copy \
    "/pool/docs/" "$DOCS_DEST"

log "Filen weekly backup completed at: $(date)"

send_email "$BACKUP_NAME: status" "$EXIT_CODE"

exit "$EXIT_CODE"
