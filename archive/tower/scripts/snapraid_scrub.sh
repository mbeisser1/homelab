#!/bin/bash

LOG_FILE="/tmp/snapraid_status.log"
SCRUB_LOG="/tmp/snapraid_scrub.log"

MAIL_TO="mjbeisser@gmail.com"
MAIL_SUBJECT=""
MAIL_MSG=""

$(sudo snapraid status 2> /dev/null > ${LOG_FILE})
LASTLINE=$(cat ${LOG_FILE} | tail -n 1)

if [ "${LASTLINE}" == "No error detected." ]; then
    #$(sudo snapraid -p 20 scrub 2>&1 > "${SCRUB_LOG}")
    $(sudo snapraid -p 25 -o 20 scrub > "${SCRUB_LOG}")
    rtnstatus=$?

    if [[ $rtnstatus -eq 0 ]]; then
        MAIL_SUBJECT="Snapraid scrub success"
        MAIL_MSG="Weekly snapraid scrub success. No errors encountered. See log."
    else
        MAIL_SUBJECT="Snapraid scrub failed"
        MAIL_MSG="Weekly snapraid scrub FAILED. Error [${rtnstatus}] encountered. See log."
    fi

    echo ${MAIL_MSG} | mailx -A ${SCRUB_LOG} -s ${MAIL_SUBJECT} ${MAIL_TO} 

else
    MAIL_SUBJECT="Snapraid status failure"
    MAIL_MSG="Weekly snapraid scrub skipped. Errors were found. See log."

    echo ${MAIL_MSG} | mailx -A ${LOG_FILE} -s ${MAIL_SUBJECT} ${MAIL_TO} 
fi

