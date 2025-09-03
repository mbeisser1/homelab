#!/bin/bash

# unrar part
find . -regextype sed -regex '.*part0\+1\.rar' -execdir unrar e {} \;

#find -iname '*.rar' -execdir unrar e {} \;
RARFILES=( $(find . -iname '*.rar' | grep -v part) )

for f in "${RARFILES[@]}"
do
    DIR=$(dirname ${f}) 
    cd ${DIR}
    # Get filename, we would remove .foo if it existed but we want the extension
    FBNAME=$(basename "$f" .foo)
    unrar e $FBNAME
    cd -
done


