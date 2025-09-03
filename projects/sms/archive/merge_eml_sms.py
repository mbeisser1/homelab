#!/usr/bin/env python3
"""
merge_sms_eml.py

Combine multiple SMS/MMS .eml files per person into:
  1) A single combined EML per person (attaching each original .eml in chronological order as message/rfc822)
  2) A JSON file per person with messages in chronological order, including text, timestamps, and base64-embedded attachments/images

Designed for SMS Backup/Sync / SMS Backup+ style exports.
Tested with headers like:
  - X-smssync-address
  - X-smssync-type (1=incoming, 2=outgoing)
  - X-smssync-date (ms since epoch)
  - Date

Usage:
  python merge_sms_eml.py INPUTS... [-o OUTDIR] [--self-email SELF ...]

Examples:
  python merge_sms_eml.py "/path/to/*.eml" -o out
  python merge_sms_eml.py "SMS with Akil Meade.eml" "SMS with Akil Meade1.eml" -o out --self-email mjbeisser@gmail.com

Notes:
- "Person" is inferred as the *other* party (non-self) via headers.
- If your own address is ambiguous, pass --self-email to help determine direction/person.
"""

import argparse
import base64
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

# -------------------------- Helpers & Types --------------------------


@dataclass
class Attachment:
    filename: str
    content_type: str
    data_b64: str


@dataclass
class ParsedMessage:
    raw_bytes: bytes
    msg_id: Optional[str]
    direction: str  # "in" or "out"
    person_name: Optional[str]
    person_addr: Optional[str]
    self_addr: Optional[str]
    timestamp_ms: int
    timestamp_iso: str
    body_text: str
    attachments: List[Attachment] = field(default_factory=list)


