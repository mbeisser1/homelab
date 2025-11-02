#!/usr/bin/env python3
import argparse
import zipfile
import tempfile
import shutil
import re
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime
from html import escape

# -------- helpers --------

def strip_suffix_for_person(stem: str) -> str:
    return re.sub(r"-\d+-.*$", "", stem).strip()

def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return s or "note"

# ---- parsing and cleaning ----

def _remove_duplicate_title(body, title_text: str):
    for h in body.find_all(["h1", "h2"]):
        if h.get_text(strip=True) == title_text:
            h.decompose()
            break

def _strip_evernote_meta_blocks(body):
    """Remove Evernote's metadata boxes (Created/Updated/Author/Tags) near the top."""
    to_remove = []
    for i, el in enumerate(body.find_all(True, recursive=True)):
        if i > 30:
            break
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue
        low = txt.lower()
        if ("created:" in low and "updated:" in low) or "author:" in low or "tags:" in low:
            to_remove.append(el)
    for el in to_remove:
        try:
            el.decompose()
        except Exception:
            pass

def _plain_text(html_fragment: str) -> str:
    return BeautifulSoup(html_fragment or "", "html.parser").get_text(" ", strip=True)

def parse_note_html(path: Path, image_out: Path):
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else path.stem

    # Extract Created/Updated (strings only)
    full_text = soup.get_text("\n")
    m = re.search(r"Created:\s*([^\n\r•]+)", full_text, flags=re.I)
    created_str = m.group(1).strip() if m else None
    # We intentionally ignore "Updated:" to keep output minimal (per request).

    def parse_dt(s):
        if not s: return None
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue
        return None

    created_dt = parse_dt(created_str)

    body = soup.body or soup

    _remove_duplicate_title(body, title)
    _strip_evernote_meta_blocks(body)

    # Remove stray "Author:" / "Tags:" mentions
    for t in body.find_all(string=re.compile(r"\b(Author|Tags):", re.I)):
        try:
            t.extract()
        except Exception:
            pass

    # Normalize <img> sources; copy local images to a shared /images directory
    for img in body.find_all("img"):
        src = img.get("src", "")
        if not src or src.startswith("http"):
            continue
        src_path = (path.parent / src)
        if src_path.is_file():
            image_out.mkdir(parents=True, exist_ok=True)
            dest = image_out / src_path.name
            if not dest.exists():
                shutil.copy2(src_path, dest)
            img["src"] = f"images/{dest.name}"

    body_html = str(body)
    text_for_check = _plain_text(body_html)
    text_for_check = re.sub(r"\bCreated:\s*[^\s].*$", "", text_for_check, flags=re.I).strip()

    if not text_for_check:
        return None

    return {
        "title": title,
        "created_str": created_str,
        "created_dt": created_dt,
        "body_html": body_html,
    }

# -------- page builders (minimal styling) --------

MIN_CSS = """
/* Minimal, readable defaults */
html,body{margin:0;padding:0;background:#fff;color:#111;font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
main{max-width:900px;margin:2rem auto;padding:0 1rem 3rem}
h1{font-size:1.6rem;margin:0 0 1.25rem}
h2{font-size:1.2rem;margin:2rem 0 .75rem;border-bottom:1px solid #eee;padding-bottom:.25rem}
img,video{max-width:100%;height:auto}
.note{margin:1rem 0 1.5rem}
.meta{color:#555;font-size:.9rem;margin:.25rem 0 1rem}
hr{border:none;border-top:1px solid #eee;margin:2rem 0}
.toc{margin:0 0 1.25rem}
.toc h3{margin:.5rem 0 .25rem;font-size:1rem}
.toc ul{margin:.25rem 0;padding-left:1.25rem}
.toc a{text-decoration:none;color:#06c}
.toc a:hover{text-decoration:underline}
"""

