#!/usr/bin/env bash
# rename_grace_sermons.sh — Rename EverNote sermon files using | Created | date
#
# Pattern: YYYY-MM-DD {PREFIX} - {title}.md  (or YYYY-MM-DD - {title} with -p '')
#
# Usage:
#   rename_grace_sermons.sh -d DIR [-p PREFIX] [-r] [-f] [-n] [-u]
#   rename_grace_sermons.sh -d DIR -p '' -n   # no prefix (EverNote misc notes)

set -euo pipefail

DIR=""
PREFIX="Grace"
DRY_RUN=false
UPDATE_TITLES=false
RECURSIVE=false
FLATTEN=false

usage() {
	cat <<EOF
Usage: $(basename "$0") -d DIR [-p PREFIX] [-r] [-f] [-n] [-u]

Rename .md files using | Created | YYYY-MM-DD | metadata in each file.
New name: YYYY-MM-DD PREFIX - {cleaned title}.md  (or YYYY-MM-DD - {title} with -p '')

Options:
  -d DIR      Directory containing sermon .md files (required)
  -p PREFIX   Church/series prefix in new filename (default: Grace; use '' for none)
  -r          Recurse into subdirectories
  -f          Flatten — write all outputs to DIR root (requires -r for subdirs)
  -n          Dry-run — print actions only
  -u          Update YAML title: and first # heading to match filename
  -h          Show this help
EOF
}

die() {
	echo "error: $*" >&2
	exit 1
}

while getopts ":d:p:rfnuh" opt; do
	case "$opt" in
	d) DIR="$OPTARG" ;;
	p) PREFIX="$OPTARG" ;;
	r) RECURSIVE=true ;;
	f) FLATTEN=true ;;
	n) DRY_RUN=true ;;
	u) UPDATE_TITLES=true ;;
	h)
		usage
		exit 0
		;;
	\?)
		die "unknown option: -$OPTARG"
		;;
	esac
done

[[ -n "$DIR" ]] || die "missing -d DIR"
[[ -d "$DIR" ]] || die "directory not found: $DIR"

exec python3 - "$DIR" "$PREFIX" "$DRY_RUN" "$UPDATE_TITLES" "$RECURSIVE" "$FLATTEN" <<'PYEOF'
import re
import sys
from pathlib import Path

DIR = Path(sys.argv[1])
PREFIX = sys.argv[2]
HAS_PREFIX = bool(PREFIX)
DRY_RUN = sys.argv[3].lower() == "true"
UPDATE_TITLES = sys.argv[4].lower() == "true"
RECURSIVE = sys.argv[5].lower() == "true"
FLATTEN = sys.argv[6].lower() == "true"

MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
SMALL_WORDS = {"a", "an", "and", "at", "for", "from", "in", "of", "the", "to"}


def parse_created(text: str) -> str | None:
    match = re.search(r"\|\s*Created\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", text)
    return match.group(1) if match else None


def first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return None


def date_variants(iso: str) -> set[str]:
    year, month, day = iso.split("-")
    month_i, day_i = int(month), int(day)
    month_short = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ][month_i - 1]
    month_long = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ][month_i - 1]

    variants = {
        iso,
        year,
        f"{month_short} {day_i}",
        f"{month_short}. {day_i}",
        f"{month_short}. {day_i}th",
        f"{month_short} {day_i}th",
        f"{month_short} {day_i}, {year}",
        f"{month_short} {day_i} {year}",
        f"{month_long} {day_i}",
        f"{month_long} {day_i}, {year}",
        f"{month_long} {day_i} {year}",
        f"{day_i} {month_short}",
        f"{day_i} {month_short} {year}",
        f"{day_i} {month_long} {year}",
        f"({day_i} {month_short})",
        f"({month_short} {day_i})",
        f"({month_long} {day_i})",
        f"({day_i} {month_long})",
        f"({day_i} {month_long} {year})",
        f"Dec {day_i}",
        f"9 Sept",
        f"Sept. {day_i}",
        f"Sept {day_i}",
        f"Oct {day_i}",
        f"Oct. {day_i}",
        f"{month_i}_{day_i}",
        f"{int(month)}_{day_i}",
        f"({int(month)}_{day_i})",
        f"({month_i}_{day_i})",
        f"2_14",
        f"(2_14)",
        f"{int(month)}/{day_i}",
        f"{int(month)}-{day_i}",
        f"August {day_i}th",
        f"August {day_i}",
        f"July {day_i}, {year}",
        f"July {day_i} {year}",
        f"July {day_i}",
        f"June {day_i}, {year}",
        f"Jan {day_i}",
        f"Jan. {day_i}",
        f"28 Mar {year}",
        f"3 April. {year}",
        f"3 April",
    }

    if day_i in (1, 21, 31):
        variants.add(f"{day_i}st {month_short}")
        variants.add(f"{day_i}st {month_long}")
    if day_i in (2, 22):
        variants.add(f"{day_i}nd {month_short}")
    if day_i in (3, 23):
        variants.add(f"{day_i}rd {month_short}")
    variants.add(f"{day_i}th {month_short}")
    variants.add(f"{day_i}th {month_long}")

    if HAS_PREFIX:
        variants.update({
            f"({PREFIX} {int(month)}_{day_i})",
            f"({PREFIX} {month_i}_{day_i})",
            f"({PREFIX} Sept. {day_i})",
            f"({PREFIX} {month_short}. {day_i})",
            f"{PREFIX} {int(month)}_{day_i}",
            f"{PREFIX} {month_i}_{day_i}",
            f"{PREFIX} Church {int(month)}_{day_i}",
            f"{PREFIX} Church {month_i}_{day_i}",
            f"({PREFIX} Singleness)",
            f"{PREFIX} Singleness",
        })

    return variants


