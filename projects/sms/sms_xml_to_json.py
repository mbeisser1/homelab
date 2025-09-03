#!/usr/bin/env python3
"""
sms_xml_to_json.py (latest)

Convert SMS Backup XML to per-thread JSON files, ready for iOS-style HTML rendering later.

Features:
- Parse <sms> messages now (skip <mms>, just count them).
- Group into 1:1 threads by counterpart phone.
- Skip numbers not valid NANP after sanitization.
- Deduplicate adjacent identical messages (same direction).
- Progress printed every N items (default 500).
- Write summary_report.json with counts.
- Supports optional --contacts CSV mapping numbers to names (Google Contacts export or simple CSV).

Defaults:
- --self-phone defaults to 9412660605 (override allowed).
- --progress defaults to 500 (override allowed).
"""

import argparse
import collections
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

DEFAULT_SELF_PHONE = "9412660605"
DEFAULT_PROGRESS_EVERY = 500
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
        ts = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc).replace(microsecond=0)
        return ts.isoformat()


def sanitize_phone(raw: str) -> str:
    if not raw:
        return ""
    digits = re.sub(r"\D+", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def is_valid_nanp_10(digits10: str) -> bool:
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
    if len(digits10) != 10:
        return digits10
    return f"({digits10[0:3]}) {digits10[3:6]}-{digits10[6:]}"


def make_addr_from_phone(digits10: str) -> str:
    return f"{e164(digits10)}{UNKNOWN_EMAIL_SUFFIX}"


def safe_filename(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|]+", "_", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s or "unknown"


def enforce_max_filename(
    base: str, suffix: str, max_len: int = MAX_FILENAME_LEN
) -> str:
    combined = base + suffix
    if len(combined) <= max_len:
        return combined
    h = hashlib.sha1(combined.encode("utf-8")).hexdigest()[:10]
    keep = max_len - len(suffix) - len(h) - 1
    trimmed_base = (base[:keep]).rstrip()
    return f"{trimmed_base}_{h}{suffix}"


def stable_message_id(
    source: str, direction: str, norm_phone: str, ts_ms: int, body: str
) -> str:
    body_norm = " ".join(html.unescape(body or "").split())
    parts = [source, direction, norm_phone, str(ts_ms), body_norm]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def strip_signature(text: str) -> str:
    return text


def normalize_text_for_compare(text: str) -> str:
    t = unicodedata.normalize("NFC", text or "")
    t = " ".join(t.split()).strip()
    return t.casefold()


def detect_schema(root: ET.Element) -> str:
    tag = root.tag.lower()
    if tag.endswith("smses"):
        return "smses"
    if tag.endswith("allsms"):
        return "allsms"
    return tag


def get_contact_name(attrs: Dict[str, str], schema: str) -> Optional[str]:
    if schema == "allsms":
        return attrs.get("name") or None
    return attrs.get("contact_name") or None


def get_type_direction(attrs: Dict[str, str]) -> Optional[str]:
    t = attrs.get("type")
    if t == "1":
        return "in"
    if t == "2":
        return "out"
    return None


def load_contacts(csv_path: str) -> dict:
    mapping = {}
    if not csv_path:
        return mapping

    def build_name(row: dict) -> str:
        first = (row.get("First Name") or "").strip()
        middle = (row.get("Middle Name") or "").strip()
        last = (row.get("Last Name") or "").strip()
        parts = [p for p in [first, middle, last] if p]
        name = " ".join(parts).strip()
        if not name:
            for k in ("File As", "Nickname", "Name", "Full Name"):
                v = (row.get(k) or "").strip()
                if v:
                    name = v
                    break
        return name

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = [h or "" for h in (reader.fieldnames or [])]
            lower = {h.strip().lower(): h for h in headers}
            simple_name = lower.get("name")
            simple_phone = lower.get("phone") or lower.get("phones")
            phone_value_cols = [
                h for h in headers if re.search(r"^phone\s*\d+\s*-\s*value$", h, re.I)
            ]
            generic_phone_cols = [
                h
                for h in headers
                if ("phone" in h.lower())
                and ("label" not in h.lower())
                and h not in phone_value_cols
            ]

            for row in reader:
                name = ""
                if simple_name:
                    name = (row.get(simple_name) or "").strip()
                if not name:
                    name = build_name(row)
                raw_phones = []
                if simple_phone:
                    raw = row.get(simple_phone) or ""
                    if raw:
                        raw_phones.extend(re.split(r"[\s,;]+", raw))
                for col in phone_value_cols + generic_phone_cols:
                    val = (row.get(col) or "").strip()
                    if val:
                        raw_phones.append(val)
                for ph in raw_phones:
                    d = sanitize_phone(ph)
                    if len(d) == 10 and is_valid_nanp_10(d):
                        if d not in mapping or (name and not mapping[d]):
                            mapping[d] = name
        return mapping
    except Exception as e:
        debug(f"WARNING: Failed to load contacts CSV '{csv_path}': {e}")
        return {}


class Counters:
    def __init__(self) -> None:
        self.sms_parsed_total = 0
        self.mms_found_total = 0
        self.mms_skipped_total = 0
        self.improper_numbers_skipped_total = 0
        self.messages_deduped_total = 0
        self.total_items_seen = 0
        self.contacts_loaded = 0
        self.names_resolved_via_csv = 0
        self.names_present_in_xml = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "sms_parsed_total": self.sms_parsed_total,
            "mms_found_total": self.mms_found_total,
            "mms_skipped_total": self.mms_skipped_total,
            "improper_numbers_skipped_total": self.improper_numbers_skipped_total,
            "messages_deduped_total": self.messages_deduped_total,
            "total_items_seen": self.total_items_seen,
            "contacts_loaded": self.contacts_loaded,
            "names_resolved_via_csv": self.names_resolved_via_csv,
            "names_present_in_xml": self.names_present_in_xml,
        }


