#!/bin/bash
# smart_report.sh
# Collect SMART health for all drives, print results, and email on failure.

LOG_FILE="/tmp/smart_status.log"
DATE_SUFFIX=$(date +%F)
MAIL_TO="snapraid@bitrealm.dev"

>"$LOG_FILE"

HOST=$(hostname -s)
DATE=$(date)
TMPFILE=$(mktemp)

log() {
	echo "[$(date +'%F %T')] $*" | tee -a "$LOG_FILE"
}

log_plain() {
	printf '%s\n' "$@" | tee -a "$LOG_FILE"
}

# Strip smartctl banners; keep only SMART payload lines
smart_data_lines() {
	grep -Eiv '^(smartctl |Copyright |$|\[GLTSD|=== START OF INFORMATION|Device Model|Serial Number|LU WWN|Add\. Product|User Capacity|Sector Sizes|Rotation Rate|Form Factor|Device is:|ATA Version|SATA Version|Local Time|SMART support|AAM feature|APM feature|Rd look-ahead|Write cache|DSN feature|ATA Security|Device type|Vendor|Product|Revision|Logical Unit|Physical|Transport protocol|Attached to|=== START OF READ SMART DATA SECTION ===)' \
		| grep -v '^$' || true
}

field_from_info() {
	local info="$1"
	local label="$2"
	echo "$info" | awk -F':' -v lbl="$label" '$1 ~ lbl {sub(/^[ \t]+/, "", $2); print $2; exit}'
}

print_ata_indicators() {
	local attrs="$1"
	local line

	while IFS= read -r line; do
		[[ -n "$line" ]] && log "    $line"
	done < <(grep -E '^(SMART overall-health|  5 |  9 |194 |197 |198 |199 )' <<<"$attrs" || true)
}

log "==================================================="
log "SMART Health Report for $HOST - $DATE"
log "==================================================="

OVERALL_OK=1
mapfile -t DEVICES < <(sudo smartctl --scan | grep -E ' (sat|scsi) ')

