#!/bin/bash
set -o pipefail

# Daily SnapRAID maintenance with integrated logging and emailing.
# Koofr desktop app handles /pool 2-way sync; Filen jobs run weekly via cron_filen_weekly.sh.

#######################################
# CONFIG
#######################################

BACKUP_NAME="SnapRAID nightly"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/snapraid_${TIMESTAMP}.log"
HTML_LOG_FILE="${LOG_FILE%.log}.html"
MAIL_TO="nas-dev@bitrealm.dev"

EXIT_CODE=0

SNAPRAID="/usr/bin/snapraid"
MAILX="/usr/bin/mailx"
TXT2HTML="/usr/bin/txt2html"

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
        echo "SnapRAID nightly completed successfully. See attached log." |
            "$MAILX" -A "$HTML_LOG_FILE" -s "$subject - SUCCESS" "$MAIL_TO"
        rm -f "$LOG_FILE" "$HTML_LOG_FILE"
    else
        echo "SnapRAID nightly failed. See attached log for details." |
            "$MAILX" -A "$HTML_LOG_FILE" -s "$subject - FAILED" "$MAIL_TO"
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

> "$LOG_FILE"

echo "Log file: $LOG_FILE"
log "Starting SnapRAID nightly"
log "Started at: $(date)"
log ""

run_and_log "SnapRAID status" "$SNAPRAID" status
if [[ $EXIT_CODE -ne 0 ]]; then
    fail_and_exit "snapraid status returned an error"
fi

run_and_log "SnapRAID sync" "$SNAPRAID" sync
if [[ $EXIT_CODE -ne 0 ]]; then
    fail_and_exit "snapraid sync failed"
fi

log "SnapRAID nightly completed at: $(date)"

send_email "$BACKUP_NAME: status" "$EXIT_CODE"

exit "$EXIT_CODE"
