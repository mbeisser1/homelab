#!/bin/bash
# smart_report.sh
# Collect SMART health for all drives; optional markdown report of issues only.

set -euo pipefail

LOG_FILE="/tmp/smart_status.log"
DATE_SUFFIX=$(date +%F)
MAIL_TO="snapraid@bitrealm.dev"

MARKDOWN_FILE=""
QUIET=0

# When invoked via sudo, write user-facing output as the original user.
CALLER_UID="${SUDO_UID:-$(id -u)}"
CALLER_GID="${SUDO_GID:-$(id -g)}"
DRIVE_SEP="======================================================="

usage() {
	cat <<'EOF'
Usage: smart_report.sh [options]

Options:
  -m, --markdown FILE   Write a readable markdown report (use - for stdout)
  -q, --quiet           Suppress verbose terminal output (useful with --markdown)
  -h, --help            Show this help

Examples:
  sudo smart_report.sh
  sudo smart_report.sh -m /tmp/smart-report.md
  sudo smart_report.sh -m - -q
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	-m | --markdown)
		MARKDOWN_FILE="${2:?missing argument for $1}"
		shift 2
		;;
	-q | --quiet) QUIET=1; shift ;;
	-h | --help)
		usage
		exit 0
		;;
	*) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
	esac
done

>"$LOG_FILE"

HOST=$(hostname -s)
DATE=$(date '+%Y-%m-%d %H:%M:%S')
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT

# Per-drive collected data (parallel arrays)
DRIVE_DEVS=()
DRIVE_MODELS=()
DRIVE_SERIALS=()
DRIVE_HEALTH=()
DRIVE_TEMP=()
DRIVE_STATUS=()
DRIVE_ISSUE_COUNT=()
DRIVE_ISSUE_LINES=()
DRIVE_HAS_ALERT=()

log() {
	[[ $QUIET -eq 1 ]] && return 0
	echo "$*" | tee -a "$LOG_FILE"
}

log_drive_sep() {
	[[ $QUIET -eq 1 ]] && return 0
	echo "$DRIVE_SEP" | tee -a "$LOG_FILE"
}

# Write a file owned by the invoking user (not root when run via sudo).
write_file_as_caller() {
	local dest="$1"
	local content="$2"
	local tmp_out

	if [[ "$dest" == "-" ]]; then
		printf '%s\n' "$content"
		return 0
	fi

	tmp_out=$(mktemp)
	printf '%s\n' "$content" >"$tmp_out"
	rm -f -- "$dest"
	if [[ $(id -u) -eq 0 && -n "${SUDO_UID:-}" ]]; then
		install -o "$CALLER_UID" -g "$CALLER_GID" -m 0644 "$tmp_out" "$dest"
	else
		install -m 0644 "$tmp_out" "$dest"
	fi
	rm -f "$tmp_out"
}

field_from_info() {
	local info="$1"
	local label="$2"
	echo "$info" | awk -F':' -v lbl="$label" '$1 ~ lbl {sub(/^[ \t]+/, "", $2); print $2; exit}'
}

print_ata_indicators() {
	local attrs="$1"
	local header line

	while IFS= read -r line; do
		[[ -n "$line" ]] && log "  $line"
	done < <(grep -Ei '^SMART overall-health' <<<"$attrs" || true)

	header=$(grep -E '^ID# ATTRIBUTE_NAME' <<<"$attrs" | head -n1 || true)
	if [[ -n "$header" ]]; then
		log "  $header"
	else
		log "  ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE"
	fi

	while IFS= read -r line; do
		[[ -n "$line" ]] && log "  $line"
	done < <(grep -E '^(  5 |  9 |194 |197 |198 |199 )' <<<"$attrs" || true)
}

# Parse SMART health line from smartctl output
health_from_output() {
	local out="$1"
	local line
	line=$(grep -Ei 'SMART overall-health|SMART Health Status' <<<"$out" | head -n1 || true)
	if grep -qi 'PASSED\|: OK' <<<"$line"; then
		echo "PASSED"
	elif grep -qi 'FAIL' <<<"$line"; then
		echo "FAILED"
	elif [[ -n "$line" ]]; then
		echo "$line" | sed -E 's/^.*: *//'
	else
		echo "UNKNOWN"
	fi
}

# Extract temperature Celsius from attribute 194 raw field
temp_from_attrs() {
	local attrs="$1"
	local raw
	raw=$(awk '$1 == 194 {print $NF; exit}' <<<"$attrs" || true)
	if [[ -n "$raw" ]]; then
		echo "$raw" | grep -Eo '^[0-9]+' | head -n1
		return
	fi
	grep -Ei 'Current Drive Temperature' <<<"$attrs" | head -n1 | grep -Eo '[0-9]+' | head -n1
}