def normalize_punctuation(text: str) -> str:
    text = re.sub(r"(?<!\d)_(?!\d)", " ", text)
    text = re.sub(r"\s*/\s*", " and ", text)
    text = re.sub(r"\s*&\s*", " and ", text)
    text = re.sub(r"\s*@\s*", " ", text)
    text = re.sub(r"\s*:\s*", ": ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"(?<!\d)\s*-\s*(?!\d)", " - ", text)
    text = re.sub(r"( - ){2,}", " - ", text)
    return text.strip()


def is_mixed_case_word(word: str) -> bool:
    letters = [c for c in word if c.isalpha()]
    if len(letters) < 2:
        return False
    uppers = sum(1 for c in letters if c.isupper())
    return 0 < uppers < len(letters)


def sanitize_caps(text: str) -> str:
    text = normalize_punctuation(text)

    def upper_repl(match: re.Match[str]) -> str:
        word = match.group(0)
        if is_mixed_case_word(word):
            return word
        return word.capitalize() if word.isalpha() else word

    text = re.sub(r"\b[A-Z]{2,}\b", upper_repl, text)

    words = text.split()
    result: list[str] = []
    for index, word in enumerate(words):
        prefix = ""
        suffix = ""
        core = word
        while core and not core[0].isalnum():
            prefix += core[0]
            core = core[1:]
        while core and not core[-1].isalnum():
            suffix = core[-1] + suffix
            core = core[:-1]

        if index > 0 and core.lower() in SMALL_WORDS:
            result.append(f"{prefix}{core.lower()}{suffix}")
            continue

        if is_mixed_case_word(core):
            result.append(word)
            continue
        elif core.isupper() and len(core) >= 2:
            result.append(f"{prefix}{core.capitalize()}{suffix}")
        elif core.islower() and HAS_PREFIX:
            result.append(f"{prefix}{core.capitalize()}{suffix}")
        else:
            result.append(word)

    text = " ".join(result)
    text = re.sub(r"(?<!\d)\s*-\s*(?!\d)", " - ", text)
    text = re.sub(r"( - ){2,}", " - ", text)
    return text.strip(" -")


def final_title_cleanup(text: str) -> str:
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"^\s*\)+\s*", "", text)
    if text.count("(") < text.count(")"):
        text = re.sub(r"\s*\)+\s*$", "", text)
    text = re.sub(r"^\s*\(\s*", "", text)
    text = text.strip(" ,;:-–—")
    text = re.sub(r"_____\.$", "_____", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def prep_seminar_title(text: str) -> str:
    is_seminar = bool(
        re.search(r"60\s+Minutes?\s+Seminars?|60\s+minute\s+seminar", text, flags=re.I)
    )
    text = re.sub(r"60\s+Minutes?\s+Seminars?", "", text, flags=re.I)
    text = re.sub(r"60\s+minute\s+seminar", "", text, flags=re.I)
    text = text.strip()

    text = re.sub(
        r"\(Pornography\s*-\s*Week\s*(\d+)\)",
        lambda m: f"Pornography Week {m.group(1)}",
        text,
        flags=re.I,
    )
    text = re.sub(r"^\s*\(Week\s+(\d+)\s*-\s*(\w+)\)\s*$", r"Week \1 \2", text, flags=re.I)
    text = re.sub(r"^\s*\(Week\s+\d+\)\s*", "", text, flags=re.I)

    match = re.match(r"^\s*\(([^)]+)\)\s+(.+)$", text)
    if match:
        topic, rest = match.group(1), match.group(2).strip()
        if not re.match(r"^Week\s+\d+", topic, flags=re.I):
            text = f"{topic} - {rest}"

    text = text.strip()
    if is_seminar and text:
        text = f"60 Minute Seminar - {text}"
    return text


def clean_title(title: str, iso: str) -> str:
    text = title.strip()
    text = re.sub(r"^\d{4}-\d{2}-\d{2}\s*(?:-\s*)?", "", text).strip()
    if HAS_PREFIX:
        text = re.sub(r"\bCelwbration\b", PREFIX, text, flags=re.I).strip()
        text = prep_seminar_title(text)

    for variant in sorted(date_variants(iso), key=len, reverse=True):
        if len(variant) < 2:
            continue
        text = re.sub(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", "", text, flags=re.I)

    text = re.sub(
        rf"\(\s*(?:{MONTHS})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?\s*\)",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        rf"\(\s*\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:,?\s*\d{{4}})?\s*\)",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        rf"(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s*\d{{4}})?",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})(?:,?\s*\d{{4}})?",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", text)
    if HAS_PREFIX:
        prefix_pat = re.escape(PREFIX)
        text = re.sub(r"\(reGROUP\s+(\w+)\)", r"\1", text, flags=re.I)
        text = re.sub(r"\.(\s+)(?=[A-Za-z])", r" -\1", text)
        text = re.sub(rf"\b{prefix_pat}\s+Church\b", "", text, flags=re.I)
        text = re.sub(rf"\b{prefix_pat}\s+Sermon\b", "", text, flags=re.I)
        text = re.sub(rf"\(\s*{prefix_pat}\s+[^)]+\)", "", text, flags=re.I)
        text = re.sub(rf"\(\s*{prefix_pat}\s*\)", "", text, flags=re.I)
        text = re.sub(rf"\b{prefix_pat}\b\s*[-–—]\s*", "", text, flags=re.I)
        text = re.sub(rf"^\s*{prefix_pat}\b\s*", "", text, flags=re.I)
        text = re.sub(rf"\s*\b{prefix_pat}\b\s*$", "", text, flags=re.I)
        text = re.sub(rf"\b{prefix_pat}\b", "", text, flags=re.I)
        text = re.sub(r"\s+we$", "", text, flags=re.I)
        text = re.sub(r"\bUndone\s+series\b", "Undone Series", text, flags=re.I)
        text = re.sub(r"\bUndone Series\s+(\w+)\b", r"Undone Series - \1", text, flags=re.I)
        text = re.sub(r":\s*Part\s+", " Part ", text, flags=re.I)
    text = re.sub(r"\s*[-–—]\s*[-–—]\s*", " - ", text)
    text = re.sub(r"^\s*[-–—.]\s*", "", text)
    text = re.sub(r"\s*[-–—]\s*$", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" -–—,.")

    wrapped = re.fullmatch(r"\((.+)\)", text)
    if wrapped:
        text = wrapped.group(1).strip()

    text = final_title_cleanup(text)
    text = sanitize_caps(text)
    return final_title_cleanup(text)


