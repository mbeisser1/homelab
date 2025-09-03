#!/bin/bash

#if [[ $EUID -ne 0 ]]; then
#    echo "This script must be run as root" 
#    exit 1
#fi

LOG_FILE="/tmp/snapraid_status.log"

$(sudo snapraid status 2> /dev/null > ${LOG_FILE})
LASTLINE=$(cat ${LOG_FILE} | tail -n 1)

if [ "${LASTLINE}" == "No error detected." ]; then
    $(sudo snapraid sync)
    #echo "Daily snapraid sync success. No errors were found. See log." | mailx -A ${LOG_FILE} -s "Snapraid status sync success" "mjbeisser@gmail.com"
else
    echo "Daily snapraid sync skipped. Errors were found. See log." | mailx -A ${LOG_FILE} -s "Snapraid status failure" "mjbeisser@gmail.com"
fi

