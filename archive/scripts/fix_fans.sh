#!/bin/bash

IPMI_USER="ADMIN"
IPMI_PASS="ADMIN"
IPMI_HOST="172.16.46.28"

# Desired thresholds
LOWER_NONCRIT=300
LOWER_CRIT=500
LOWER_NONRECOV=700

UPPER_NONCRIT=4000
UPPER_CRIT=4500
UPPER_NONRECOV=5000

# List of fans to configure
FANS=("FAN1" "FAN2" "FAN4")

for FAN in "${FANS[@]}"; do
	echo "Setting thresholds for $FAN..."

	ipmitool -I lanplus -H "$IPMI_HOST" -U "$IPMI_USER" -P "$IPMI_PASS" \
		sensor thresh "$FAN" lower $LOWER_NONCRIT $LOWER_CRIT $LOWER_NONRECOV

	ipmitool -I lanplus -H "$IPMI_HOST" -U "$IPMI_USER" -P "$IPMI_PASS" \
		sensor thresh "$FAN" upper $UPPER_NONCRIT $UPPER_CRIT $UPPER_NONRECOV
done

echo "Thresholds updated."