def build_notebook_html(name: str, notes: list[dict], outdir: Path) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") + ".html"

    toc_items, sections = [], []
    for idx, n in enumerate(notes, start=1):
        anchor = f"{slugify(n['title'])}-{idx}"
        toc_items.append(f"<li><a href='#{anchor}'>{escape(n['title'])}</a></li>")
        created_html = f"<div class='meta'>Created: {escape(n['created_str'])}</div>" if n['created_str'] else ""
        sections.append(f"""
<section class="note" id="{anchor}">
  <h2>{escape(n['title'])}</h2>
  {created_html}
  {n['body_html']}
</section>
""")

    html = f"""<!doctype html>
<meta charset="utf-8">
<title>{escape(name)}</title>
<style>{MIN_CSS}</style>
<main>
  <h1>{escape(name)}</h1>
  <div class="toc">
    <h3>Contents</h3>
    <ul>
      {''.join(toc_items)}
    </ul>
  </div>
  {('<hr/>'.join(sections)) if sections else ''}
</main>
"""
    (outdir / safe).write_text(html, encoding="utf-8")
    return safe

def build_index_html(normal_pages, everfriend_pages, outdir: Path):
    # Minimal, no sidebar/iframe; just two lists.
    items1 = "\n".join(f"<li><a href='{fname}'>{escape(name)}</a></li>" for name, fname in normal_pages)
    items2 = "\n".join(f"<li><a href='{fname}'>{escape(person)}</a></li>" for person, fname in everfriend_pages)
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>Notebook Index</title>
<style>{MIN_CSS}</style>
<main>
  <h1>Notebook Index</h1>
  <section class="toc">
    <h3>Notebooks</h3>
    <ul>
      {items1}
    </ul>
  </section>
  <section class="toc">
    <h3>EverFriend</h3>
    <ul>
      {items2}
    </ul>
  </section>
</main>
"""
    (outdir / "index.html").write_text(html, encoding="utf-8")

# -------- main --------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, help="Evernote export zip")
    parser.add_argument("--out", required=True, help="Output directory")
    args = parser.parse_args()

    outdir = Path(args.out)
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    images_out = outdir / "images"

    tmpdir = Path(tempfile.mkdtemp(prefix="evernote_"))
    with zipfile.ZipFile(args.zip, "r") as z:
        z.extractall(tmpdir)

    root_dirs = [p for p in tmpdir.iterdir() if p.is_dir()]
    root = root_dirs[0] if root_dirs else tmpdir

    other_groups, everfriends = {}, {}
    for f in root.rglob("*.html"):
        if not f.is_file():
            continue
        rel = f.relative_to(root)
        top = rel.parts[0].lower() if rel.parts else ""
        if top == "everfriend":
            person = strip_suffix_for_person(f.stem)
            everfriends.setdefault(person, []).append(f)
        else:
            m = re.match(r"([^-]+)", f.stem)
            group = m.group(1).strip() if m else f.stem
            other_groups.setdefault(group, []).append(f)

    normal_pages, everfriend_pages = [], []

    for group in sorted(other_groups.keys(), key=lambda s: s.lower()):
        notes = []
        for f in sorted(other_groups[group], key=lambda p: p.name.lower()):
            n = parse_note_html(f, images_out)
            if n:
                notes.append(n)
        notes.sort(key=lambda n: (n["created_dt"] or datetime.min, n["title"].lower()))
        if notes:
            fname = build_notebook_html(group, notes, outdir)
            normal_pages.append((group, fname))

    for person in sorted(everfriends.keys(), key=lambda s: s.lower()):
        notes = []
        for f in sorted(everfriends[person], key=lambda p: p.name.lower()):
            n = parse_note_html(f, images_out)
            if n:
                notes.append(n)
        notes.sort(key=lambda n: (n["created_dt"] or datetime.min, n["title"].lower()))
        if notes:
            fname = build_notebook_html(person, notes, outdir)
            everfriend_pages.append((person, fname))

    build_index_html(normal_pages, everfriend_pages, outdir)

    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"✅ Done. Open {outdir/'index.html'}")

if __name__ == "__main__":
    main()