def guess_direction_and_parties(
    msg, self_emails: List[str]
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Return (direction, person_name, person_addr, self_addr).
    direction: "in" if message is from other -> self, else "out".
    """
    # Prefer SMS backup headers when present
    # X-smssync-type: 1 = incoming, 2 = outgoing (convention from SMS Backup+)
    smstype = msg.get("X-smssync-type")
    to_addrs = getaddresses(msg.get_all("To", []))
    from_addrs = getaddresses(msg.get_all("From", []))

    # Normalize self_emails for quick checks
    se = set(e.lower() for e in self_emails if e)

    # Helper to pick a "main" address
    def first_addr(addrs):
        if not addrs:
            return (None, None)
        name, addr = addrs[0]
        addr = (addr or "").strip()
        name = (name or "").strip() or None
        return (name, addr)

    from_name, from_addr = first_addr(from_addrs)
    to_name, to_addr = first_addr(to_addrs)

    # If SMS header declares direction, use it
    if smstype:
        smstype = smstype.strip()
        if smstype == "1":  # incoming to self
            direction = "in"
            # From is person, To is self (likely)
            person_name, person_addr = from_name, from_addr
            self_addr = to_addr
            return direction, person_name, person_addr, self_addr
        elif smstype == "2":  # outgoing from self
            direction = "out"
            # To is person, From is self (likely)
            person_name, person_addr = to_name, to_addr
            self_addr = from_addr
            return direction, person_name, person_addr, self_addr

    # Otherwise infer via self email list (or heuristics)
    # If From is self -> outgoing
    if from_addr and from_addr.lower() in se:
        return "out", to_name, to_addr, from_addr
    # If To is self -> incoming
    if to_addr and to_addr.lower() in se:
        return "in", from_name, from_addr, to_addr

    # Fallback: if there's X-smssync-address, that's likely the person
    person_addr = msg.get("X-smssync-address")
    if person_addr:
        # Heuristic: if From contains person addr, then incoming; else outgoing
        if from_addr and person_addr in from_addr:
            return "in", from_name or None, person_addr, to_addr
        elif to_addr and person_addr in to_addr:
            return "out", to_name or None, person_addr, from_addr

    # Last resort: assume "person" = the non-gmail-looking address
    # and "self" = a gmail/known address
    candidates = [(from_name, from_addr), (to_name, to_addr)]
    gmailish = [
        c
        for c in candidates
        if c[1] and ("@gmail." in c[1].lower() or c[1].lower() in se)
    ]
    others = [c for c in candidates if c[1] and c not in gmailish]
    if gmailish and others:
        # If from is other -> incoming, else outgoing
        if from_addr and any(from_addr == g[1] for g in gmailish):
            # from is self -> outgoing
            return "out", (others[0][0] or None), others[0][1], from_addr
        else:
            # from is other -> incoming
            return "in", (others[0][0] or None), others[0][1], gmailish[0][1]

    # Give up: mark unknown direction, put person as non-self (if we can tell)
    return "out", to_name or from_name, to_addr or from_addr, None


def get_timestamp_ms(msg) -> int:
    # Prefer X-smssync-date (ms)
    xms = msg.get("X-smssync-date")
    if xms:
        try:
            return int(xms.strip())
        except Exception:
            pass
    # Fallback to Date
    dt = None
    date_hdr = msg.get("Date")
    if date_hdr:
        try:
            dt = parsedate_to_datetime(date_hdr)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = None
    if dt is None:
        return 0
    return int(dt.timestamp() * 1000)


def iso_from_ms(ms: int) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return ""


def decode_text(msg) -> str:
    """
    Extract best-effort plain text from the email.
    Priority:
      - text/plain part
      - text/html (stripped of tags)
      - simple payload if not multipart
    """

    def html_to_text(html: str) -> str:
        # naive strip of tags/decoding entities; good enough for SMS bodies
        text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", "", html)
        text = re.sub(r"(?s)<br\\s*/?>", "\\n", text)
        text = re.sub(r"(?s)</p\\s*>", "\\n", text)
        text = re.sub(r"(?s)<.*?>", "", text)
        return re.sub(r"&nbsp;", " ", text)

    if msg.is_multipart():
        # search for text/plain first
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    payload = part.get_payload(decode=True) or b""
                    return payload.decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    ).strip()
                except Exception:
                    continue
        # then text/html
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/html":
                try:
                    payload = part.get_payload(decode=True) or b""
                    html = payload.decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                    return html_to_text(html).strip()
                except Exception:
                    continue
        return ""
    else:
        payload = msg.get_payload(decode=True) or b""
        if payload:
            ctype = msg.get_content_type()
            if ctype == "text/html":
                return html_to_text(
                    payload.decode(
                        msg.get_content_charset() or "utf-8", errors="replace"
                    )
                ).strip()
            else:
                return payload.decode(
                    msg.get_content_charset() or "utf-8", errors="replace"
                ).strip()
        return ""


def extract_attachments(msg) -> List[Attachment]:
    atts: List[Attachment] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        cdisp = (part.get("Content-Disposition") or "").lower()
        ctype = (part.get_content_type() or "").lower()
        if "attachment" in cdisp or ctype.startswith("image/"):
            filename = part.get_filename()
            if not filename:
                # derive a simple name from content type
                ext = ctype.split("/")[-1] if "/" in ctype else "bin"
                filename = f"attachment.{ext}"
            try:
                data = part.get_payload(decode=True) or b""
                atts.append(
                    Attachment(
                        filename=filename,
                        content_type=ctype,
                        data_b64=base64.b64encode(data).decode("ascii"),
                    )
                )
            except Exception:
                continue
    return atts


def parse_eml_file(path: str, self_emails: List[str]) -> ParsedMessage:
    with open(path, "rb") as f:
        raw = f.read()
    msg = BytesParser(policy=policy.default).parsebytes(raw)

    direction, person_name, person_addr, self_addr = guess_direction_and_parties(
        msg, self_emails
    )
    t_ms = get_timestamp_ms(msg)
    body = decode_text(msg)
    atts = extract_attachments(msg)
    msg_id = msg.get("Message-ID")

    # If no person name, try to infer from headers with the person_addr
    if not person_name and person_addr:
        all_names = getaddresses(msg.get_all("To", []) + msg.get_all("From", []))
        for nm, ad in all_names:
            if ad == person_addr and nm:
                person_name = nm.strip() or None
                break

    return ParsedMessage(
        raw_bytes=raw,
        msg_id=msg_id,
        direction=direction,
        person_name=person_name,
        person_addr=person_addr,
        self_addr=self_addr,
        timestamp_ms=t_ms,
        timestamp_iso=iso_from_ms(t_ms),
        body_text=body,
        attachments=atts,
    )


def person_key_from(pm: ParsedMessage) -> str:
    # Prefer explicit address if available, else fall back to name
    if pm.person_addr:
        return pm.person_addr
    if pm.person_name:
        return pm.person_name
    # Really last resort, include direction+timestamp hash-ish
    return f"unknown_{pm.direction}_{pm.timestamp_ms}"


def safe_filename(s: str) -> str:
    s = s or "unknown"
    s = re.sub(r"[^A-Za-z0-9._@+-]+", "_", s).strip("_")
    return s or "unknown"


# -------------------------- Core Routine --------------------------


def combine_for_person(person_key: str, messages: List[ParsedMessage], outdir: str):
    # Sort chronologically (ascending)
    messages.sort(key=lambda m: (m.timestamp_ms, m.msg_id or ""))

    # Derive a nice display name/address
    names = [m.person_name for m in messages if m.person_name]
    addrs = [m.person_addr for m in messages if m.person_addr]
    self_addrs = [m.self_addr for m in messages if m.self_addr]

    name = None
    if names:
        # most common
        name = Counter(names).most_common(1)[0][0]
    addr = addrs[0] if addrs else None
    self_addr = self_addrs[0] if self_addrs else None

    # ---------- Write combined EML (attach originals as message/rfc822) ----------
    combined = EmailMessage()
    subj_name = name or addr or person_key
    combined["Subject"] = f"Combined SMS with {subj_name} ({len(messages)} messages)"
    combined["From"] = self_addr or "me@local"
    combined["To"] = (
        f"{subj_name} <{addr or person_key}>"
        if addr or name
        else subj_name or "unknown"
    )

    combined.set_content(
        f"Combined {len(messages)} messages in chronological order.\n"
        f"Person: {subj_name}\n"
        f"Key: {person_key}\n"
    )

    for idx, pm in enumerate(messages, 1):
        # Attach original .eml bytes as message/rfc822
        combined.add_attachment(
            pm.raw_bytes,
            maintype="message",
            subtype="rfc822",
            filename=f"{idx:04d}_{safe_filename(pm.msg_id or 'message')}.eml",
        )

    eml_name = f"{safe_filename(subj_name)}_combined.eml"
    eml_path = os.path.join(outdir, eml_name)
    with open(eml_path, "wb") as f:
        f.write(combined.as_bytes())

    # ---------- Write JSON with messages & embedded attachments ----------
    json_obj: Dict[str, Any] = {
        "person_key": person_key,
        "person_name": name,
        "person_address": addr,
        "self_address": self_addr,
        "message_count": len(messages),
        "messages": [],
    }

    for pm in messages:
        json_obj["messages"].append(
            {
                "message_id": pm.msg_id,
                "direction": pm.direction,
                "timestamp_ms": pm.timestamp_ms,
                "timestamp_iso": pm.timestamp_iso,
                "body": pm.body_text,
                "attachments": [att.__dict__ for att in pm.attachments],
            }
        )

    json_name = f"{safe_filename(subj_name)}_combined.json"
    json_path = os.path.join(outdir, json_name)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_obj, f, ensure_ascii=False, indent=2)

    return eml_path, json_path


def main():
    ap = argparse.ArgumentParser(
        description="Combine SMS/MMS .eml files per person into combined .eml and JSON (attachments embedded)."
    )
    ap.add_argument("inputs", nargs="+", help="Input .eml files or globs")
    ap.add_argument(
        "-o",
        "--outdir",
        default=None,
        help="Output directory (default: ./combined_eml_out_YYYYmmdd_HHMMSS)",
    )
    ap.add_argument(
        "--self-email",
        action="append",
        default=[
            "mjbeisser@gmail.com",
            "beissemj@gmail.com",
            "mbeisser@fastmail.com",
            "mbeisser_archive@fastmail.com",
            "9412660605",
        ],
        help="Specify your own email address(es) to help infer direction/person. Defaults include your known addresses/phone.",
    )
    args = ap.parse_args()

    # Expand globs
    paths: List[str] = []
    for p in args.inputs:
        paths.extend(glob.glob(p))
    paths = [p for p in paths if os.path.isfile(p) and p.lower().endswith(".eml")]
    if not paths:
        print("No .eml files found from inputs.", file=sys.stderr)
        sys.exit(2)

    # Prepare outdir
    if args.outdir:
        outdir = args.outdir
    else:
        ts = datetime.now().strftime("%y%m%d_%H%M%S")
        outdir = f"combine_eml_sms_{ts}"
    os.makedirs(outdir, exist_ok=True)

    # Parse messages and group per person
    groups: Dict[str, List[ParsedMessage]] = defaultdict(list)
    for path in paths:
        try:
            pm = parse_eml_file(path, args.self_email)
            key = person_key_from(pm)
            groups[key].append(pm)
        except Exception as e:
            print(f"[WARN] Failed to parse {path}: {e}", file=sys.stderr)

    # Combine each person
    summary = []
    for person_key, msgs in groups.items():
        eml_path, json_path = combine_for_person(person_key, msgs, outdir)
        summary.append((person_key, eml_path, json_path))

    # Emit a simple report
    print("Wrote:")
    for person_key, eml_path, json_path in summary:
        print(f"  - {person_key}:")
        print(f"      EML : {eml_path}")
        print(f"      JSON: {json_path}")


if __name__ == "__main__":
    main()
