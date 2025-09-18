#!/usr/bin/env python3
"""
trilium_html_rewriter.py

Rewrite HTML files so that media links (img/video/audio/source/track/script/link/a, etc.)
point to an external NAS path (file:// or http(s)), while keeping the HTML body importable
into Trilium. This allows Trilium to store only the HTML, with large media staying outside.

USAGE (common):
  python3 trilium_html_rewriter.py \
    --input-root /path/to/archive_in \
    --output-root /path/to/trilium_ready_out \
    --nas-root /pool/archive/mms \
    --scheme file \
    --verbose

  # If you ever decide to serve read-only via HTTPS instead:
  python3 trilium_html_rewriter.py \
    --input-root /path/to/archive_in \
    --output-root /path/to/trilium_ready_out \
    --url-base https://nas.local/archive/mms \
    --scheme https

KEY IDEAS
- We do NOT touch your originals. We write a mirrored directory tree under --output-root.
- We compute each rewritten URL by taking the file path resolved against --nas-root
  (for 'file' scheme), or against --url-base (for http/https).
- Only HTML files are rewritten; other files are copied if --copy-nonhtml is set (default: skip).
- "Relative" URLs are rewritten; absolute URLs with a scheme (http:, https:, file:, data:, mailto:, tel:, javascript:) remain untouched.
- We also rewrite root-absolute paths starting with '/' by joining them to --root-absolute-base
  if provided, otherwise we treat them as project-relative to --nas-root.

LIMITATIONS
- This is a conservative rewriter using regular expressions; it preserves attribute quoting and
  unknown attributes. It won't execute JS or parse inline scripts for dynamic URLs.
- It handles 'srcset' by rewriting each URL token individually.

Author: ChatGPT
License: MIT
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

# ----------------------------
# Utilities
# ----------------------------

URL_ATTRS = {"src", "href", "poster", "data-src", "data-href", "data-thumb", "content"}
# Tag-specific attributes we care about (subset; we still match generically)
SRCSET_ATTRS = {"srcset"}
TAGS_OF_INTEREST = {
    "img",
    "source",
    "track",
    "video",
    "audio",
    "script",
    "link",
    "a",
    "iframe",
    "embed",
    "object",
    "meta",
}

# Schemes we will NOT modify
SAFE_SCHEMES = {"http", "https", "file", "data", "mailto", "tel", "javascript"}

# Basic HTML attribute regex: captures name="value" or name='value'
ATTR_RE = re.compile(
    r"""(?P<name>[a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    flags=re.DOTALL,
)

# Simple tag opener regex to process tag-by-tag (we avoid full DOM libs to stay stdlib-only)
TAG_RE = re.compile(
    r"""<(?P<end>/)?(?P<tag>[a-zA-Z][a-zA-Z0-9:_-]*)(?P<attrs>(?:\s+[^\s<>/][^<>]*)*)\s*(?P<self>/)?>""",
    flags=re.DOTALL,
)


def is_absolute_url(u: str) -> bool:
    p = urlparse(u)
    return bool(p.scheme)


def is_root_absolute(u: str) -> bool:
    # Treat URLs starting with "/" as root-absolute (no scheme).
    return u.startswith("/") and not is_absolute_url(u)


def needs_rewrite(u: str) -> bool:
    if not u:
        return False
    if is_absolute_url(u):
        scheme = urlparse(u).scheme.lower()
        return (
            scheme not in SAFE_SCHEMES
        )  # Unlikely, but allow custom rewrite if weird scheme
    # relative or root-absolute
    return True


def norm_join_file_url(base_fs_root: Path, rel_path_from_input_root: Path) -> str:
    # Join filesystem path and convert to file:// URI
    fs_target = (base_fs_root / rel_path_from_input_root).resolve()
    return fs_target.as_uri()


def join_http_url(base_url: str, rel_url: str) -> str:
    # Ensure single slash joining without double // issues (after scheme://host)
    if not base_url.endswith("/"):
        base_url += "/"
    # We want to percent-encode unsafe characters in rel_url path segments
    # without touching '/'.
    parts = rel_url.split("/")
    enc_parts = [quote(p, safe=":@&=+$,;~*'()[]") for p in parts]
    return base_url + "/".join(enc_parts)


def rewrite_single_url(
    value: str,
    input_root: Path,
    current_html: Path,
    nas_root: Path | None,
    scheme: str,
    url_base: str | None,
    root_absolute_base: str | None,
) -> str:
    # Leave absolute + safe schemes untouched
    if is_absolute_url(value):
        scheme0 = urlparse(value).scheme.lower()
        if scheme0 in SAFE_SCHEMES:
            return value
        # else fall-through and treat as relative (rare)

    # For srcset, the caller splits values; this handles single URLs only.
    # Resolve 'value' relative to current HTML file's directory in the INPUT tree
    # to compute a relative path from INPUT ROOT.
    v = value

    # Root-absolute path like "/foo/bar.png"
    if is_root_absolute(v):
        rel_from_input_root = v.lstrip("/")
    else:
        # Relative path: resolve against HTML file dir, then make it relative to input_root
        abs_guess = (current_html.parent / v).resolve()
        try:
            rel_from_input_root = abs_guess.relative_to(input_root.resolve())
        except ValueError:
            # If file lies outside input root (odd), fall back to the raw value but normalized
            rel_from_input_root = Path(v)

    # Emit new URL based on scheme
    if scheme == "file":
        if nas_root is None:
            raise ValueError("--nas-root is required when --scheme=file")
        return norm_join_file_url(nas_root.resolve(), rel_from_input_root)
    elif scheme in ("http", "https"):
        if not url_base:
            raise ValueError("--url-base is required when --scheme=http/https")
        return join_http_url(
            url_base.rstrip("/"), str(rel_from_input_root).replace("\\", "/")
        )
    else:
        # Unexpected scheme; leave unchanged
        return value


def rewrite_srcset(value: str, **kwargs) -> str:
    """Rewrite each URL in a srcset attribute.
    Example: "img1.jpg 1x, img2.jpg 2x" -> "file:///.../img1.jpg 1x, file:///.../img2.jpg 2x"
    """
    parts = [p.strip() for p in value.split(",")]
    out_parts = []
    for p in parts:
        if not p:
            continue
        # split on whitespace; first token is URL, rest are descriptors
        tokens = p.split()
        if not tokens:
            continue
        url_tok = tokens[0]
        rest = " ".join(tokens[1:])
        new_url = rewrite_single_url(url_tok, **kwargs)
        out_parts.append((new_url + (" " + rest if rest else "")))
    return ", ".join(out_parts)


def process_tag(
    tag_match: re.Match,
    input_root: Path,
    current_html: Path,
    nas_root: Path | None,
    scheme: str,
    url_base: str | None,
    root_absolute_base: str | None,
    stats: dict,
) -> str:
    """Return rewritten tag text."""
    is_end = bool(tag_match.group("end"))
    tag = (tag_match.group("tag") or "").lower()
    attrs_txt = tag_match.group("attrs") or ""
    selfclose = bool(tag_match.group("self"))

    if is_end or not attrs_txt:
        return tag_match.group(0)  # unchanged

    # Only process tags of interest (otherwise fast path)
    if tag not in TAGS_OF_INTEREST:
        return tag_match.group(0)

    last_end = 0
    new_attrs_txt = ""

    for m in ATTR_RE.finditer(attrs_txt):
        name = m.group("name").lower()
        quote_ch = m.group("quote")
        val = m.group("value")

        # Write preceding text unchanged
        new_attrs_txt += attrs_txt[last_end : m.start()]

        # Handle srcset separately
        if name in SRCSET_ATTRS:
            new_val = rewrite_srcset(
                val,
                input_root=input_root,
                current_html=current_html,
                nas_root=nas_root,
                scheme=scheme,
                url_base=url_base,
                root_absolute_base=root_absolute_base,
            )
            if new_val != val:
                stats["rewritten"] += 1
            new_attrs_txt += f"{name}={quote_ch}{new_val}{quote_ch}"
        elif (name in URL_ATTRS) or (
            name.startswith("data-") and ("src" in name or "href" in name)
        ):
            if needs_rewrite(val):
                new_val = rewrite_single_url(
                    val,
                    input_root=input_root,
                    current_html=current_html,
                    nas_root=nas_root,
                    scheme=scheme,
                    url_base=url_base,
                    root_absolute_base=root_absolute_base,
                )
                if new_val != val:
                    stats["rewritten"] += 1
                new_attrs_txt += f"{name}={quote_ch}{new_val}{quote_ch}"
            else:
                new_attrs_txt += m.group(0)
        else:
            new_attrs_txt += m.group(0)

        last_end = m.end()

    new_attrs_txt += attrs_txt[last_end:]

    # Rebuild the tag with possibly updated attrs
    start = "</" if is_end else "<"
    end = " />" if selfclose else ">"
    return f"{start}{tag}{new_attrs_txt}{end}"


def rewrite_html_file(
    src_html: Path,
    dst_html: Path,
    input_root: Path,
    nas_root: Path | None,
    scheme: str,
    url_base: str | None,
    root_absolute_base: str | None,
    dry_run: bool,
    stats_global: dict,
) -> None:
    text = src_html.read_text(encoding="utf-8", errors="ignore")
    stats_local = {"rewritten": 0}

    def repl(m: re.Match) -> str:
        return process_tag(
            m,
            input_root=input_root,
            current_html=src_html,
            nas_root=nas_root,
            scheme=scheme,
            url_base=url_base,
            root_absolute_base=root_absolute_base,
            stats=stats_local,
        )

    new_text = TAG_RE.sub(repl, text)

    if not dry_run:
        dst_html.parent.mkdir(parents=True, exist_ok=True)
        dst_html.write_text(new_text, encoding="utf-8")

    stats_global["files"] += 1
    stats_global["links"] += stats_local["rewritten"]


def main():
    ap = argparse.ArgumentParser(
        description="Rewrite HTML links for Trilium hybrid import."
    )
    ap.add_argument(
        "--input-root",
        type=Path,
        required=True,
        help="Directory containing original HTML export.",
    )
    ap.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Directory to write rewritten HTML (mirror tree).",
    )
    ap.add_argument(
        "--nas-root",
        type=Path,
        help="Filesystem root where media will live (e.g., /pool/archive/mms). Required for --scheme=file.",
    )
    ap.add_argument(
        "--scheme",
        choices=["file", "http", "https"],
        default="file",
        help="How to form rewritten URLs.",
    )
    ap.add_argument(
        "--url-base",
        type=str,
        help="Base URL (e.g., https://nas.local/archive/mms) for http/https scheme.",
    )
    ap.add_argument(
        "--root-absolute-base",
        type=str,
        default=None,
        help="Optional base for root-absolute paths ('/foo'). If omitted, root-absolute is treated as project-relative to --nas-root or --url-base.",
    )
    ap.add_argument(
        "--copy-nonhtml",
        action="store_true",
        help="Also copy non-HTML files to output mirror (default: skip).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and print stats without writing files.",
    )
    ap.add_argument("--verbose", "-v", action="store_true", help="Verbose logging.")
    args = ap.parse_args()

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()

    if not input_root.exists():
        print(f"[ERROR] --input-root not found: {input_root}", file=sys.stderr)
        sys.exit(2)

    if args.scheme == "file" and not args.nas_root:
        print("[ERROR] --nas-root is required when --scheme=file", file=sys.stderr)
        sys.exit(2)
    if args.scheme in ("http", "https") and not args.url_base:
        print(
            "[ERROR] --url-base is required when --scheme=http/https", file=sys.stderr
        )
        sys.exit(2)

    stats = {"files": 0, "links": 0, "copied": 0, "skipped": 0}

    for src in input_root.rglob("*"):
        try:
            rel = src.relative_to(input_root)
        except Exception:
            continue

        dst = output_root / rel

        if src.is_dir():
            # create dirs lazily when writing files
            continue

        suffix = src.suffix.lower()
        if suffix in (".html", ".htm"):
            if args.verbose:
                print(f"[HTML] rewrite: {src} -> {dst}")
            rewrite_html_file(
                src_html=src,
                dst_html=dst,
                input_root=input_root,
                nas_root=args.nas_root,
                scheme=args.scheme,
                url_base=args.url_base,
                root_absolute_base=args.root_absolute_base,
                dry_run=args.dry_run,
                stats_global=stats,
            )
        else:
            if args.copy_nonhtml:
                if not args.dry_run:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                stats["copied"] += 1
                if args.verbose:
                    print(f"[COPY] {src} -> {dst}")
            else:
                stats["skipped"] += 1
                if args.verbose:
                    print(f"[SKIP] {src}")

    print(
        f"[DONE] Files processed: {stats['files']}, links rewritten: {stats['links']}, "
        f"non-HTML copied: {stats['copied']}, skipped: {stats['skipped']}"
    )


if __name__ == "__main__":
    main()
