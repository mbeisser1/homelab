#!/bin/bash

#rename 's/\./\ /g' *
rename 's/\ /\./g' ./*
rename 's/\_/\./g' ./*
rename 's/\.\./\./g' ./*

rename 's/5\ 1/5\.1/g' ./*
rename 's/7\ 1/7\.1/g' ./*

rename 's/1080P/[1080p]/i' ./*
#rename 's/1080/[1080p]/i' ./*
rename 's/720P/[720p]/i' ./*
#rename 's/720/[720p]/i' ./*
rename 's/BluRay/BRRip/i' ./*
rename 's/Blu-Ray/BRRip/i' ./*
rename 's/BDRIP/BRRip/i' ./*
rename 's/BLUEBIRD//i' ./*
rename 's/LIMITED//i' ./*
rename 's/MULTI//i' ./*
rename 's/REMASTERED//i' ./*
rename 's/EXTENDED//i' ./*
rename 's/BLUEBIRD//i' ./*
rename 's/\[Open\.Matte\]//i' ./* 
rename 's/repack//i' ./*
rename 's/proper//i' ./*

# Put parentheses around year
rename 's/\.([0-9]{4})\./\.\($1\)\./g' ./*

# Remove trailing -264-XXXX crap
#rename 's/[xX]264-\w./*x264/' ./*

# Remove trailing -XXXXX garbage
rename 's/(.*)(-.*)/$1/' ./*

#avoid duplicate [[]]
rename 's/\[\[/\[/g' ./*
rename 's/\]\]/\]/g' ./*

# ends with .
rename 's/\.$//' ./*
rename 's/\-$//' ./*
rename 's/\ $//' ./*

# rename XX..YY -> XX.YY
rename 's/\.\./\./g' ./*

find . -type d -iname '*sample*' -execdir rm -r {} \;
find . -type f -iname '*sample*' -execdir rm -r {} \;
find . -type d -iname '*proof*' -execdir rm -r {} \;
