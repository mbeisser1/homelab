#!/bin/bash

LOG_FILE="/tmp/snapraid_status.log"
SCRUB_LOG="/tmp/snapraid_scrub.log"
DATE_SUFFIX=$(date +%F)  # YYYY-MM-DD

MAIL_TO="snapraid@bitrealm.dev"
MAIL_SUBJECT=""
MAIL_MSG=""

# Run snapraid status and capture output
snapraid status > "$LOG_FILE" 2>&1
LASTLINE=$(tail -n 1 "$LOG_FILE")

if [ "$LASTLINE" == "No error detected." ]; then
    # Run scrub
    snapraid -p 5 scrub > "$SCRUB_LOG" 2>&1
    rtnstatus=$?

    if [[ $rtnstatus -eq 0 ]]; then
        MAIL_SUBJECT="SnapRAID Scrub Success"
        MAIL_MSG="Weekly SnapRAID scrub completed successfully. See log for details."
        mailx -A "$SCRUB_LOG" -s "$MAIL_SUBJECT" "$MAIL_TO" <<< "$MAIL_MSG"
        rm -f "$SCRUB_LOG"
    else
        MAIL_SUBJECT="SnapRAID Scrub FAILED"
        MAIL_MSG="SnapRAID scrub failed with exit code [$rtnstatus]. See log for details."
        mailx -A "$SCRUB_LOG" -s "$MAIL_SUBJECT" "$MAIL_TO" <<< "$MAIL_MSG"
        mv "$SCRUB_LOG" "${SCRUB_LOG%.log}-$DATE_SUFFIX.log"
    fi

    rm -f "$LOG_FILE"  # Status was clean, so we delete it
else
    # Snapraid status found errors
    MAIL_SUBJECT="SnapRAID Status Check FAILED"
    MAIL_MSG="SnapRAID status reported errors. Scrub skipped. See log for details."
    mailx -A "$LOG_FILE" -s "$MAIL_SUBJECT" "$MAIL_TO" <<< "$MAIL_MSG"
    mv "$LOG_FILE" "${LOG_FILE%.log}-$DATE_SUFFIX.log"
fi
