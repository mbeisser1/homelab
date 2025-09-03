#!/bin/bash

SRC=${1}
DEST=${2}
EXIT=0

if [ -z "${SRC}" ]; then
	echo "Source path required. (Default: /completed/*)"
	EXIT=1
fi

if [ -z "${DEST}" ]; then
	#echo "Destination path required. (Default: /pool/tranfer/)"
	echo "Destination path required. Defaultng to /pool/tranfer/"
    DEST="/pool/transfer/"
	#EXIT=1
fi

if [ ${EXIT} -eq 1 ]; then
	#echo "rsync -vPr -e ssh mbeisser@vnode0059.pulsedmedia.com:/home/mbeisser/completed/* /pool/transfer/"
	#echo "rsync -vPr -e ssh mbeisser@3-129vulture.pulsedmedia.com:/home/mbeisser/completed/* /pool/transfer/"
	echo "rsync -vPr -e ssh mbeisser@3-143alicia.pulsedmedia.com:/home/mbeisser/completed/* /pool/transfer/"
	exit -1
fi

CMD="rsync -vPr -e ssh mbeisser@3-143alicia.pulsedmedia.com:/home/mbeisser/${SRC} ${DEST}"
echo "${CMD}"
exec ${CMD}
