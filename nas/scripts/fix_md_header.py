#!/usr/bin/env python3
# md_fix_created_header.py
import argparse, re, sys
from pathlib import Path
from difflib import unified_diff

CREATED_LINE_RE = re.compile(r'^\s*\|\s*Created\s*\|\s*([^\|]+?)\s*\|\s*$', re.I)
H1_RE = re.compile(r'^\s*#\s+.*$')
DATE_IN_TEXT_RE = re.compile(r'\d{4}-\d{2}-\d{2}')  # prefer ISO date if present

def normalize_bom(line: str) -> str:
    return line.lstrip("\ufeff")

def transform(text: str, force: bool=False):
    lines = text.splitlines()
    if not lines:
        return None

    lines[0] = normalize_bom(lines[0])

    i = 0
    # skip leading blank lines
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines):
        return None

    m_created = CREATED_LINE_RE.match(lines[i])
    if not m_created:
        return None
    raw_date = m_created.group(1).strip()
    # prefer YYYY-MM-DD if present, else keep raw text
    dmatch = DATE_IN_TEXT_RE.search(raw_date)
    date = dmatch.group(0) if dmatch else raw_date

    i += 1
    # skip blank lines between the created row and the heading
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines):
        return None

    # require a first-level heading next
    if not H1_RE.match(lines[i]):
        return None
    heading_line = lines[i].rstrip()
    i += 1

    # check if a Created line already exists right after the H1
    j = i
    while j < len(lines) and lines[j].strip() == "":
        j += 1

    already = False
    if j < len(lines):
        line_after = lines[j].strip()
        if line_after.lower().startswith("**created:**"):
            if not force:
                # already transformed; do nothing unless forcing
                return None
            else:
                # drop the existing created line to replace with our normalized one
                j += 1
                # also drop one optional blank line after it
                if j < len(lines) and lines[j].strip() == "":
                    j += 1
                i = j  # remainder starts after the old Created block

    new_lines = []
    new_lines.append(heading_line)
    new_lines.append(f"**Created:** {date}")
    new_lines.append("")  # one blank line for readability
    new_lines.extend(lines[i:])

    new_text = "\n".join(new_lines).rstrip() + "\n"
    if new_text == text:
        return None
    return new_text

def main():
    ap = argparse.ArgumentParser(description="Move `| Created | … |` to a '**Created:** …' line under the first H1.")
    ap.add_argument("root", nargs="?", default=".", help="Root folder to scan (default: current directory)")
    ap.add_argument("--write", action="store_true", help="Apply changes in-place (otherwise dry-run)")
    ap.add_argument("--diff", action="store_true", help="Show unified diffs for changes")
    ap.add_argument("--force", action="store_true", help="Rewrite even if a '**Created:**' line already exists")
    ap.add_argument("--glob", default="**/*.md", help="Glob pattern relative to root (default: **/*.md)")
    ap.add_argument("--encoding", default="utf-8", help="File encoding (default: utf-8)")
    args = ap.parse_args()

    root = Path(args.root)
    changed = 0
    scanned = 0

    for md in root.rglob(args.glob.split("**/")[-1] if args.glob.startswith("**/") else args.glob):
        if not md.is_file() or md.suffix.lower() != ".md":
            continue
        scanned += 1
        try:
            original = md.read_text(encoding=args.encoding, errors="ignore")
        except Exception as e:
            print(f"[read-failed] {md}: {e}", file=sys.stderr)
            continue

        new_text = transform(original, force=args.force)
        if new_text is None:
            continue

        changed += 1
        print(f"[would-change] {md}")
        if args.diff:
            for line in unified_diff(
                original.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=str(md),
                tofile=str(md),
            ):
                sys.stdout.write(line)

        if args.write:
            try:
                md.write_text(new_text, encoding=args.encoding)
                print(f"[written] {md}")
            except Exception as e:
                print(f"[write-failed] {md}: {e}", file=sys.stderr)

    mode = "APPLIED" if args.write else "DRY-RUN"
    print(f"\nDone ({mode}). Scanned: {scanned}, Changed: {changed}")

if __name__ == "__main__":
    main()
