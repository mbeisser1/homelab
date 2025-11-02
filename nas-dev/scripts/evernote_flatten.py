#!/usr/bin/env python3
import argparse
from pathlib import Path
import shutil

def is_candidate_dir(d: Path) -> bool:
    """
    Returns True if directory d contains exactly one .md file named '<dirname>.md'
    and nothing else (ignores hidden files like .DS_Store).
    """
    if not d.is_dir():
        return False
    entries = [p for p in d.iterdir() if not p.name.startswith('.')]
    if len(entries) != 1:
        return False
    only = entries[0]
    expected = f"{d.name}.md"
    return only.is_file() and only.suffix.lower() == ".md" and only.name == expected

def process(root: Path, apply: bool) -> None:
    moved = 0
    skipped = 0
    deleted = 0

    for d in sorted([p for p in root.rglob("*") if p.is_dir()]):
        if not is_candidate_dir(d):
            skipped += 1
            continue

        src_md = d / f"{d.name}.md"
        dest_md = d.parent / src_md.name

        # Report
        action_hdr = "[APPLY]" if apply else "[DRYRUN]"
        print(f"{action_hdr} Candidate: {d}")
        print(f"         Move: {src_md}  ->  {dest_md}")

        if dest_md.exists():
            print(f"         SKIP: Destination already exists: {dest_md}")
            skipped += 1
            continue

        if apply:
            # Move the markdown file up one level
            shutil.move(str(src_md), str(dest_md))
            moved += 1

            # Remove the now-empty directory (only if empty)
            try:
                d.rmdir()
                deleted += 1
                print(f"         Deleted empty dir: {d}")
            except OSError:
                # Directory not empty (shouldn't happen given our check), leave it
                print(f"         WARN: Could not delete {d} (not empty).")
        else:
            moved += 1  # count planned move
            deleted += 1  # count planned delete

    print("\nSummary:")
    print(f"  Planned/Moved files : {moved}")
    print(f"  Planned/Deleted dirs: {deleted}")
    print(f"  Skipped              : {skipped}")

def main():
    ap = argparse.ArgumentParser(
        description="If a folder contains a single .md file named exactly like the folder, move that file up one level and delete the folder."
    )
    ap.add_argument("root", nargs="?", default=".", help="Root directory to scan (default: current directory).")
    ap.add_argument("--apply", action="store_true", help="Actually perform changes. Default is dry-run.")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Root does not exist: {root}")
        return

    process(root, apply=args.apply)

if __name__ == "__main__":
    main()

