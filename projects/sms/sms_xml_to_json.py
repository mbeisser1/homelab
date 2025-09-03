#!/usr/bin/env python3
"""
sms_xml_to_json.py

Convert SMS Backup XML to per-thread JSON files, ready for iOS-style HTML rendering later.

v1 scope:
- Parse <sms> messages now.
- Detect <mms> nodes and count them (skip content in v1).
- Group into 1:1 threads by counterpart phone.
- Skip only numbers that are NOT valid NANP after sanitization.
- Deduplicate consecutive identical messages (same direction) by body.
- Progress printed every N items (default 500).
- Write summary_report.json with counts.

Defaults are chosen to be EML-JSON compatible where reasonable:
- Addresses use "<E164>@unknown.email".
- message_id is a stable SHA-1 hash of ("xml" | direction | normalized_phone | timestamp_ms | body_stripped).

Usage:
  python sms_xml_to_json.py input.xml [--outdir OUTDIR] [--self-phone 9412660605] [--progress 500]
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import html
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from typing import Dict, Iterable, List, Optional, Tuple

# -----------------------------
# Constants / Helpers
# -----------------------------

DEFAULT_SELF_PHONE = "9412660605"
DEFAULT_PROGRESS_EVERY = 500

# max length for base filename before adding suffix/hash
MAX_FILENAME_LEN = 120

UNKNOWN_EMAIL_SUFFIX = "@unknown.email"


def debug(msg: str) -> None:
    print(msg, flush=True)


def now_utc_iso(ms: int) -> str:
    """Return UTC ISO-8601 with timezone offset +00:00 for an epoch milliseconds integer."""
    try:
        sec = ms / 1000.0
        ts = dt.datetime.fromtimestamp(sec, tz=dt.timezone.utc).replace(microsecond=0)
        return ts.isoformat()  # e.g., '2011-05-19T15:35:04+00:00'
    except Exception:
        # Fallback to epoch zero if input is malformed
        ts = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc).replace(microsecond=0)
        return ts.isoformat()


def sanitize_phone(raw: str) -> str:
    """Keep digits only. Drop leading '1' for NANP 11-digit. Return digits or empty if none."""
    if not raw:
        return ""
    digits = re.sub(r"\D+", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def is_valid_nanp_10(digits10: str) -> bool:
    """
    NANP validity (basic):
      - Exactly 10 digits
      - Area code and central office (exchange) cannot start with 0 or 1 (NXX)
    """
    if len(digits10) != 10:
        return False
    area = digits10[0]
    exchange = digits10[3]
    if area in "01" or exchange in "01":
        return False
    return True


def e164(digits10: str) -> str:
    return "+1" + digits10


def pretty_phone(digits10: str) -> str:
    """(407) 555-0123 style."""
    if len(digits10) != 10:
        return digits10
    return f"({digits10[0:3]}) {digits10[3:6]}-{digits10[6:]}"


def make_addr_from_phone(digits10: str) -> str:
    return f"{e164(digits10)}{UNKNOWN_EMAIL_SUFFIX}"


def safe_filename(s: str) -> str:
    # Replace path-separators and problematic chars
    s = re.sub(r"[\\/:*?\"<>|]+", "_", s).strip()
    # Collapse spaces
    s = re.sub(r"\s+", " ", s)
    return s or "unknown"


def enforce_max_filename(
    base: str, suffix: str, max_len: int = MAX_FILENAME_LEN
) -> str:
    """
    Ensure base + suffix fits within max_len by truncating base and appending a short hash.
    """
    combined = base + suffix
    if len(combined) <= max_len:
        return combined
    h = hashlib.sha1(combined.encode("utf-8")).hexdigest()[:10]
    keep = max_len - len(suffix) - len(h) - 1  # 1 for underscore
    trimmed_base = (base[:keep]).rstrip()
    return f"{trimmed_base}_{h}{suffix}"


def stable_message_id(
    source: str, direction: str, norm_phone: str, ts_ms: int, body: str
) -> str:
    """
    Create a stable ID across runs for XML-derived messages.
    """
    body_norm = " ".join(html.unescape(body or "").split())
    parts = [source, direction, norm_phone, str(ts_ms), body_norm]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def detect_schema(root: ET.Element) -> str:
    """
    Return 'smses' or 'allsms' for known schemas; otherwise fallback to root.tag.
    """
    tag = root.tag.lower()
    if tag.endswith("smses"):
        return "smses"
    if tag.endswith("allsms"):
        return "allsms"
    return tag


def get_contact_name(attrs: Dict[str, str], schema: str) -> Optional[str]:
    if schema == "allsms":
        # Attached schema uses 'name'
        return attrs.get("name") or None
    # SMS Backup & Restore uses 'contact_name'
    return attrs.get("contact_name") or None


def get_type_direction(attrs: Dict[str, str]) -> Optional[str]:
    """
    Map 'type' attribute to 'in' or 'out'
      - 1 => in (received)
      - 2 => out (sent)
    Return None if not mapped.
    """
    t = attrs.get("type")
    if t == "1":
        return "in"
    if t == "2":
        return "out"
    return None


# -----------------------------
# Core processing
# -----------------------------


class Counters:
    def __init__(self) -> None:
        self.sms_parsed_total = 0
        self.mms_found_total = 0
        self.mms_skipped_total = 0
        self.improper_numbers_skipped_total = 0
        self.messages_deduped_total = 0
        self.total_items_seen = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "sms_parsed_total": self.sms_parsed_total,
            "mms_found_total": self.mms_found_total,
            "mms_skipped_total": self.mms_skipped_total,
            "improper_numbers_skipped_total": self.improper_numbers_skipped_total,
            "messages_deduped_total": self.messages_deduped_total,
            "total_items_seen": self.total_items_seen,
        }


def process_sms_xml(
    xml_path: str,
    outdir: str,
    self_phone_digits: str,
    progress_every: int = DEFAULT_PROGRESS_EVERY,
) -> Dict[str, object]:
    """
    Parse the XML incrementally and write per-thread JSONs.
    Returns a summary dictionary.
    """
    counters = Counters()
    threads: Dict[str, Dict[str, object]] = collections.defaultdict(
        lambda: {
            "thread_key": "",
            "thread_label": "",
            "person_name": None,
            "person_address": None,
            "self_address": None,
            "message_count": 0,
            "participants": [],
            "messages": [],
        }
    )

    # Pre-computed self fields
    self_digits10 = sanitize_phone(self_phone_digits)
    if len(self_digits10) != 10:
        raise ValueError(
            f"--self-phone must sanitize to 10 digits; got: {self_digits10!r}"
        )
    self_addr = make_addr_from_phone(self_digits10)
    self_label = "Me"

    context = ET.iterparse(xml_path, events=("start", "end"))
    _, root = next(context)  # get root element to detect schema
    schema = detect_schema(root)

    for event, elem in context:
        if event != "end":
            continue

        tag = elem.tag.lower()
        if tag.endswith("sms"):
            counters.total_items_seen += 1
            attrs = elem.attrib

            direction = get_type_direction(attrs)
            if direction is None:
                elem.clear()
                continue

            # Counterpart phone is in 'address'
            raw_addr = attrs.get("address", "")
            other_digits = sanitize_phone(raw_addr)

            # Skip improper numbers only if they are not valid NANP after sanitization
            if not is_valid_nanp_10(other_digits):
                counters.improper_numbers_skipped_total += 1
                elem.clear()
                if counters.total_items_seen % progress_every == 0:
                    debug(f"[progress] processed {counters.total_items_seen} items ...")
                continue

            # Pull name (if any) from per-schema attribute
            contact_name = get_contact_name(attrs, schema)

            # Build thread key based on counterpart
            thread_key = other_digits
            thread_label = contact_name or pretty_phone(other_digits)
            person_name = contact_name
            person_address = make_addr_from_phone(other_digits)

            # Acquire message fields
            try:
                ts_ms = int(attrs.get("date", "0"))
            except ValueError:
                ts_ms = 0
            ts_iso = now_utc_iso(ts_ms)
            body_raw = attrs.get("body", "") or ""
            body_txt = html.unescape(body_raw).strip()

            # Build sender object
            if direction == "in":
                sender = {
                    "name": person_name,
                    "addr": person_address,
                    "phone": other_digits,
                    "is_self": False,
                    "label": person_name or pretty_phone(other_digits),
                }
            else:
                sender = {
                    "name": self_label,
                    "addr": self_addr,
                    "phone": self_digits10,
                    "is_self": True,
                    "label": self_label,
                }

            # Build message_id (stable)
            msg_id = stable_message_id(
                source="xml",
                direction=direction,
                norm_phone=other_digits,
                ts_ms=ts_ms,
                body=body_txt,
            )

            # Initialize / update thread bucket
            th = threads[thread_key]
            if not th["thread_key"]:
                th["thread_key"] = thread_key
                th["thread_label"] = thread_label
                th["person_name"] = person_name
                th["person_address"] = person_address
                th["self_address"] = self_addr
                th["participants"] = [
                    {
                        "name": person_name,
                        "addr": person_address,
                        "phone": other_digits,
                    }
                ]
                th["messages"] = []

            th["messages"].append(
                {
                    "message_id": msg_id,
                    "direction": direction,
                    "timestamp_ms": ts_ms,
                    "timestamp_iso": ts_iso,
                    "body": body_txt,
                    "sender": sender,
                    "attachments": [],  # SMS v1: empty; MMS v2 will populate
                }
            )

            counters.sms_parsed_total += 1

            # progress
            if counters.total_items_seen % progress_every == 0:
                debug(f"[progress] processed {counters.total_items_seen} items ...")

            # Clear element to free memory
            elem.clear()

            # Prevent memory leak in iterparse by clearing parent sometimes
            # while elem.getprevious() is not None:
            #     try:
            #         parent = elem.getparent()  # only exists if using lxml
            #         if parent is not None:
            #             parent.remove(elem)
            #     except AttributeError:
            #         # stdlib ElementTree has no .getparent(), so just skip
            #         pass

        elif tag.endswith("mms"):
            counters.total_items_seen += 1
            counters.mms_found_total += 1
            counters.mms_skipped_total += 1  # v1 skips content

            if counters.total_items_seen % progress_every == 0:
                debug(f"[progress] processed {counters.total_items_seen} items ...")

            elem.clear()

        # (ignore other tags and attributes)
        # clear non-root occasionally
        if elem is not root:
            elem.clear()

    # Post-process threads: sort, dedup consecutive duplicates, counts, write files
    os.makedirs(outdir, exist_ok=True)

    threads_written = 0
    for tkey, th in threads.items():
        # Sort
        msgs = th["messages"]
        msgs.sort(key=lambda m: (m["timestamp_ms"], m["direction"], m["body"]))

        # Dedup consecutive same-direction identical bodies
        deduped: List[dict] = []
        last_body = None
        last_dir = None
        for m in msgs:
            bnorm = " ".join((m.get("body") or "").split())
            if deduped and last_dir == m["direction"] and last_body == bnorm:
                counters.messages_deduped_total += 1
                continue
            deduped.append(m)
            last_dir = m["direction"]
            last_body = bnorm

        th["messages"] = deduped
        th["message_count"] = len(deduped)

        # Filename: prefer contact name; fallback to pretty phone; then append _combined.json
        base_name = th["thread_label"] or pretty_phone(tkey)
        base_name = safe_filename(base_name)
        # Ensure uniqueness across similarly named contacts by appending phone digits
        base_name_unique = f"{base_name}_{tkey}"
        final_name = enforce_max_filename(
            base_name_unique, "_combined.json", MAX_FILENAME_LEN
        )

        out_path = os.path.join(outdir, final_name)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(th, f, ensure_ascii=False, indent=2)

        threads_written += 1

    # summary report
    summary = counters.to_dict()
    summary.update(
        {
            "threads_written_total": threads_written,
            "output_dir": os.path.abspath(outdir),
        }
    )
    with open(os.path.join(outdir, "summary_report.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # final console summary
    debug("\n--- Summary ---")
    for k, v in summary.items():
        debug(f"{k}: {v}")

    return summary


def compute_default_outdir(script_name: str) -> str:
    base = os.path.splitext(os.path.basename(script_name))[0]
    ts = dt.datetime.now().strftime("%y%m%d_%H%M%S")
    return f"{base}_{ts}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert SMS Backup XML to per-thread JSON."
    )
    parser.add_argument("xml_path", help="Path to SMS backup .xml file")
    parser.add_argument(
        "--outdir", help="Output directory (default: <script_name>_YYMMDD_HHMMSS)"
    )
    parser.add_argument(
        "--self-phone",
        default=DEFAULT_SELF_PHONE,
        help="Your own phone number (digits, any format). Default: %(default)s",
    )
    parser.add_argument(
        "--progress",
        type=int,
        default=DEFAULT_PROGRESS_EVERY,
        help="Print progress every N items. Default: %(default)s",
    )
    args = parser.parse_args(argv)

    xml_path = args.xml_path
    if not os.path.isfile(xml_path):
        print(f"ERROR: input file not found: {xml_path}", file=sys.stderr)
        return 2

    outdir = args.outdir or compute_default_outdir(__file__)
    try:
        summary = process_sms_xml(
            xml_path=xml_path,
            outdir=outdir,
            self_phone_digits=args.self_phone,
            progress_every=args.progress,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
