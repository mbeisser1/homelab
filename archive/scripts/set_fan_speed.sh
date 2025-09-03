#!/bin/bash

# Attempt to extract the IPMI IP address from ipmitool
ipmi_output=$(ipmitool lan print 1 2>/dev/null)
ipmi_ip=$(echo "$ipmi_output" | awk -F ': *' '/^IP Address[[:space:]]*:/ {print $2}' | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1)

# Check if IP was found
if [[ -z "$ipmi_ip" ]]; then
  echo "Error: Could not determine IPMI IP address from 'ipmitool lan print 1'"
  exit 1
fi

echo "Found IPMI IP address: $ipmi_ip"

# Define the fan commands
fan_cmds=(
  "ipmitool -H $ipmi_ip -U root -P root sensor thresh FAN3 lower 100 200 300"
  "ipmitool -H $ipmi_ip -U root -P root sensor thresh FAN4 lower 100 200 300"
)

# Run and check each command
for cmd in "${fan_cmds[@]}"; do
  echo "Running: $cmd"
  if ! eval "$cmd"; then
    echo "Error: Command failed — $cmd"
    exit 1
  fi
done

echo "IPMI fan thresholds set successfully."