def pick_title(stem: str, heading: str | None, iso: str) -> str:
    if HAS_PREFIX and re.search(r"\(Singleness\s+2\)", stem, flags=re.I):
        return clean_title("Singleness 2", iso)

    from_stem = clean_title(stem, iso)
    from_heading = clean_title(heading, iso) if heading else ""

    if not from_stem:
        return from_heading
    if not from_heading:
        return from_stem

    if not HAS_PREFIX:
        if from_stem.endswith(" fo"):
            return from_heading
        return from_stem

    stem_truncated = from_stem.endswith(" fo") or len(from_stem) < 5
    heading_better = len(from_heading) > len(from_stem)
    heading_has_speaker = " - " in from_heading and " - " not in from_stem

    if stem_truncated or heading_better or heading_has_speaker:
        return from_heading
    return from_stem


def proposed_name(stem: str, iso: str, heading: str | None = None) -> str:
    cleaned = pick_title(stem, heading, iso)
    if HAS_PREFIX:
        if cleaned:
            return f"{iso} {PREFIX} - {cleaned}"
        return f"{iso} {PREFIX}"
    if cleaned:
        return f"{iso} - {cleaned}"
    return iso


def yaml_title(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    for line in text[3:end].splitlines():
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip()
    return None


def file_stem(path: Path, text: str) -> str:
    if not HAS_PREFIX and not re.match(r"^\d{4}-\d{2}-\d{2}(?:\s-\s|\s|$)", path.stem):
        title = yaml_title(text)
        if title:
            return title
    return path.stem


def iter_markdown_files() -> list[Path]:
    if RECURSIVE:
        return sorted(DIR.rglob("*.md"))
    return sorted(DIR.glob("*.md"))


def dest_path(src: Path, new_stem: str) -> Path:
    safe_stem = new_stem.replace("/", " and ")
    if FLATTEN:
        return DIR / f"{safe_stem}.md"
    return src.with_name(f"{safe_stem}.md")


def update_file_titles(path: Path) -> bool:
    new_title = path.stem
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    in_frontmatter = False
    changed = False
    heading_done = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if index == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if line.startswith("title:"):
                current = line.split(":", 1)[1].strip()
                if current != new_title:
                    lines[index] = f"title: {new_title}\n"
                    changed = True
            if stripped == "---":
                in_frontmatter = False
            continue
        if not heading_done and line.startswith("# ") and not line.startswith("## "):
            current = line[2:].strip()
            if current != new_title:
                lines[index] = f"# {new_title}\n"
                changed = True
            heading_done = True
            break

    if changed and not DRY_RUN:
        path.write_text("".join(lines), encoding="utf-8")
    return changed


def rename_files() -> int:
    files = iter_markdown_files()
    if not files:
        print(f"No .md files in {DIR}")
        return 0

    planned: list[tuple[Path, Path]] = []
    skipped: list[str] = []

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        created = parse_created(text)
        if not created:
            skipped.append(str(path.relative_to(DIR)))
            continue

        new_stem = proposed_name(file_stem(path, text), created, first_heading(text))
        dest = dest_path(path, new_stem)
        if path.resolve() == dest.resolve():
            continue
        planned.append((path, dest))

    targets = [dest.name for _, dest in planned]
    dupes = {name for name in targets if targets.count(name) > 1}
    if dupes:
        print("error: target filename collisions:", ", ".join(sorted(dupes)), file=sys.stderr)
        return 1

    mode = "dry-run" if DRY_RUN else "rename"
    print(f"Directory: {DIR}")
    print(f"Prefix:    {PREFIX if HAS_PREFIX else '(none)'}")
    print(f"Recursive: {RECURSIVE}")
    print(f"Flatten:   {FLATTEN}")
    print(f"Mode:      {mode}")
    print(f"Files:     {len(planned)} to rename, {len(skipped)} skipped\n")

    for src, dest in planned:
        rel = src.relative_to(DIR)
        print(f"{rel}")
        print(f"  -> {dest.name}")
        if not DRY_RUN:
            if dest.exists() and src.resolve() != dest.resolve():
                print(f"  skip (target exists): {dest.name}", file=sys.stderr)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)
            print("  ok")

    if skipped:
        print("\nSkipped (no | Created | date):", file=sys.stderr)
        for name in skipped:
            print(f"  {name}", file=sys.stderr)

    print("\nDone.")
    return 0


def update_titles() -> int:
    files = iter_markdown_files() if RECURSIVE else sorted(DIR.glob("*.md"))
    if not files:
        print(f"No .md files in {DIR}")
        return 0

    mode = "dry-run" if DRY_RUN else "update-titles"
    print(f"Directory: {DIR}")
    print(f"Prefix:    {PREFIX}")
    print(f"Mode:      {mode}")
    print(f"Files:     {len(files)}\n")

    updated = 0
    for path in files:
        if update_file_titles(path):
            print(f"update: {path.name}")
            print(f"  title/heading -> {path.stem}")
            updated += 1

    print(f"\nUpdated: {updated}")
    print("Done.")
    return 0


def main() -> int:
    if UPDATE_TITLES:
        return update_titles()
    return rename_files()


raise SystemExit(main())
PYEOF
