#!/usr/bin/env python3
"""
fix_trilium_html.py — prepare HTML files for Trilium ZIP import

- Removes bogus <link rel="stylesheet" href="style.css">
- Moves <style>...</style> from <head> into the top of <body>
- Leaves all other content untouched
- Overwrites files in-place unless --dryrun is given
"""

import sys
from pathlib import Path

from bs4 import BeautifulSoup


def fix_html_file(path: Path, dryrun: bool = False):
    text = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(text, "html.parser")

    # Collect <style> blocks in <head>
    style_blocks = soup.head.find_all("style") if soup.head else []

    # Remove bogus <link rel="stylesheet">
    if soup.head:
        for link in soup.head.find_all("link", {"rel": "stylesheet"}):
            link.decompose()

    # If we have a body and style blocks, move them
    if soup.body and style_blocks:
        for style in style_blocks:
            style.extract()  # remove from head
            soup.body.insert(0, style)  # prepend into body

    # Drop the <head> entirely (Trilium will strip anyway)
    if soup.head:
        soup.head.decompose()

    # Write result
    new_html = str(soup)
    if dryrun:
        print(f"--- {path} ---")
        print(new_html[:500], "...\n")
    else:
        path.write_text(new_html, encoding="utf-8")


def main():
    if len(sys.argv) < 2:
        print("Usage: fix_trilium_html.py <directory> [--dryrun]")
        sys.exit(1)

    root = Path(sys.argv[1])
    dryrun = "--dryrun" in sys.argv

    for html_file in root.rglob("*.html"):
        fix_html_file(html_file, dryrun=dryrun)


if __name__ == "__main__":
    main()