if [[ ${#DEVICES[@]} -eq 0 ]]; then
	log "No SATA/SCSI devices found by smartctl --scan. Exiting."
	exit 1
fi

log "Devices found:"
printf '%s\n' "${DEVICES[@]}" | tee -a "$LOG_FILE"
log ""

for entry in "${DEVICES[@]}"; do
	dev=$(echo "$entry" | awk '{print $1}')
	scan_dtype=$(echo "$entry" | awk '{print $3}')

	log "Checking device: $dev (scan type=$scan_dtype)..."

	# SATA drives behind LSI HBA often need -d sat for full SMART attributes
	smart_dtype="$scan_dtype"
	smart_out=""
	if sat_out=$(sudo smartctl -A -H -d sat "$dev" 2>/dev/null) && grep -q 'ID#' <<<"$sat_out"; then
		smart_dtype="sat"
		smart_out="$sat_out"
	fi
	if [[ -z "$smart_out" ]]; then
		smart_out=$(sudo smartctl -A -H -d "$scan_dtype" "$dev" 2>&1) || true
		smart_dtype="$scan_dtype"
	fi

	# Device identity - prefer sat -i for model on HBA-presented drives
	info=""
	for try_dtype in sat "$scan_dtype"; do
		if try_info=$(sudo smartctl -i -d "$try_dtype" "$dev" 2>/dev/null); then
			info="$try_info"
			break
		fi
	done
	if [[ -z "$info" ]]; then
		info=$(sudo smartctl -i -d "$scan_dtype" "$dev" 2>&1 || true)
	fi

	model=$(field_from_info "$info" 'Device Model|Model Number')
	vendor=$(field_from_info "$info" 'Vendor')
	product=$(field_from_info "$info" 'Product')
	if [[ -z "$model" && ( -n "$vendor" || -n "$product" ) ]]; then
		model="${vendor:+$vendor }${product}"
	fi
	serial=$(field_from_info "$info" 'Serial Number')
	capacity=$(field_from_info "$info" 'User Capacity')

	log "  Model:   ${model:-unknown}"
	log "  Serial:  ${serial:-unknown}"
	log "  Size:    ${capacity:-unknown}"
	log "  SMART via: -d $smart_dtype"
	printf '%s\n' "$info" >>"$LOG_FILE"

	if [[ -z "$smart_out" ]]; then
		log "  ERROR: smartctl returned no data for $dev"
		OVERALL_OK=0
		log "---------------------------------------------------"
		continue
	fi

	log ""
	log "  SMART data:"
	log_plain "$smart_out"

	log ""
	log "  Key failure indicators:"
	if [[ "$smart_dtype" == "sat" ]] && grep -q 'ID#' <<<"$smart_out"; then
		print_ata_indicators "$smart_out"
	else
		while IFS= read -r line; do
			[[ -n "$line" ]] && log "    $line"
		done < <(grep -Ei '^(SMART Health Status|SMART overall-health|Current Drive Temperature|Drive Trip Temperature)' <<<"$smart_out" || true)

		errors=$(sudo smartctl -l error -d "$scan_dtype" "$dev" 2>/dev/null || true)
		if grep -qi 'Error Counter logging not supported' <<<"$errors"; then
			log "    SCSI error counter log: not supported on this drive"
		elif [[ -n "$errors" ]]; then
			log ""
			log "  SCSI error counter log:"
			while IFS= read -r line; do
				[[ -n "$line" ]] && log "    $line"
			done < <(smart_data_lines <<<"$errors")
		fi

		if sat_attrs=$(sudo smartctl -A -d sat "$dev" 2>/dev/null) && grep -q 'ID#' <<<"$sat_attrs"; then
			log ""
			log "  ATA attributes (via -d sat):"
			print_ata_indicators "$sat_attrs"
		fi
	fi

	sudo smartctl -H -d "$smart_dtype" "$dev" >"$TMPFILE" 2>&1
	HEALTH_EXIT=$?
	HEALTH_LINE=$(grep -Ei 'SMART overall-health|SMART Health Status' "$TMPFILE" || true)

	log ""
	if [[ $HEALTH_EXIT -eq 0 ]]; then
		log "  Result: $dev PASSED"
	elif [[ $HEALTH_EXIT -eq 1 ]]; then
		log "  Result: $dev FAILED"
		[[ -n "$HEALTH_LINE" ]] && log "  Details: $HEALTH_LINE"
		OVERALL_OK=0
	elif [[ $HEALTH_EXIT -eq 2 ]]; then
		log "  Result: $dev UNKNOWN (SMART not supported or disabled)"
		[[ -n "$HEALTH_LINE" ]] && log "  Details: $HEALTH_LINE"
	else
		log "  Result: $dev ERROR (smartctl exit $HEALTH_EXIT)"
		OVERALL_OK=0
	fi

	log "---------------------------------------------------"
done

rm -f "$TMPFILE"

log "==================================================="
if [[ $OVERALL_OK -eq 1 ]]; then
	log "SUMMARY: All drives passed SMART health."
else
	log "SUMMARY: One or more drives reported SMART errors!"
fi
log "==================================================="

if [[ $OVERALL_OK -ne 1 ]]; then
	if echo "SMART detected problems on one or more drives! See log." |
		mailx -A "$LOG_FILE" -s "SMART ALERT - $HOST" "$MAIL_TO"; then
		log "Alert email sent to $MAIL_TO"
	else
		log "ERROR: Failed to send alert email. Log retained at $LOG_FILE"
	fi
	mv "$LOG_FILE" "${LOG_FILE%.log}-$DATE_SUFFIX.log"
	log "Log saved to ${LOG_FILE%.log}-$DATE_SUFFIX.log"
	exit 1
fi

exit 0
