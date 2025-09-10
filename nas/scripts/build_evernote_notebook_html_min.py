#!/usr/bin/env python3
"""
build_evernote_notebook_html_min.py
(Per-person/topic grouping; Created date only; robust image renaming; dividers)

Create **one minimal HTML page per group** (person/topic) from an Evernote export
ZIP (or already-extracted folder). Each group gets its own folder:

out/
  <GroupA>/
    <GroupA>.html
    images/
      <sanitized files...>
  <GroupB>/
    <GroupB>.html
    images/
      ...

Also writes out/index.html that lists all groups and links to their pages.

Grouping options (pick one):
  --group-by regex:<PATTERN>    # regex applied to filename stem; use first capture group if no (?P<name>)
  --group-by parentdir          # use the note file's parent directory name
  --group-by notebookmeta       # try <meta name="notebook" content="...">, else filename fallback
If omitted, a heuristic filename-based prefix is used (before ' - ' or '_' or first token).

Usage:
  python build_evernote_notebook_html_min.py \
    --zip /path/to/evernote.zip \
    --out /path/to/out \
    --title "My Export" \
    [--group-by regex:^(?P<g>[^_]+)_] \
    [--strip-css] [--max-filename-len 80] [--divider hr|rule|none]

Or (extracted):
  python build_evernote_notebook_html_min.py \
    --src-dir /path/to/extracted \
    --out /path/to/out \
    --title "My Export"

Notes:
- Leaves sources alone; copies images to each group's images/ folder with sanitized names.
- Rewrites <img src="..."> inside each group page.
- Dates: shows **Created** only (best-effort from meta/time/file timestamp). No Updated.
"""

import argparse, base64, os, re, sys, zipfile, shutil, unicodedata, hashlib
from pathlib import Path
from html import escape, unescape
from datetime import datetime

IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc\s*=\s*["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)
DATA_URI_RE = re.compile(r'^data:(?P<mime>[-\w.+/]+)?(?:;charset=[^;,"]+)?;base64,(?P<b64>[A-Za-z0-9+/=\s]+)\s*$', re.IGNORECASE)
META_CREATED_RE = re.compile(r'<meta[^>]+name=["\']created["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)
TIME_TAG_RE     = re.compile(r'<time[^>]+datetime=["\']([^"\']+)["\']', re.IGNORECASE)
TEXT_CREATED_RE = re.compile(r'(?:^|>|\s)(?:Created|Creation Date)\s*:\s*([^<\n]+)', re.IGNORECASE)
META_NOTEBOOK_RE= re.compile(r'<meta[^>]+name=["\']notebook["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)

ALLOWED_CHARS_RE = re.compile(r'[^A-Za-z0-9._-]')
MULTI_UNDERSCORES_RE = re.compile(r'_{2,}')

def sanitize_filename(name: str, max_len: int = 80) -> str:
    base, ext = os.path.splitext(name)
    base = unicodedata.normalize("NFKC", base).replace(" ", "_")
    base = ALLOWED_CHARS_RE.sub("_", base)
    base = MULTI_UNDERSCORES_RE.sub("_", base).strip("_") or "file"
    ext = (ext or "").lower()[:16]
    max_base = max(8, max_len - len(ext))
    out_base, suffix = base, ""
    if len(base) > max_base:
        h = hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:8]
        keep = max(1, max_base - (1 + len(h)))
        out_base = base[:keep]; suffix = "-" + h
    return f"{out_base}{suffix}{ext}"

def sanitize_group(name: str) -> str:
    # More generous for folder & page names
    s = unicodedata.normalize("NFKC", name).strip()
    s = s.replace("/", "-").replace("\\", "-")
    s = re.sub(r'\s+', ' ', s)
    s = s.strip(" .")
    return s or "Group"

def uniquify(target: Path, filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    candidate = filename; i = 1
    while (target / candidate).exists():
        candidate = f"{stem}-{i}{ext}"; i += 1
    return candidate

def is_remote_url(s: str) -> bool:
    s = s.strip().lower()
    return s.startswith("http://") or s.startswith("https://")

def extract_zip_to_temp(zip_path: Path, temp_dir: Path) -> Path:
    temp_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(temp_dir)
    return temp_dir

def find_html_files(root: Path):
    for p in sorted(root.rglob("*.html")):
        yield p

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def strip_evernote_boilerplate(html: str) -> str:
    html = re.sub(r'<style\b[^>]*>.*?</style>', '', html, flags=re.IGNORECASE|re.DOTALL)
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    html = re.sub(r'<div[^>]*class=["\']?en-note["\']?[^>]*>(.*?)</div>', r'\1', html, flags=re.IGNORECASE|re.DOTALL)
    return html

def format_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")

def try_parse_created(s: str) -> str:
    if not s: return ""
    s = s.strip()
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(:\d{2})?', s)
    if m: return f"{m.group(1)} {m.group(2)}"
    m = re.match(r'^([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})\s+(\d{1,2}:\d{2}\s*[AP]M)', s, re.IGNORECASE)
    if m:
        try:
            dt = datetime.strptime(s, "%B %d, %Y %I:%M %p")
            return format_dt(dt)
        except Exception: pass
    return s

def extract_created(html: str, html_path: Path) -> str:
    created = ""
    m = META_CREATED_RE.search(html)
    if m: created = try_parse_created(m.group(1))
    if not created:
        m = TIME_TAG_RE.search(html)
        if m: created = try_parse_created(m.group(1))
    if not created:
        m = TEXT_CREATED_RE.search(html)
        if m: created = try_parse_created(m.group(1))
    if not created:
        try:
            st = html_path.stat()
            created = format_dt(datetime.fromtimestamp(st.st_ctime))
        except Exception: pass
    return created

def minimal_wrap(title: str, body_html: str, strip_css: bool) -> str:
    css = "" if strip_css else """
    <style>
      html,body{margin:0;padding:0;background:#fff;color:#111;font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,sans-serif}
      main{max-width:900px;margin:2rem auto;padding:0 1rem 4rem}
      h1{font-size:1.6rem;margin:1rem 0 1.5rem}
      h2{font-size:1.25rem;margin:2rem 0 .75rem;border-bottom:1px solid #eee;padding-bottom:.25rem}
      img,video{max-width:100%;height:auto}
      article{margin:1.25rem 0 1.75rem}
      .note-title{margin:.2rem 0 .3rem;font-weight:600}
      .meta{color:#666;font-size:.9rem;margin:.2rem 0 1rem}
      hr.rule{border:none;border-top:1px solid #eee;margin:2rem 0}
      .toc a{display:block;margin:.2rem 0;text-decoration:none;color:#06c}
    </style>
    """
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
{css}
<main>
  <h1>{escape(title)}</h1>
  {body_html}
</main>
</html>"""

def choose_group(html_path: Path, html: str, group_by: str|None) -> str:
    stem = html_path.stem
    if group_by:
        if group_by.startswith("regex:"):
            pat = group_by[6:]
            m = re.search(pat, stem)
            if m:
                g = m.groupdict().get("g") or (m.group(1) if m.groups() else None)
                if g: return sanitize_group(g)
        elif group_by == "parentdir":
            return sanitize_group(html_path.parent.name)
        elif group_by == "notebookmeta":
            m = META_NOTEBOOK_RE.search(html)
            if m:
                return sanitize_group(m.group(1))
    # Heuristic: prefix before ' - ' else '_' else first token
    if " - " in stem:
        return sanitize_group(stem.split(" - ", 1)[0])
    if "_" in stem:
        return sanitize_group(stem.split("_", 1)[0])
    return sanitize_group(stem.split()[0] if " " in stem else stem)

def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--zip", help="Path to Evernote export ZIP")
    src.add_argument("--src-dir", help="Path to already-extracted folder")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--title", required=True, help="Top-level title (for index only)")
    ap.add_argument("--group-by", help="regex:<PATTERN> | parentdir | notebookmeta", default=None)
    ap.add_argument("--strip-css", action="store_true")
    ap.add_argument("--max-filename-len", type=int, default=80)
    ap.add_argument("--divider", choices=["hr","rule","none"], default="rule")
    args = ap.parse_args()

    out_root = Path(args.out); out_root.mkdir(parents=True, exist_ok=True)
    temp_dir = None
    if args.zip:
        temp_dir = out_root / "_temp_extract"
        if temp_dir.exists(): shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        extract_zip_to_temp(Path(args.zip), temp_dir)
        root = temp_dir
    else:
        root = Path(args.src_dir)

    # Collect notes by group
    groups = {}  # group_name -> list of (html_path, body_html, created)
    images_maps = {}  # group_name -> {source_path: sanitized_name}
    imgs_counters = {}  # group_name -> counter for embedded data URIs

    for html_path in find_html_files(root):
        html = read_text(html_path)
        body = strip_evernote_boilerplate(html)
        group = choose_group(html_path, html, args.group_by)
        created = extract_created(html, html_path)
        groups.setdefault(group, [])
        groups[group].append((html_path, body, created))

    if not groups:
        print("No HTML files found."); return

    # Build each group folder
    for group, items in groups.items():
        group_dir = out_root / sanitize_filename(group, 120).rsplit(".",1)[0]
        group_dir.mkdir(parents=True, exist_ok=True)
        images_out = group_dir / "images"; images_out.mkdir(exist_ok=True)
        rename_map = {}
        img_counter = 0
        pieces = []

        for html_path, body, created in items:
            # Rewrite <img src> to sanitized copies inside this group's images/
            replacements = []
            for m in IMG_SRC_RE.finditer(body):
                original = unescape(m.group(2).strip())
                if is_remote_url(original):
                    continue
                # data: URI -> file
                dm = DATA_URI_RE.match(original)
                if dm:
                    img_counter += 1
                    b64 = dm.group("b64").replace("\n","").replace("\r","").replace(" ","")
                    try:
                        raw = base64.b64decode(b64, validate=True)
                    except Exception:
                        continue
                    mime = (dm.group("mime") or "").lower()
                    ext = {
                        "image/png": ".png","image/jpeg": ".jpg","image/jpg": ".jpg",
                        "image/gif": ".gif","image/webp": ".webp","image/svg+xml": ".svg",
                    }.get(mime, ".bin")
                    fname = uniquify(images_out, f"embedded_{img_counter}{ext}")
                    (images_out / fname).write_bytes(raw)
                    new_tag = f"{m.group(1)}images/{fname}{m.group(3)}"
                    replacements.append((m.span(), new_tag))
                    continue
                # local file path relative to html
                candidate = (html_path.parent / original).resolve()
                if candidate.is_file():
                    new_name = rename_map.get(str(candidate))
                    if not new_name:
                        new_name = sanitize_filename(candidate.name, max_len=args.max_filename_len)
                        new_name = uniquify(images_out, new_name)
                        shutil.copy2(candidate, images_out / new_name)
                        rename_map[str(candidate)] = new_name
                    new_tag = f"{m.group(1)}images/{new_name}{m.group(3)}"
                    replacements.append((m.span(), new_tag))

            if replacements:
                buf = []; last = 0
                for (start, end), repl in sorted(replacements, key=lambda x: x[0][0]):
                    buf.append(body[last:start]); buf.append(repl); last = end
                buf.append(body[last:]); body = "".join(buf)

            meta_html = f'<div class="meta">Created: {escape(created)}</div>' if created else ""
            note_title = html_path.stem
            pieces.append(f'<article>\n  <h2 class="note-title">{escape(note_title)}</h2>\n  {meta_html}\n  {body}\n</article>')

        # Divider
        if args.divider == "hr": div = "<hr/>"
        elif args.divider == "rule": div = '<hr class="rule"/>'
        else: div = ""

        merged_html = f"\n{div}\n".join(pieces) if pieces else "<p>No notes in this group.</p>"
        final_html = minimal_wrap(group, merged_html, strip_css=args.strip_css)
        out_html = group_dir / f"{sanitize_filename(group, 120).rsplit('.',1)[0]}.html"
        out_html.write_text(final_html, encoding="utf-8")
        (images_out / "_rename_map.json").write_text(
            __import__("json").dumps(rename_map, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[✓] Wrote group page: {out_html}")

    # Write a tiny index listing groups
    links = []
    for group in sorted(groups.keys()):
        gdir = sanitize_filename(group, 120).rsplit(".",1)[0]
        links.append(f'<li><a href="{gdir}/{gdir}.html">{escape(group)}</a></li>')
    index = f"<!doctype html><meta charset='utf-8'><title>{escape(args.title)}</title><ul class='toc'>{''.join(links)}</ul>"
    (out_root / "index.html").write_text(index, encoding="utf-8")
    if temp_dir and temp_dir.exists(): shutil.rmtree(temp_dir)
    print(f"[✓] Index: {out_root / 'index.html'}")

if __name__ == "__main__":
    main()
