#!/bin/bash
# smart_report_scsi.sh
# Collect SMART health from SCSI/SAS drives and email results.

LOG_FILE="/tmp/smart_status.log"
DATE_SUFFIX=$(date +%F)
MAIL_TO="snapraid@bitrealm.dev"

> "$LOG_FILE"

HOST=$(hostname -s)
DATE=$(date)
TMPFILE=$(mktemp)

log() {
    echo "[$(date +'%F %T')] $*" | tee -a "$LOG_FILE"
}

log "==================================================="
log "SMART Health Report for $HOST - $DATE"
log "==================================================="

OVERALL_OK=1
mapfile -t DEVICES < <(sudo smartctl --scan | grep scsi)

if [[ ${#DEVICES[@]} -eq 0 ]]; then
    log "No SCSI devices found. Exiting."
    exit 1
fi

log "Devices found:"
printf '%s\n' "${DEVICES[@]}" | tee -a "$LOG_FILE"
log ""

for entry in "${DEVICES[@]}"; do
    dev=$(echo "$entry" | awk '{print $1}')
    dtype=$(echo "$entry" | awk '{print $3}')

    log "Checking device: $dev (type=$dtype)..."

    # Dump summary + errors into log
    sudo smartctl -A -l error -d "$dtype" "$dev" >> "$LOG_FILE" 2>&1

    # Extract key metrics
    DEFECTS=$(sudo smartctl -A -d "$dtype" "$dev" 2>/dev/null | awk -F: '/grown defect list/ {gsub(/ /,"",$2); print $2}')
    NONMED=$(sudo smartctl -A -d "$dtype" "$dev" 2>/dev/null | awk -F: '/Non-medium error count/ {gsub(/ /,"",$2); print $2}')
    READ_ERR=$(sudo smartctl -l error -d "$dtype" "$dev" 2>/dev/null | awk '/Read:/ {print $2}' | tail -1)
    WRITE_ERR=$(sudo smartctl -l error -d "$dtype" "$dev" 2>/dev/null | awk '/Write:/ {print $2}' | tail -1)
    VERIFY_ERR=$(sudo smartctl -l error -d "$dtype" "$dev" 2>/dev/null | awk '/Verify:/ {print $2}' | tail -1)

    # Evaluate
    ALERTS=0
    [[ "$DEFECTS" =~ ^[0-9]+$ && "$DEFECTS" -gt 0 ]] && { log "ALERT: $dev has $DEFECTS grown defects"; ALERTS=1; }
    [[ "$NONMED" =~ ^[0-9]+$ && "$NONMED" -gt 0 ]] && { log "ALERT: $dev reports $NONMED non-medium errors"; ALERTS=1; }
    [[ "$READ_ERR" =~ ^[0-9]+$ && "$READ_ERR" -gt 0 ]] && { log "ALERT: $dev has $READ_ERR read errors"; ALERTS=1; }
    [[ "$WRITE_ERR" =~ ^[0-9]+$ && "$WRITE_ERR" -gt 0 ]] && { log "ALERT: $dev has $WRITE_ERR write errors"; ALERTS=1; }
    [[ "$VERIFY_ERR" =~ ^[0-9]+$ && "$VERIFY_ERR" -gt 0 ]] && { log "ALERT: $dev has $VERIFY_ERR verify errors"; ALERTS=1; }

    if [[ $ALERTS -eq 0 ]]; then
        log "Result: $dev PASSED (no defects or errors)"
    else
        OVERALL_OK=0
    fi

    log "---------------------------------------------------"
done

rm -f "$TMPFILE"

log "==================================================="

# Email results
if [[ $OVERALL_OK -eq 1 ]]; then
    log "All drives look healthy (no defects or errors)."
    if echo "SMART check passed on all drives. See attached log." \
        | mailx -A "$LOG_FILE" -s "SMART Report OK - $HOST" "$MAIL_TO"; then
        log "Email sent successfully (OK report)."
        rm -f "$LOG_FILE"
    else
        log "ERROR: Failed to send email (OK report). Log retained."
    fi
else
    log "One or more drives reported SMART errors!"
    if echo "SMART detected problems on one or more drives! See log." \
        | mailx -A "$LOG_FILE" -s "SMART ALERT - $HOST" "$MAIL_TO"; then
        log "Email sent successfully (ALERT report)."
    else
        log "ERROR: Failed to send email (ALERT report)."
    fi
    mv "$LOG_FILE" "${LOG_FILE%.log}-$DATE_SUFFIX.log"
    log "Log saved to ${LOG_FILE%.log}-$DATE_SUFFIX.log"
fi
