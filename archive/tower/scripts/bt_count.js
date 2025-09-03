// Script to calculate the total size of data listed in all torrent files in a given directory.
// 
// Dependencies: Install `parse-torrent-file` and `glob` with `npm install`. `fs` is already a core library.
// Usage: Move all directories containing *.torrent files into the torrent/ directory
//        and run `node app.js`.
//        
// Author: https://github.com/dewey - 6.11.2014       

var parseTorrentFile = require('parse-torrent-file'),
    fs = require('fs'),
    glob = require('glob');

var total = 0;
var numberoftorrents = 0;

//glob(__dirname + "/*.torrent", function(err, files) {
glob("./*.torrent", function(err, files) { 
    if (!err) {
        for (var i = files.length - 1; i >= 0; i--) {
            numberoftorrents++
            // console.log("Scanned: " + files[i])

            var torrent = fs.readFileSync(files[i])
            var parsed
            try {
                parsed = parseTorrentFile(torrent)
                total += parsed.length
            } catch (e) {
                console.log(e)
            }
        };
        console.log("Total size: \n" + Math.round(total) + " bytes\n" + Math.round(total / 1024 / 1024) + " MB\n" + Math.round(total / 1024 / 1024 / 1024) + " GB")
        console.log("Number of Torrents: " + numberoftorrents)
    } else {
        console.log("Error reading torrent files.")
    }
})
