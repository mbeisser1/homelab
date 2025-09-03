#!/bin/bash

# For every mkv file in the cwd make a folder with that basename and then move the file into that folder. 

# /
#  a.mkv
#  b.mkv
#  c.mkv
 
# /a/a.mkv
# /b/b.mkv
# /c.c.mkv

find . -maxdepth 1 -iname "*.mkv" -exec sh -c 'mkdir "${1%.*}" ; mv "$1" "${1%.*}" ' _ {} \;
