#!/bin/bash

#!/bin/bash

INNAME=${1}
OUTNAME=$(basename -s .ts ${INNAME}).mkv

if [ -z "${INNAME}" ]; then
    echo "Input .ts file required required."
else
    CMD="ffmpeg -fflags +genpts -i ${INNAME} -c:v copy -c:a aac ${OUTNAME}"
    echo $CMD
    $(${CMD})
fi
