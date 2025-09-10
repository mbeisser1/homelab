#!/usr/bin/env python3
"""
trilium_import_rest.py
(Batch import per-group pages into Trilium with tidy hierarchy)

Given an --html-dir produced by the builder (one subfolder per group, with
<Group>.html and images/), create this hierarchy in Trilium:

<Notebook Title>         (under --parent)
└─ <Group>               (a container note per group)
   ├─ Pages/
   │   └─ <Group>.html   (text/html)
   └─ _images/
       ├─ <file notes>
       └─ ...

You can also import a single page with --html and --images-dir (previous mode).

Usage (batch):
  python trilium_import_rest.py \
    --server http://localhost:37840 \
    --api-key YOUR_API_KEY \
    --parent root \
    --notebook-title "My Export" \
    --html-dir /path/to/out

Usage (single page):
  python trilium_import_rest.py \
    --server http://localhost:37840 \
    --api-key YOUR_API_KEY \
    --parent root \
    --notebook-title "My Export" \
    --html /path/to/Group.html \
    --images-dir /path/to/Group/images

Notes:
- Requires: pip install requests
- Rewrites <img src="images/..."> to note://<attachmentId> after upload.
"""

import argparse, os, re
from pathlib import Path
from typing import Optional
import requests

IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc\s*=\s*["\'])([^"\']+)(["\'][^>]*>)', re.IGNORECASE)

def trilium_post(server: str, path: str, api_key: str, **kwargs):
    url = f"{server.rstrip('/')}{path}"
    headers = kwargs.pop("headers", {})
    headers["X-Api-Key"] = api_key
    r = requests.post(url, headers=headers, timeout=120, **kwargs)
    r.raise_for_status()
    return r

def trilium_put(server: str, path: str, api_key: str, **kwargs):
    url = f"{server.rstrip('/')}{path}"
    headers = kwargs.pop("headers", {})
    headers["X-Api-Key"] = api_key
    r = requests.put(url, headers=headers, timeout=120, **kwargs)
    r.raise_for_status()
    return r

def ensure_container(server, api_key, parent_id, title):
    resp = trilium_post(server, "/api/notes", api_key,
        json={"parentNoteId": parent_id, "title": title, "type": "text", "mime": "text/plain", "content": ""})
    data = resp.json(); return data.get("noteId") or data.get("id")

def create_html_note(server, api_key, parent_id, title, html):
    resp = trilium_post(server, "/api/notes", api_key,
        json={"parentNoteId": parent_id, "title": title, "type": "text", "mime": "text/html", "content": html})
    data = resp.json(); return data.get("noteId") or data.get("id")

def upload_attachment(server, api_key, parent_note_id, filename, data, mime: Optional[str]):
    resp = trilium_post(server, f"/api/notes/{parent_note_id}/attachments", api_key,
        files={"file": (filename, data, mime or "application/octet-stream")})
    info = resp.json(); return info.get("attachmentNoteId") or info.get("id") or info.get("noteId")

def guess_mime(path: Path) -> Optional[str]:
    import mimetypes
    mimetypes.add_type("image/webp", ".webp")
    mimetypes.add_type("image/svg+xml", ".svg")
    return mimetypes.guess_type(str(path))[0]

def rewrite_imgs_to_noteids(html: str, src_to_id: dict) -> str:
    repls = []
    for m in IMG_SRC_RE.finditer(html):
        src = m.group(2).strip()
        att_id = src_to_id.get(src) or src_to_id.get(src.lstrip("./"))
        if att_id:
            repls.append((m.span(), f"{m.group(1)}note://{att_id}{m.group(3)}"))
    if not repls: return html
    out = []; last = 0
    for (s,e), rep in sorted(repls, key=lambda x: x[0][0]):
        out.append(html[last:s]); out.append(rep); last = e
    out.append(html[last:])
    return "".join(out)

def import_single(server, api_key, notebook_id, group_title, html_path: Path, images_dir: Path):
    group_container = ensure_container(server, api_key, notebook_id, group_title)
    pages_id  = ensure_container(server, api_key, group_container, "Pages")
    images_id = ensure_container(server, api_key, group_container, "_images")

    html = html_path.read_text(encoding="utf-8", errors="replace")
    html_note_id = create_html_note(server, api_key, pages_id, html_path.stem, html)

    # upload images
    src_to_id = {}
    for p in images_dir.iterdir():
        if not p.is_file() or p.name.startswith("_rename_map"):
            continue
        data = p.read_bytes(); mime = guess_mime(p)
        att_id = upload_attachment(server, api_key, images_id, p.name, data, mime)
        src_to_id[f"images/{p.name}"] = att_id
        src_to_id[p.name] = att_id

    html2 = rewrite_imgs_to_noteids(html, src_to_id)
    if html2 != html:
        trilium_put(server, f"/api/notes/{html_note_id}", api_key,
            json={"type":"text", "mime":"text/html", "content": html2})
    return group_container, pages_id, images_id, html_note_id

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--parent", default="root")
    ap.add_argument("--notebook-title", required=True)
    ap.add_argument("--html-dir", help="Directory with per-group subfolders from builder")
    ap.add_argument("--html", help="Single page HTML path")
    ap.add_argument("--images-dir", help="Single page images directory")
    args = ap.parse_args()

    if not args.html_dir and not (args.html and args.images_dir):
        raise SystemExit("Provide either --html-dir (batch) OR --html + --images-dir (single).")

    # Create notebook container
    notebook_id = ensure_container(args.server, args.api_key, args.parent, args.notebook_title)

    if args.html_dir:
        root = Path(args.html_dir)
        for group_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
            # find <Group>.html in this dir
            html_files = [p for p in group_dir.glob("*.html")]
            if not html_files:
                continue
            html_path = html_files[0]
            images_dir = group_dir / "images"
            if not images_dir.exists():
                print(f"[!] Skipping {group_dir} (no images/ folder)")
                continue
            print(f"[*] Importing group: {group_dir.name}")
            import_single(args.server, args.api_key, notebook_id, group_dir.name, html_path, images_dir)
        print(f"[✓] Imported notebook: {args.notebook_title}")
    else:
        import_single(args.server, args.api_key, notebook_id,
                      Path(args.html).stem, Path(args.html), Path(args.images_dir))
        print(f"[✓] Imported single page under: {args.notebook_title}")

if __name__ == "__main__":
    main()
