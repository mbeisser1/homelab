#!/bin/bash

# Given an input file of an hd-torrents.org query this will generate the links

egrep 'You are not active on this torrent' ${1} | perl -lape 's/(.*)(download.php\?.*\.torrent)(.*)/https:\/\/hd-torrents\.org\/$2/g' | perl -lape 's/\&amp;/\&/g' | grep -i '^https'
