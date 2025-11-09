#!/usr/bin/env python3
"""
Import a folder of HTML files (plus their local assets) into Trilium note-by-note
via ETAPI.  Each HTML becomes a child of the specified parent note.

Usage:
  python import_html_etapi.py  -d /path/html_tree  -p <parentNoteId>  -t <ETAPI_TOKEN>

Requirements:
  pip install requests tqdm
"""

import argparse
import json
import mimetypes
import re
import sys
from pathlib import Path
from typing import Dict, Set

import requests
from tqdm import tqdm

STATE_FILE = ".etapi_import_state.json"
URL_BASE: str = ""  # filled from CLI
TOKEN: str = (
    "y6XSlfaPSsA9_CDIvMIJvSBsxA/iq/rJLYYtBeC9lviM1swpSs4Q2n+E="  # filled from CLI
)
PARENT_ID: str = "FSUwxFRcIkPV"  # filled from CLI
SESSION = requests.Session()


# ---------- helpers -----------------------------------------------------------
def api(path: str, **kw):
    """Convenience wrapper for ETAPI calls."""
    resp = SESSION.request(
        method=kw.pop("method", "GET"),
        url=f"{URL_BASE}/etapi{path}",
        headers={"Authorization": TOKEN},
        timeout=60,
        **kw,
    )
    resp.raise_for_status()
    return resp


def load_state() -> Set[str]:
    return (
        set(json.loads(Path(STATE_FILE).read_text()))
        if Path(STATE_FILE).exists()
        else set()
    )


def save_state(done: Set[str]):
    Path(STATE_FILE).write_text(json.dumps(list(done)))


def collect_local_assets(html_path: Path, root: Path) -> Dict[str, Path]:
    """Return dict  relative_path → absolute_path  for every local asset."""
    assets: Dict[str, Path] = {}
    content = html_path.read_text(encoding="utf-8", errors="ignore")
    for match in re.finditer(
        r"""(?:src|href)\s*=\s*["'](.*?)["']""", content, flags=re.I
    ):
        raw = match.group(1).replace("\\", "/")
        if raw.startswith(("http://", "https://", "data:", "#")):
            continue
        abs_path = (html_path.parent / raw).resolve()
        try:
            rel = abs_path.relative_to(root)
        except ValueError:
            continue
        if abs_path.is_file():
            assets[str(rel)] = abs_path
    return assets


def upload_note(title: str, content: str) -> str:
    """Create note under PARENT_ID; return noteId."""
    body = {
        "parentNoteId": PARENT_ID,
        "title": title,
        "type": "text",
        "content": content,
    }
    note = api("/notes", method="POST", json=body).json()
    return note["note"]["noteId"]


def upload_attachment(note_id: str, file_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(file_path))
    with file_path.open("rb") as fh:
        att = api(
            f"/notes/{note_id}/attachments",
            method="POST",
            files={"upload": (file_path.name, fh, mime or "application/octet-stream")},
        ).json()
    return att["attachmentId"]


def update_note_body(note_id: str, new_body: str):
    api(f"/notes/{note_id}/content", method="PUT", data=new_body.encode("utf-8"))


def rewrite_html(body: str, mapping: Dict[str, str]) -> str:
    """Replace local urls by api/attachments/{id}/filename ."""
    for rel_path, att_id in mapping.items():
        file_name = Path(rel_path).name
        body = re.sub(
            rf"""(["'])([^"']*{re.escape(rel_path)})\\1""",
            rf"\1api/attachments/{att_id}/{file_name}\1",
            body,
        )
    return body


# ---------- main ------------------------------------------------------------
def main():
    global URL_BASE, PARENT_ID, TOKEN
    ap = argparse.ArgumentParser(description="Import HTML tree into Trilium via ETAPI")
    ap.add_argument("-d", "--dir", required=True, type=Path, help="root of html tree")
    ap.add_argument(
        "-p",
        "--parent",
        default=PARENT_ID,
        help="noteId of parent under which to import",
    )
    ap.add_argument("-t", "--token", default=TOKEN, help="ETAPI token")
    ap.add_argument(
        "-u", "--url", default="http://127.0.0.1:8180", help="Trilium base URL"
    )
    args = ap.parse_args()

    URL_BASE = args.url.rstrip("/")
    TOKEN = args.token
    PARENT_ID = args.parent
    root: Path = args.dir.expanduser().resolve()

    done = load_state()
    html_files = sorted(p for p in root.rglob("*.html") if str(p) not in done)

    if not html_files:
        print("Nothing to do.")
        return

    for html_path in tqdm(html_files, desc="Importing"):
        title = html_path.stem
        body = html_path.read_text(encoding="utf-8", errors="ignore")
        assets = collect_local_assets(html_path, root)

        note_id = upload_note(title, body)  # initial empty body also fine
        mapping: Dict[str, str] = {}
        for rel, abs_path in assets.items():
            att_id = upload_attachment(note_id, abs_path)
            mapping[rel] = att_id

        if mapping:
            body = rewrite_html(body, mapping)
            update_note_body(note_id, body)

        done.add(str(html_path))
        save_state(done)
        print("MJb: breaking early")
        break

    print("All done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAborted by user")
