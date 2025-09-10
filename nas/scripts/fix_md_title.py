#!/usr/bin/env python3
"""
fix_md_title_v2.py

Transforms blocks like:

## Appointment 2019 Jan 20 (2020-01-19)
# 2020-01-19
**Created:**
# Appointment 2019 Jan 20

into:

# Appointment 2019 Jan 20
**Created:** 2020-01-19

Details:
- Handles multiple sections per file
- Allows blank lines between lines in the block
- Safe (--dry-run) preview mode
"""

from __future__ import annotations
import argparse
import pathlib
import re
import sys
from typing import List, Tuple

RE_H2_WITH_PARENS_DATE = re.compile(
    r'^\s*##\s+(?P<title_h2>.+?)\s*\(\s*(?P<date_h2>\d{4}-\d{2}-\d{2})\s*\)\s*$'
)
RE_H1_DATE_ONLY = re.compile(
    r'^\s*#\s+(?P<date_h1>\d{4}-\d{2}-\d{2})\s*$'
)
RE_CREATED_LINE = re.compile(
    r'^\s*\*\*Created:\*\*\s*(?P<created>.*)\s*$'
)
RE_H1_TITLE = re.compile(
    r'^\s*#\s+(?P<title_h1>.+?)\s*$'
)

def is_blank(line: str) -> bool:
    return line.strip() == ""

def detect_newline_style(text: str) -> str:
    # Preserve Windows newlines if present, else default to '\n'
    return "\r\n" if "\r\n" in text else "\n"

def try_match_block(lines: List[str], start: int) -> Tuple[bool, int, str, str]:
    """
    Attempt to match a full block starting at lines[start].

    Pattern (blank lines allowed between):
      H2: "## <title> (<YYYY-MM-DD>)"
      H1: "# <YYYY-MM-DD>"
      "**Created:**" (may be empty)
      H1: "# <title>"

    Returns:
      (matched, end_index_exclusive, final_title, final_date)
      If matched is False, other values are undefined.
    """
    i = start
    n = len(lines)

    # 1) H2 with paren date
    m = RE_H2_WITH_PARENS_DATE.match(lines[i]) if i < n else None
    if not m:
        return (False, 0, "", "")
    i += 1

    # skip blanks
    while i < n and is_blank(lines[i]): i += 1

    # 2) H1 with date
    if i >= n: return (False, 0, "", "")
    m2 = RE_H1_DATE_ONLY.match(lines[i])
    if not m2:
        return (False, 0, "", "")
    date_h1 = m2.group("date_h1")
    i += 1

    # skip blanks
    while i < n and is_blank(lines[i]): i += 1

    # 3) **Created:** line (may be empty content)
    if i >= n: return (False, 0, "", "")
    m3 = RE_CREATED_LINE.match(lines[i])
    if not m3:
        return (False, 0, "", "")
    i += 1

    # skip blanks
    while i < n and is_blank(lines[i]): i += 1

    # 4) H1 final title
    if i >= n: return (False, 0, "", "")
    m4 = RE_H1_TITLE.match(lines[i])
    if not m4:
        return (False, 0, "", "")

    final_title = m4.group("title_h1").strip()
    end = i + 1  # block ends after final H1 line

    # Prefer H1 date; fall back to H2 date just in case
    final_date = date_h1 or m.group("date_h2")
    return (True, end, final_title, final_date)

def transform_text(text: str) -> Tuple[str, int]:
    nl = detect_newline_style(text)
    lines = text.splitlines()

    out: List[str] = []
    i = 0
    replaced = 0
    while i < len(lines):
        matched, end_idx, title, date = try_match_block(lines, i)
        if matched:
            # Replace entire block with the two normalized lines
            out.append(f"# {title}")
            out.append(f"**Created:** {date}")
            replaced += 1
            i = end_idx
        else:
            out.append(lines[i])
            i += 1

    # Preserve trailing newline if the original had one
    result = nl.join(out)
    if text.endswith(("\n", "\r\n")):
        result += nl
    return result, replaced

def process_file(path: pathlib.Path, dry_run: bool) -> int:
    try:
        original = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] read {path}: {e}", file=sys.stderr)
        return 1

    new_text, count = transform_text(original)

    if dry_run:
        print(f"[DRY-RUN] {path}: fixed {count} block(s).", file=sys.stderr)
        print(new_text, end="")
        return 0

    if count == 0:
        print(f"[OK] {path}: no changes.", file=sys.stderr)
        return 0

    try:
        path.write_text(new_text, encoding="utf-8")
        print(f"[OK] {path}: fixed {count} block(s).", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"[ERROR] write {path}: {e}", file=sys.stderr)
        return 1

def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize Appointment sections to '# Title' + '**Created:** YYYY-MM-DD'.")
    ap.add_argument("files", nargs="+", help="Markdown file(s) to process")
    ap.add_argument("-n", "--dry-run", action="store_true", help="Print transformed content to stdout (don’t write files)")
    args = ap.parse_args()

    rc = 0
    for f in args.files:
        rc |= process_file(pathlib.Path(f), args.dry_run)
    return rc

if __name__ == "__main__":
    sys.exit(main())