# Build monitored-attribute rows for markdown (always all fields)
# Output format per line: name|raw|alert  (alert empty when OK)
build_monitored_rows() {
	local attrs="$1"
	local health="$2"

	awk -v health="$health" '
		/^ *[0-9]+ / {
			id = $1
			name[id] = $2
			rawv[id] = $NF
			wfv[id] = $(NF-1)
		}
		function alert_for(id,    r, w, temp) {
			if (!(id in rawv)) return ""
			r = rawv[id]
			w = wfv[id]
			if (w != "-") return "critical"
			if (id == 5 || id == 197 || id == 198) {
				if (r + 0 > 0) return "critical"
			} else if (id == 196 || id == 199 || id == 188) {
				if (r + 0 > 0) return "warning"
			} else if (id == 194) {
				temp = r
				sub(/\(.*/, "", temp)
				if (temp + 0 >= 60) return "critical"
				if (temp + 0 >= 55) return "warning"
			}
			return ""
		}
		function val(id,    v) {
			if (id in rawv) {
				v = rawv[id]
				if (id == 194) sub(/\(.*/, "", v)
				return v
			}
			return "—"
		}
		function label(id) {
			if (id in name) return name[id]
			if (id == 5) return "Reallocated_Sector_Ct"
			if (id == 196) return "Reallocated_Event_Count"
			if (id == 197) return "Current_Pending_Sector"
			if (id == 198) return "Offline_Uncorrectable"
			if (id == 199) return "UDMA_CRC_Error_Count"
			if (id == 188) return "Command_Timeout"
			if (id == 194) return "Temperature_Celsius"
			return "attr_" id
		}
		BEGIN {
			split("5,196,197,198,199,188,194", ids, ",")
		}
		END {
			halert = (health == "FAILED" || health == "ERROR") ? "critical" : ""
			printf "SMART health|%s|%s\n", health, halert
			for (i = 1; i <= length(ids); i++) {
				id = ids[i] + 0
				printf "%s|%s|%s\n", label(id), val(id), alert_for(id)
			}
		}
	' <<<"$attrs"
}

# Sets DRIVE_ISSUE_COUNT and DRIVE_ISSUE_LINES for markdown + email gating
collect_monitored_data() {
	local idx="$1"
	local attrs="$2"
	local health="$3"
	local -a rows=()
	local row name raw alert
	local has_alert=0
	local count=0

	while IFS='|' read -r name raw alert; do
		rows+=("$name|$raw|$alert")
		if [[ -n "$alert" ]]; then
			has_alert=1
			((count++)) || true
			[[ "$alert" == "critical" ]] && : # counted
		fi
	done < <(build_monitored_rows "$attrs" "$health")

	DRIVE_HAS_ALERT[$idx]=$has_alert
	DRIVE_ISSUE_COUNT[$idx]=$count
	DRIVE_ISSUE_LINES[$idx]=$(printf '%s\n' "${rows[@]}")
}

write_markdown_report() {
	local outfile="$1"
	local -a md=()
	local total_alerts=0
	local idx dev model serial health temp status count has_alert

	md+=("# SMART Report: $HOST")
	md+=("")
	md+=("Generated: $DATE")
	md+=("")
	md+=("## Summary")
	md+=("")
	md+=("| Device | Model | Serial | Health | Temp (C) | Status |")
	md+=("| ------ | ----- | ------ | ------ | -------- | ------ |")

	for idx in "${!DRIVE_DEVS[@]}"; do
		dev="${DRIVE_DEVS[$idx]}"
		model="${DRIVE_MODELS[$idx]}"
		serial="${DRIVE_SERIALS[$idx]}"
		health="${DRIVE_HEALTH[$idx]}"
		temp="${DRIVE_TEMP[$idx]:-—}"
		count="${DRIVE_ISSUE_COUNT[$idx]:-0}"
		has_alert="${DRIVE_HAS_ALERT[$idx]:-0}"
		total_alerts=$((total_alerts + count))

		if [[ "$health" == "FAILED" || "$health" == "ERROR" ]]; then
			status="FAILED"
		elif [[ $has_alert -eq 1 ]]; then
			status="${count} alert(s)"
		else
			status="OK"
		fi

		md+=("| $dev | $model | $serial | $health | $temp | $status |")
	done

	md+=("")
	md+=("## Monitored attributes")
	md+=("")
	md+=("All monitored fields are shown for every drive. The **Alert** column appears only when a drive has a detected problem.")
	md+=("")

	for idx in "${!DRIVE_DEVS[@]}"; do
		dev="${DRIVE_DEVS[$idx]}"
		model="${DRIVE_MODELS[$idx]}"
		has_alert="${DRIVE_HAS_ALERT[$idx]:-0}"

		md+=("### $dev - $model")
		md+=("")

		if [[ $has_alert -eq 1 ]]; then
			md+=("| Attribute | Raw | Alert |")
			md+=("| --------- | --- | ----- |")
			while IFS='|' read -r name raw alert; do
				[[ -z "$alert" ]] && alert="OK"
				md+=("| $name | $raw | $alert |")
			done <<<"${DRIVE_ISSUE_LINES[$idx]}"
		else
			md+=("| Attribute | Raw |")
			md+=("| --------- | --- |")
			while IFS='|' read -r name raw alert; do
				md+=("| $name | $raw |")
			done <<<"${DRIVE_ISSUE_LINES[$idx]}"
		fi
		md+=("")
	done

	md+=("## Alert thresholds")
	md+=("")
	md+=("| ID | Attribute | Alert level |")
	md+=("| -- | --------- | ----------- |")
	md+=("| — | SMART health | critical if FAILED |")
	md+=("| 5 | Reallocated_Sector_Ct | critical if raw > 0 |")
	md+=("| 196 | Reallocated_Event_Count | warning if raw > 0 |")
	md+=("| 197 | Current_Pending_Sector | critical if raw > 0 |")
	md+=("| 198 | Offline_Uncorrectable | critical if raw > 0 |")
	md+=("| 199 | UDMA_CRC_Error_Count | warning if raw > 0 |")
	md+=("| 188 | Command_Timeout | warning if raw > 0 |")
	md+=("| 194 | Temperature_Celsius | warning >= 55 C, critical >= 60 C |")

	local content
	content=$(printf '%s\n' "${md[@]}")

	write_file_as_caller "$outfile" "$content"
	if [[ "$outfile" != "-" && $QUIET -eq 0 ]]; then
		echo "Markdown report written to $outfile"
	fi
}

log "$DRIVE_SEP"
log "SMART Health Report for $HOST - $DATE"
log "$DRIVE_SEP"

OVERALL_OK=1
mapfile -t DEVICES < <(sudo smartctl --scan | grep -E ' (sat|scsi) ')

if [[ ${#DEVICES[@]} -eq 0 ]]; then
	log "No SATA/SCSI devices found by smartctl --scan. Exiting."
	exit 1
fi

log "Devices found:"
printf '%s\n' "${DEVICES[@]}" | tee -a "$LOG_FILE"

drive_idx=0
for entry in "${DEVICES[@]}"; do
	[[ $drive_idx -gt 0 ]] && log_drive_sep

	dev=$(echo "$entry" | awk '{print $1}')
	scan_dtype=$(echo "$entry" | awk '{print $3}')

	log "Checking device: $dev (scan type=$scan_dtype)..."

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

	if [[ -z "$smart_out" ]]; then
		log "  ERROR: smartctl returned no data for $dev"
		OVERALL_OK=0
		DRIVE_DEVS[$drive_idx]="$dev"
		DRIVE_MODELS[$drive_idx]="${model:-unknown}"
		DRIVE_SERIALS[$drive_idx]="${serial:-unknown}"
		DRIVE_HEALTH[$drive_idx]="ERROR"
		DRIVE_TEMP[$drive_idx]=""
		DRIVE_HAS_ALERT[$drive_idx]=1
		DRIVE_ISSUE_COUNT[$drive_idx]=1
		DRIVE_ISSUE_LINES[$drive_idx]="SMART health|ERROR|critical"
		((drive_idx++)) || true
		continue
	fi

	if [[ $QUIET -eq 0 ]]; then
		log "  Key failure indicators:"
		if [[ "$smart_dtype" == "sat" ]] && grep -q 'ID#' <<<"$smart_out"; then
			print_ata_indicators "$smart_out"
		else
			while IFS= read -r line; do
				[[ -n "$line" ]] && log "  $line"
			done < <(grep -Ei '^(SMART Health Status|SMART overall-health|Current Drive Temperature|Drive Trip Temperature)' <<<"$smart_out" || true)
		fi
	fi

	sudo smartctl -H -d "$smart_dtype" "$dev" >"$TMPFILE" 2>&1
	HEALTH_EXIT=$?
	HEALTH_LINE=$(grep -Ei 'SMART overall-health|SMART Health Status' "$TMPFILE" || true)
	health=$(health_from_output "$smart_out")
	[[ $HEALTH_EXIT -eq 1 ]] && health="FAILED"
	temp=$(temp_from_attrs "$smart_out")

	collect_monitored_data "$drive_idx" "$smart_out" "$health"
	[[ "$health" == "FAILED" ]] && OVERALL_OK=0
	if [[ ${DRIVE_HAS_ALERT[$drive_idx]:-0} -eq 1 ]]; then
		while IFS='|' read -r _ _ alert; do
			[[ "$alert" == "critical" ]] && OVERALL_OK=0 && break
		done <<<"${DRIVE_ISSUE_LINES[$drive_idx]}"
	fi

	DRIVE_DEVS[$drive_idx]="$dev"
	DRIVE_MODELS[$drive_idx]="${model:-unknown}"
	DRIVE_SERIALS[$drive_idx]="${serial:-unknown}"
	DRIVE_HEALTH[$drive_idx]="$health"
	DRIVE_TEMP[$drive_idx]="${temp:-}"

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

	((drive_idx++)) || true
done

log_drive_sep
if [[ $OVERALL_OK -eq 1 ]]; then
	log "SUMMARY: All drives passed SMART health."
else
	log "SUMMARY: One or more drives reported SMART errors!"
fi
log "$DRIVE_SEP"

if [[ -n "$MARKDOWN_FILE" ]]; then
	write_markdown_report "$MARKDOWN_FILE"
fi

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
