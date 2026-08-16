#!/bin/bash

# Fetch the HTML list of Ubuntu mirrors and extract URLs of up-to-date mirrors
wget -q -O- https://launchpad.net/ubuntu/+archivemirrors > mirrors.txt
grep -P -B8 "statusUP" mirrors.txt | grep -o -P "(f|ht)tp://[^\"]*" > filtered_mirrors.txt

# Read the list of mirrors
mapfile -t mirrors < filtered_mirrors.txt
total_mirrors=${#mirrors[@]}

# Array to hold speeds
declare -A speeds

echo "Testing mirrors for speed..."

# Test each mirror with a 2-second timeout
for i in "${!mirrors[@]}"; do
    # Calculate the sequence number
    seq_num=$((i+1))
    
    # Get the speed in bytes per second and convert to kilobytes per second
    speed_bps=$(curl --max-time 2 -r 0-102400 -s -w %{speed_download} -o /dev/null "${mirrors[$i]}/ls-lR.gz")
    speed_kbps=$(echo "$speed_bps / 1024" | bc)
    
    # Save the speed with the mirror URL
    speeds["${mirrors[$i]}"]=$speed_kbps
    
    # Print the mirror and speed
    echo "[$seq_num/$total_mirrors] ${mirrors[$i]} --> $speed_kbps KB/s"
done

# Sort mirrors by speed and get the top 5
echo "Top 5 fastest mirrors:"
for mirror in "${!speeds[@]}"; do
    echo "$mirror ${speeds[$mirror]}"
done | sort -rn -k2 | head -5
