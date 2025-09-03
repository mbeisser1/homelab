#!/bin/bash

while [ 1 ]
do
    rsync -azvvP -e ssh beissemj@thoon.feralhosting.com:/media/sdx1/beissemj/private/deluge/completed/* /plex/transfer/
    if [ "$?" = "0" ] ; then
        echo "rsync completed normally"
        exit
    else
        echo "Rsync failure. Backing off and retrying..."
        sleep 180
    fi
done
