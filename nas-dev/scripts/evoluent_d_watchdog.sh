#!/bin/bash
#set -euo pipefail
set -eu

# Desired button mapping (Adjust if needed)
MAP_WANTED="1 2 3 4 5 6 7 9 2 8"

# Name to identify your mouse in xinput
DEVICE_NAME="Evoluent"

echo "Starting Evoluent mapping watchdog..."

while true; do
  # 
  # Find the Device ID using grep and cut.
  #
  # 1. xinput --list --short prints the list of devices.
  # 2. grep -i "$DEVICE_NAME" filters for lines containing "Evoluent".
  # 3. grep "slave pointer" ensures we get the mouse device, not the core keyboard.
  # 4. head -n 1 ensures we only act on the first match if multiple appear.
  #
  DEVICE_LINE=$(xinput --list --short 2>/dev/null | grep -i "$DEVICE_NAME" | grep "slave pointer" | head -n 1)

  if [[ -n "$DEVICE_LINE" ]]; then

    # 
    # Extract the ID number from the line.
    # Example Line: ⎜   ↳ Evoluent VerticalMouse 4          id=11   [slave  pointer  (2)]
    #
    # Step 1: echo "$DEVICE_LINE" prints the found text.
    # Step 2: cut -d= -f2 splits the text at the "=" symbol and keeps the second part.
    #         Result of step 2: "11   [slave  pointer  (2)]"
    # Step 3: cut -d' ' -f1 splits that text at the space and keeps the first part.
    #         Result of step 3: "11"
    #
    DEVICE_ID=$(echo "$DEVICE_LINE" | cut -d= -f2 | cut -d' ' -f1)

    # Get the current mapping
    MAP_NOW=$(xinput get-button-map "$DEVICE_ID" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')

    # Compare and fix if needed
    if [[ "$MAP_NOW" != "$MAP_WANTED" ]]; then
      echo "$(date): Fixing mapping for device ${DEVICE_ID} (was: ${MAP_NOW})"
      # Apply the new mapping.
      xinput set-button-map "$DEVICE_ID" $MAP_WANTED
    fi
  fi

  # Wait before trying again
  sleep 10
done
