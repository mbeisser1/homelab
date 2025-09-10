#!/bin/bash

LOG_FILE="/tmp/snapraid_status.log"
DATE_SUFFIX=$(date +%F)

MAIL_TO="snapraid@bitrealm.dev"

# Run status and capture output
snapraid status >"$LOG_FILE" 2>&1
LASTLINE=$(tail -n 1 "$LOG_FILE")

if [ "$LASTLINE" == "No error detected." ]; then
	# Run sync and capture its result
	SYNC_RESULT=$(snapraid sync 2>&1)
	SYNC_EXIT=$?

	if [[ $SYNC_EXIT -eq 0 ]]; then
		echo "Daily SnapRAID sync success. No errors found. See log." |
			mailx -A "$LOG_FILE" -s "SnapRAID Sync Success" "$MAIL_TO"
		rm -f "$LOG_FILE"
	else
		echo -e "SnapRAID sync returned non-zero exit code ($SYNC_EXIT).\n\nOutput:\n$SYNC_RESULT" |
			mailx -A "$LOG_FILE" -s "SnapRAID Sync Error (Code $SYNC_EXIT)" "$MAIL_TO"
		mv "$LOG_FILE" "${LOG_FILE%.log}-$DATE_SUFFIX.log"
	fi
else
	echo "SnapRAID status check failed. Sync skipped. See log." |
		mailx -A "$LOG_FILE" -s "SnapRAID Status Error" "$MAIL_TO"
	mv "$LOG_FILE" "${LOG_FILE%.log}-$DATE_SUFFIX.log"
fi
