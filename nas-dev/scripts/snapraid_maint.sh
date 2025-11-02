#!/usr/bin/env bash
set -euo pipefail

FORCE_EMAIL="${1-}" # pass --force-email to always send a report
LOCKFILE="/run/lock/snapraid/maint.lock"
LOG_DIR="/var/log/snapraid"
mkdir -p "$LOG_DIR"

DATE_SUFFIX="$(/bin/date +%F_%H-%M-%S)"
STATUS_LOG="$LOG_DIR/status_$DATE_SUFFIX.log"
SCRUB_LOG="$LOG_DIR/scrub_$DATE_SUFFIX.log"

MAIL_TO="snapraid@bitrealm.dev"
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# single-run lock
exec 9>"$LOCKFILE"
flock -n 9 || exit 0

# 1) Status
/usr/bin/nice -n 10 /usr/bin/ionice -c2 -n7 /usr/bin/snapraid status >"$STATUS_LOG" 2>&1 || true
STATUS_OK=0
if ! /bin/grep -q "No error detected." "$STATUS_LOG"; then
	STATUS_OK=1
fi

# 2) Scrub (light)
SCRUB_OK=0
if [[ "$STATUS_OK" -eq 0 ]]; then
	/usr/bin/nice -n 10 /usr/bin/ionice -c2 -n7 /usr/bin/snapraid scrub -p 5 -o 7 >"$SCRUB_LOG" 2>&1 || SCRUB_OK=$?
fi

# 3) Email policy
SEND_EMAIL=0
SUBJECT="SnapRAID report ($(hostname)) $DATE_SUFFIX"
BODY_OK="SnapRAID maintenance completed successfully."
BODY_FAIL="SnapRAID reported issues. See logs."

if [[ "$FORCE_EMAIL" == "--force-email" ]]; then
	SEND_EMAIL=1
elif [[ "$STATUS_OK" -ne 0 || "$SCRUB_OK" -ne 0 ]]; then
	SEND_EMAIL=1
fi

if [[ "$SEND_EMAIL" -eq 1 ]]; then
	# attach whichever logs exist
	ATTACHES=()
	[[ -s "$STATUS_LOG" ]] && ATTACHES+=(-A "$STATUS_LOG")
	[[ -s "$SCRUB_LOG" ]] && ATTACHES+=(-A "$SCRUB_LOG")

	SUBJECT_PREFIX="OK"
	BODY="$BODY_OK"
	if [[ "$STATUS_OK" -ne 0 || "$SCRUB_OK" -ne 0 ]]; then
		SUBJECT_PREFIX="FAIL"
		BODY="$BODY_FAIL (status_ok=$STATUS_OK scrub_ok=$SCRUB_OK)"
	fi

	echo "$BODY" | /usr/bin/mailx "${ATTACHES[@]}" -s "[$SUBJECT_PREFIX] $SUBJECT" "$MAIL_TO"
fi

# optional: prune old logs (>30 days)
find "$LOG_DIR" -type f -mtime +30 -delete || true
