#!/bin/bash
# smart_report.sh
# Collect SMART health for all drives and email results, with detailed logging.

LOG_FILE="/tmp/smart_status.log"
DATE_SUFFIX=$(date +%F)
MAIL_TO="snapraid@bitrealm.dev"

>"$LOG_FILE"

HOST=$(hostname -s)
DATE=$(date)
TMPFILE=$(mktemp)

# log() writes to both stdout and the log file
log() {
	echo "[$(date +'%F %T')] $*" | tee -a "$LOG_FILE"
}

log "==================================================="
log "SMART Health Report for $HOST - $DATE"
log "==================================================="

OVERALL_OK=1
mapfile -t DEVICES < <(sudo smartctl --scan)

if [[ ${#DEVICES[@]} -eq 0 ]]; then
	log "No devices found by smartctl --scan. Exiting."
	exit 1
fi

log "Devices found:"
printf '%s\n' "${DEVICES[@]}" | tee -a "$LOG_FILE"
log ""

for entry in "${DEVICES[@]}"; do
	dev=$(echo "$entry" | awk '{print $1}')
	dtype=$(echo "$entry" | awk '{print $3}')

	log "Checking device: $dev (type=$dtype)..."

	# Dump full attributes into the log
	if ! sudo smartctl -A -H -d "$dtype" "$dev" >>"$LOG_FILE" 2>&1; then
		log "ERROR: smartctl full report failed for $dev"
		OVERALL_OK=0
		continue
	fi

	# Run health-only check and capture exit code
	sudo smartctl -H -d "$dtype" "$dev" >"$TMPFILE" 2>&1
	HEALTH_EXIT=$?
	HEALTH_LINE=$(grep "SMART overall-health" "$TMPFILE" || true)

	if [[ $HEALTH_EXIT -eq 0 ]]; then
		log "Result: $dev PASSED"
	elif [[ $HEALTH_EXIT -eq 1 ]]; then
		log "Result: $dev FAILED"
		[[ -n "$HEALTH_LINE" ]] && log "Details: $HEALTH_LINE"
		OVERALL_OK=0
	elif [[ $HEALTH_EXIT -eq 2 ]]; then
		log "Result: $dev UNKNOWN (SMART not supported or disabled)"
		[[ -n "$HEALTH_LINE" ]] && log "Details: $HEALTH_LINE"
	else
		log "Result: $dev ERROR (smartctl exit $HEALTH_EXIT)"
		OVERALL_OK=0
	fi

	log "---------------------------------------------------"
done

rm -f "$TMPFILE"

log "==================================================="

# Email results
if [[ $OVERALL_OK -eq 1 ]]; then
	log "All drives passed SMART health."
	if echo "SMART check passed on all drives. See attached log." |
		mailx -A "$LOG_FILE" -s "SMART Report OK - $HOST" "$MAIL_TO"; then
		log "Email sent successfully (OK report)."
		rm -f "$LOG_FILE"
	else
		log "ERROR: Failed to send email (OK report). Log retained."
	fi
else
	log "One or more drives reported SMART errors!"
	if echo "SMART detected problems on one or more drives! See log." |
		mailx -A "$LOG_FILE" -s "SMART ALERT - $HOST" "$MAIL_TO"; then
		log "Email sent successfully (ALERT report)."
	else
		log "ERROR: Failed to send email (ALERT report)."
	fi
	mv "$LOG_FILE" "${LOG_FILE%.log}-$DATE_SUFFIX.log"
	log "Log saved to ${LOG_FILE%.log}-$DATE_SUFFIX.log"
fi
