#!/usr/bin/env python3
# concat_notes_md.py
import argparse
import re
from pathlib import Path

# New primary format: "**Created:** 2016-11-13"
CREATED_BOLD_RE   = re.compile(r'^\s*\*\*\s*Created\s*:\s*\*\*\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*$', re.I)

# Backward-compat formats
CREATED_TABLE_RE  = re.compile(r'^\|\s*Created\s*\|\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*\|\s*$', re.I)
CREATED_LEGACY_RE = re.compile(r'^\s*Created\s*at\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*$', re.I)

def extract_created_date(md_path: Path) -> str:
    """
    Extracts the Created date (YYYY-MM-DD) from the markdown file.
    Supports:
      **Created:** YYYY-MM-DD
      | Created | YYYY-MM-DD |
      Created at: YYYY-MM-DD
    Returns '9999-99-99' if not found so undated files sort last.
    """
    try:
        with md_path.open("r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                s = raw.strip()
                m = CREATED_BOLD_RE.match(s)
                if m:
                    return m.group(1)
                m = CREATED_TABLE_RE.match(s)
                if m:
                    return m.group(1)
                m = CREATED_LEGACY_RE.match(s)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return "9999-99-99"

def process_directory(dir_path: Path, delete_sources: bool, dry_run: bool) -> bool:
    """
    Concatenate all .md files in dir_path (excluding the output file itself),
    sorted by Created date, into <FolderName>.md within the same directory.
    Optionally delete source files after writing.
    With dry_run=True, only print what would happen (no writes/deletes).
    Returns True if work would be (or was) done, else False.
    """
    if not dir_path.is_dir():
        return False

    folder_name = dir_path.name
    out_file = dir_path / f"{folder_name}.md"

    # Gather *.md files, excluding the output file (re-runs safe)
    md_files = [p for p in dir_path.glob("*.md") if p.name != out_file.name]
    if not md_files:
        return False

    # Pair files with dates, sort by date then by filename for stability
    dated = [(extract_created_date(p), p) for p in md_files]
    dated.sort(key=lambda t: (t[0], t[1].name))

    if dry_run:
        print(f"\n[DRY-RUN] Directory: {dir_path}")
        print(f"[DRY-RUN] Would write combined file: {out_file}")
        print("[DRY-RUN] Files in concat order:")
        for date, p in dated:
            print(f"  - {date}  {p.name}")
        if delete_sources:
            print("[DRY-RUN] Would delete sources after writing:")
            for _, p in dated:
                print(f"    - {p}")
        return True

    # Write combined file
    try:
        with out_file.open("w", encoding="utf-8") as out:
            out.write(f"# {folder_name}\n\n")
            for date, p in dated:
                # Minimal extra heading per file; adjust if you want different structure.
                out.write(f"# {p.stem}\n")
                try:
                    out.write(p.read_text(encoding="utf-8", errors="ignore"))
                except Exception as e:
                    out.write(f"_Error reading {p.name}: {e}_\n")
                out.write("\n")
    except Exception as e:
        print(f"Error writing {out_file}: {e}")
        return False

    # Optionally delete originals
    if delete_sources:
        for _, p in dated:
            try:
                p.unlink()
                print(f"Deleted: {p}")
            except Exception as e:
                print(f"Could not delete {p}: {e}")

    print(f"Wrote: {out_file}")
    return True

def walk_and_process(root: Path, recursive: bool, delete_sources: bool, dry_run: bool) -> None:
    if dry_run and delete_sources:
        print("[NOTE] --dry-run specified: ignoring deletes (no files will be removed).")

    processed_any = False
    if recursive:
        # Process root first (if it has md files), then all subdirs
        processed_any |= process_directory(root, delete_sources, dry_run)
        for d in sorted([p for p in root.rglob("*") if p.is_dir()]):
            processed_any |= process_directory(d, delete_sources, dry_run)
    else:
        processed_any |= process_directory(root, delete_sources, dry_run)

    if not processed_any:
        print("No markdown files found to process.")

def main():
    ap = argparse.ArgumentParser(
        description="Concatenate markdown files (optionally recursively) into <FolderName>.md, sorted by **Created:** date."
    )
    ap.add_argument("path", nargs="?", default=".", help="Directory to process (default: current directory).")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="Process the directory and all subdirectories (one output per directory).")
    ap.add_argument("-d", "--delete", action="store_true",
                    help="Delete concatenated source .md files after writing the combined file.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Do not write or delete anything; print the output file and the ordered list of files.")
    args = ap.parse_args()

    root = Path(args.path).resolve()
    walk_and_process(root, recursive=args.recursive, delete_sources=args.delete, dry_run=args.dry_run)

if __name__ == "__main__":
    main()