def process_sms_xml(
    xml_path: str,
    outdir: str,
    self_phone_digits: str,
    progress_every: int = DEFAULT_PROGRESS_EVERY,
    contacts_map: dict | None = None,
) -> Dict[str, object]:
    counters = Counters()
    contacts_map = contacts_map or {}
    try:
        counters.contacts_loaded = len(contacts_map)
    except Exception:
        counters.contacts_loaded = 0

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

    self_digits10 = sanitize_phone(self_phone_digits)
    if len(self_digits10) != 10:
        raise ValueError(
            f"--self-phone must sanitize to 10 digits; got: {self_digits10!r}"
        )
    self_addr = make_addr_from_phone(self_digits10)
    self_label = "Me"

    context = ET.iterparse(xml_path, events=("start", "end"))
    _, root = next(context)
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
            raw_addr = attrs.get("address", "")
            other_digits = sanitize_phone(raw_addr)
            if not is_valid_nanp_10(other_digits):
                counters.improper_numbers_skipped_total += 1
                elem.clear()
                if counters.total_items_seen % progress_every == 0:
                    debug(f"[progress] processed {counters.total_items_seen} items ...")
                continue
            contact_name = get_contact_name(attrs, schema)
            if contact_name:
                counters.names_present_in_xml += 1
            if not contact_name:
                contact_name = contacts_map.get(other_digits) or None
                if contact_name:
                    counters.names_resolved_via_csv += 1
            thread_key = other_digits
            thread_label = contact_name or pretty_phone(other_digits)
            person_name = contact_name
            person_address = make_addr_from_phone(other_digits)
            try:
                ts_ms = int(attrs.get("date", "0"))
            except ValueError:
                ts_ms = 0
            ts_iso = now_utc_iso(ts_ms)
            body_raw = attrs.get("body", "") or ""
            body_txt = html.unescape(body_raw)
            body_txt = strip_signature(body_txt)
            body_txt = unicodedata.normalize("NFC", body_txt).strip()
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
            msg_id = stable_message_id("xml", direction, other_digits, ts_ms, body_txt)
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
                    "attachments": [],
                }
            )
            counters.sms_parsed_total += 1
            if counters.total_items_seen % progress_every == 0:
                debug(f"[progress] processed {counters.total_items_seen} items ...")
            elem.clear()
        elif tag.endswith("mms"):
            counters.total_items_seen += 1
            counters.mms_found_total += 1
            counters.mms_skipped_total += 1
            if counters.total_items_seen % progress_every == 0:
                debug(f"[progress] processed {counters.total_items_seen} items ...")
            elem.clear()
        if elem is not root:
            elem.clear()

    os.makedirs(outdir, exist_ok=True)
    threads_written = 0
    for tkey, th in threads.items():
        msgs = th["messages"]
        msgs.sort(key=lambda m: (m["timestamp_ms"], m["direction"], m["body"]))
        deduped = []
        for m in msgs:
            norm_body = normalize_text_for_compare(m.get("body") or "")
            if deduped:
                prev = deduped[-1]
                prev_norm = normalize_text_for_compare(prev.get("body") or "")
                if (
                    prev.get("direction") == m.get("direction")
                    and prev_norm == norm_body
                ):
                    counters.messages_deduped_total += 1
                    continue
            deduped.append(m)
        th["messages"] = deduped
        th["message_count"] = len(deduped)
        base_name = th["thread_label"] or pretty_phone(tkey)
        base_name = safe_filename(base_name)
        base_name_unique = f"{base_name}_{tkey}"
        final_name = enforce_max_filename(
            base_name_unique, "_combined.json", MAX_FILENAME_LEN
        )
        out_path = os.path.join(outdir, final_name)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(th, f, ensure_ascii=False, indent=2)
        threads_written += 1

    summary = counters.to_dict()
    summary.update(
        {
            "threads_written_total": threads_written,
            "output_dir": os.path.abspath(outdir),
        }
    )
    with open(os.path.join(outdir, "summary_report.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
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
        "--contacts", help="Optional contacts CSV to map phone numbers to names"
    )
    parser.add_argument(
        "--outdir", help="Output directory (default: <script_name>_YYMMDD_HHMMSS)"
    )
    parser.add_argument(
        "--self-phone",
        default=DEFAULT_SELF_PHONE,
        help="Your own phone number. Default: %(default)s",
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
    contacts_map = {}
    if getattr(args, "contacts", None):
        contacts_map = load_contacts(args.contacts)
    try:
        process_sms_xml(xml_path, outdir, args.self_phone, args.progress, contacts_map)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
