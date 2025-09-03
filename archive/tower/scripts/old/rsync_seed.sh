#!/bin/bash

#rsync -azvvP -e ssh beissemj@thoon.feralhosting.com:/media/sdx1/beissemj/private/deluge/data/${1} ${2}

rsync -azvvP -e ssh beissemj@thoon.feralhosting.com:/media/sdx1/beissemj/private/${1} ${2}
