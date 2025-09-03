#!/usr/bin/env python3
"""
combine_eml_sms.py

Combine multiple SMS/MMS .eml files into:
  1) One combined EML per thread (1:1 or group), attaching each original .eml (message/rfc822) in chronological order
  2) A JSON per thread with messages in order, text, timestamps, base64-embedded attachments/images,
     per-message sender + source .eml, and hybrid iPhone-like grouping.

Also writes a summary_report.json capturing counts for ALL messages/threads, including skipped cases.

Key behaviors:
- Hybrid grouping (iPhone-like): 1:1 messages go to a person file; messages with 2+ non-self participants go to a separate Group_* file
- Direction inference: prefer X-smssync-type, then X-smssync-address match; else compare From/To with your identities; if ambiguous, consult folder/label hints
- Participants are taken from From/To headers only (not Cc/Bcc), to avoid false groups
- Phone sanitization: digits-only (no '+', no leading '1'); used for keys/filenames
- Self-to-self threads are allowed; messages are de-duplicated to avoid doubled entries
- 1:1 threads with improper/short-code counterpart (phone-like but not 10 digits) -> NO EML/JSON written; logged as skipped
- Any thread (1:1 or group) with only 1 message (AFTER DEDUPE) -> NO EML/JSON written; logged as skipped
- Progress prints every 1000 files; final summary printed and written to summary_report.json
- Filenames capped at 100 chars; if exceeded, truncate and append _<5-char-hash> before extension
"""

import argparse
import base64
import glob
import json
import os
import re
import sys
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, getaddresses
from typing import List, Optional, Tuple, Dict, Any, Set

# -------------------------- Config / Aliases --------------------------
ALIAS: Dict[str, str] = {}

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
    # All non-self participants (from From/To only) for this message
    participants: List[dict] = field(default_factory=list)  # {"name","addr","phone"}
    # Sender info
    sender_name: Optional[str] = None
    sender_addr: Optional[str] = None
    sender_phone: Optional[str] = None
    sender_is_self: bool = False
    # Source EML file path
    source_path: Optional[str] = None

def sanitize_phoneish(s: Optional[str]) -> Optional[str]:
    """Normalize phone-ish strings: strip +, non-digits; drop leading US '1'. Return digits if >=7 else None."""
    if not s:
        return None
    local = s.split('@', 1)[0]
    digits = re.sub(r'\D', '', local)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits if len(digits) >= 7 else None

def is_proper_10_digit_number(s: Optional[str]) -> bool:
    ph = sanitize_phoneish(s or "")
    return bool(ph and len(ph) == 10)

def normalize_addr(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def folder_hint_direction(msg) -> Optional[str]:
    CANDIDATE_HDRS = ["X-Gmail-Labels", "X-Labels", "X-Folder", "Folder", "X-Mozilla-Status2"]
    val = ""
    for h in CANDIDATE_HDRS:
        v = msg.get(h)
        if v:
            val += " " + str(v)
    val_l = val.lower()
    if not val_l.strip():
        return None
    if "sent" in val_l or "[gmail]/sent" in val_l or "sent mail" in val_l:
        return "out"
    if "inbox" in val_l or "[gmail]/inbox" in val_l or "received" in val_l:
        return "in"
    return None

def phone_variants(digits: str) -> Set[str]:
    v: Set[str] = {digits}
    if len(digits) == 10:
        v.add("1" + digits)
        v.add("+1" + digits)
        v.add(digits + "@unknown.email")
        v.add(("1" + digits) + "@unknown.email")
        v.add(("+1" + digits) + "@unknown.email")
    return v

def build_self_set(self_identifiers: List[str]) -> Set[str]:
    S: Set[str] = set()
    for t in self_identifiers:
        t = normalize_addr(t)
        if not t:
            continue
        S.add(t)
        ph = sanitize_phoneish(t)
        if ph:
            S |= {normalize_addr(x) for x in phone_variants(ph)}
    return S

def is_self_addr(addr: Optional[str], SELF: Set[str]) -> bool:
    if not addr:
        return False
    a = normalize_addr(addr)
    if a in SELF:
        return True
    ph = sanitize_phoneish(a)
    if not ph:
        return False
    for s in SELF:
        s_ph = sanitize_phoneish(s)
        if s_ph and s_ph == ph:
            return True
    return False

def canonical_name(name_or_addr: Optional[str]) -> Optional[str]:
    if not name_or_addr:
        return None
    ph = sanitize_phoneish(name_or_addr)
    if ph and ph in ALIAS:
        return ALIAS[ph]
    key = normalize_addr(name_or_addr)
    if key in ALIAS:
        return ALIAS[key]
    return (name_or_addr if sanitize_phoneish(name_or_addr) is None else ph) or name_or_addr

def get_timestamp_ms(msg) -> int:
    def to_ms(n: int) -> int:
        if n > 10**14:   # microseconds
            return n // 1000
        if n < 10**12:   # seconds
            return n * 1000
        return n         # milliseconds

    xms = msg.get('X-smssync-date')
    if xms:
        try:
            n = int(xms.strip())
            return to_ms(n)
        except Exception:
            pass

    date_hdr = msg.get('Date')
    if date_hdr:
        try:
            dt = parsedate_to_datetime(date_hdr)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except Exception:
            pass

    return 0

def iso_from_ms(ms: int) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return ""

def html_to_text(html: str) -> str:
    text = re.sub(r'(?is)<(script|style).*?>.*?</\1>', '', html)
    text = re.sub(r'(?s)<br\s*/?>', '\n', text)
    text = re.sub(r'(?s)</p\s*>', '\n', text)
    text = re.sub(r'(?s)<.*?>', '', text)
    return re.sub(r'&nbsp;', ' ', text)

def decode_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == 'text/plain':
                try:
                    payload = part.get_payload(decode=True) or b''
                    return payload.decode(part.get_content_charset() or 'utf-8', errors='replace').strip()
                except Exception:
                    continue
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == 'text/html':
                try:
                    payload = part.get_payload(decode=True) or b''
                    html = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
                except Exception:
                    continue
                return html_to_text(html).strip()
        return ""
    else:
        payload = msg.get_payload(decode=True) or b''
        if not payload:
            return ""
        ctype = msg.get_content_type()
        if ctype == 'text/html':
            return html_to_text(payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')).strip()
        return payload.decode(msg.get_content_charset() or 'utf-8', errors='replace').strip()

def extract_attachments(msg) -> List[Attachment]:
    atts: List[Attachment] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        cdisp = (part.get('Content-Disposition') or '').lower()
        ctype = (part.get_content_type() or '').lower()
        if 'attachment' in cdisp or ctype.startswith('image/'):
            filename = part.get_filename()
            if not filename:
                ext = ctype.split('/')[-1] if '/' in ctype else 'bin'
                filename = f'attachment.{ext}'
            try:
                data = part.get_payload(decode=True) or b''
                atts.append(Attachment(filename=filename, content_type=ctype, data_b64=base64.b64encode(data).decode('ascii')))
            except Exception:
                continue
    return atts

def collect_participants(msg, self_emails: List[str]) -> List[dict]:
    """Collect non-self participants from From/To only (skip Cc/Bcc)."""
    SELF = build_self_set(self_emails)
    addrs = getaddresses(msg.get_all('From', []) + msg.get_all('To', []))
    out = []
    seen = set()
    for nm, ad in addrs:
        ad = (ad or "").strip()
        if not ad or is_self_addr(ad, SELF):
            continue
        key = (normalize_addr(nm or ""), normalize_addr(ad))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": (nm or "").strip() or None,
            "addr": ad,
            "phone": sanitize_phoneish(ad),
        })
    return out

def compute_sender(msg, self_emails: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str], bool]:
    """Return (name, addr, phone, is_self) for the sender based on From:, compared to self set."""
    SELF = build_self_set(self_emails)
    from_addrs = getaddresses(msg.get_all('From', []))
    name, addr = (None, None)
    if from_addrs:
        name = (from_addrs[0][0] or "").strip() or None
        addr = (from_addrs[0][1] or "").strip() or None
    is_self = is_self_addr(addr, SELF)
    phone = sanitize_phoneish(addr or "") or sanitize_phoneish(name or "")
    return name, addr, phone, is_self

def guess_direction_and_parties(msg, self_emails: List[str]) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Return (direction, person_name, person_addr, self_addr).
    Priorities:
      1) X-smssync-type (1=in, 2=out)
      2) X-smssync-address match against From/To
      3) From/To vs known self identifiers (emails + phone variants)
      4) Fallback heuristics (with ambiguity warnings and folder-label hints)
    """
    SELF = build_self_set(self_emails)

    smstype = (msg.get('X-smssync-type') or "").strip()
    person_addr_hdr = (msg.get('X-smssync-address') or "").strip()

    to_addrs = getaddresses(msg.get_all('To', []))
    from_addrs = getaddresses(msg.get_all('From', []))

    def first_addr(addrs):
        if not addrs:
            return (None, None)
        name, addr = addrs[0]
        return ((name or "").strip() or None, (addr or "").strip() or None)

    from_name, from_addr = first_addr(from_addrs)
    to_name, to_addr = first_addr(to_addrs)

    # 1) Explicit type wins
    if smstype == '1':
        return 'in', from_name, from_addr, to_addr
    if smstype == '2':
        return 'out', to_name, to_addr, from_addr

    # 2) X-smssync-address alignment
    if person_addr_hdr:
        if from_addr and person_addr_hdr in (from_addr or ""):
            return 'in', from_name, person_addr_hdr, to_addr
        if to_addr and person_addr_hdr in (to_addr or ""):
            return 'out', to_name, person_addr_hdr, from_addr
        ph_hdr = sanitize_phoneish(person_addr_hdr)
        if ph_hdr:
            if sanitize_phoneish(from_addr or "") == ph_hdr:
                return 'in', from_name, person_addr_hdr, to_addr
            if sanitize_phoneish(to_addr or "") == ph_hdr:
                return 'out', to_name, person_addr_hdr, from_addr

    # 3) Compare to self set
    from_self = is_self_addr(from_addr, SELF)
    to_self = is_self_addr(to_addr, SELF)
    if from_self and not to_self:
        return 'out', to_name, to_addr or person_addr_hdr or to_name, from_addr
    if to_self and not from_self:
        return 'in', from_name, from_addr or person_addr_hdr or from_name, to_addr

    # Ambiguous
    if from_self == to_self:
        mid = msg.get('Message-ID') or 'no-id'
        print(f"[WARN] Ambiguous self detection for {mid}: From={from_addr} To={to_addr}", file=sys.stderr)
        hint = folder_hint_direction(msg)
        if hint == 'in':
            return 'in', from_name, from_addr or person_addr_hdr, to_addr
        if hint == 'out':
            return 'out', to_name, to_addr or person_addr_hdr, from_addr
        if person_addr_hdr:
            ph_hdr = sanitize_phoneish(person_addr_hdr)
            if ph_hdr:
                if sanitize_phoneish(from_addr or "") == ph_hdr:
                    return 'in', from_name, person_addr_hdr, to_addr
                if sanitize_phoneish(to_addr or "") == ph_hdr:
                    return 'out', to_name, person_addr_hdr, from_addr

    # 4) Fallback
    candidates = [(from_name, from_addr), (to_name, to_addr)]
    nonself = [c for c in candidates if not is_self_addr(c[1], SELF)]
    if nonself:
        if nonself[0][1] == from_addr:
            return 'in', from_name, from_addr or person_addr_hdr, to_addr
        else:
            return 'out', to_name, to_addr or person_addr_hdr, from_addr

    return 'out', to_name or from_name, to_addr or from_addr or person_addr_hdr, from_addr or to_addr

def parse_eml_file(path: str, self_emails: List[str]) -> ParsedMessage:
    with open(path, 'rb') as f:
        raw = f.read()
    msg = BytesParser(policy=policy.default).parsebytes(raw)

    direction, person_name, person_addr, self_addr = guess_direction_and_parties(msg, self_emails)
    t_ms = get_timestamp_ms(msg)
    body = decode_text(msg)
    atts = extract_attachments(msg)
    msg_id = msg.get('Message-ID')
    parts = collect_participants(msg, self_emails)
    s_name, s_addr, s_phone, s_is_self = compute_sender(msg, self_emails)

    if not person_name and person_addr:
        all_names = getaddresses(msg.get_all('To', []) + msg.get_all('From', []))
        for nm, ad in all_names:
            if ad == person_addr and nm:
                person_name = (nm or "").strip() or None
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
        participants=parts,
        sender_name=s_name,
        sender_addr=s_addr,
        sender_phone=s_phone,
        sender_is_self=s_is_self,
        source_path=path,
    )

def person_key_from(pm: ParsedMessage) -> str:
    """Stable key for 1:1 threads (prefer phone digits -> addr -> name)."""
    ph = sanitize_phoneish(pm.person_addr) or sanitize_phoneish(pm.person_name or "")
    if ph:
        return ph
    if pm.person_addr:
        return pm.person_addr
    if pm.person_name:
        return pm.person_name
    return f"unknown_{pm.direction}_{pm.timestamp_ms}"

def safe_filename(s: str) -> str:
    s = s or "unknown"
    s = re.sub(r'[^A-Za-z0-9._@+-]+', '_', s).strip('_')
    return s or "unknown"

import hashlib as _hashlib

def enforce_max_filename(name: str, maxlen: int = 100) -> str:
    base, ext = os.path.splitext(name)
    if len(name) <= maxlen:
        return name
    h = _hashlib.sha1(base.encode("utf-8")).hexdigest()[:5]
    keep = max(1, maxlen - len(ext) - 1 - len(h))
    return base[:keep] + "_" + h + ext

def is_improper_counterpart(identifier: Optional[str]) -> bool:
    """
    True ONLY if the counterpart clearly looks like a phone number but is not 10 digits.
    - Email addresses -> False
    - Names / strings with no digits -> False
    - Digits-only (strip '+' and optional leading '1'):
        * 10 digits -> False
        * Otherwise -> True (e.g., 58988, 1234567, etc.)
    """
    if not identifier:
        return False
    s = identifier.strip()
    if '@' in s:
        return False
    digits = re.sub(r"\D", "", s)
    if not digits:
        return False
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return len(digits) != 10

# --------- Participant de-duplication (by phone first, then addr/name) ----------

def looks_like_phone_label(s: Optional[str]) -> bool:
    if not s:
        return False
    t = re.sub(r"\D", "", s)
    return len(t) >= 7

def is_better_name(old: Optional[str], new: Optional[str]) -> bool:
    """Prefer a human name over a numeric/phone-like label."""
    if not new:
        return False
    if not old:
        return True
    if looks_like_phone_label(old) and not looks_like_phone_label(new):
        return True
    return False

def participant_key(p: dict) -> str:
    ph = p.get("phone")
    if ph:
        return f"phone:{ph}"
    addr = normalize_addr(p.get("addr") or "")
    if addr:
        return f"addr:{addr}"
    nm = normalize_addr((p.get("name") or ""))
    if nm:
        return f"name:{nm}"
    return f"anon:{id(p)}"

def unique_participants(part_list: List[dict]) -> List[dict]:
    """Deduplicate participants by sanitized phone first, then addr/name. Merge and prefer human names."""
    out: Dict[str, dict] = {}
    for p in part_list:
        if not p:
            continue
        key = participant_key(p)
        if key not in out:
            out[key] = dict(name=p.get("name"), addr=p.get("addr"), phone=p.get("phone"))
        else:
            cur = out[key]
            if is_better_name(cur.get("name"), p.get("name")):
                cur["name"] = p.get("name")
            if not cur.get("addr") and p.get("addr"):
                cur["addr"] = p.get("addr")
            if not cur.get("phone") and p.get("phone"):
                cur["phone"] = p.get("phone")
    return sorted(out.values(), key=lambda x: (x.get("phone") or "", x.get("addr") or "", x.get("name") or ""))

# -------------------------- Core Routine --------------------------

def dedupe_messages(messages: List[ParsedMessage]) -> Tuple[List[ParsedMessage], int]:
    seen_ids = set()
    seen_fingerprints = set()
    out = []
    removed = 0

    def att_digest(m: ParsedMessage) -> str:
        import hashlib
        h = hashlib.sha1()
        for a in m.attachments:
            h.update(a.filename.encode('utf-8', 'ignore'))
            h.update(a.content_type.encode('utf-8', 'ignore'))
            h.update(a.data_b64.encode('utf-8', 'ignore'))
        return h.hexdigest()

    for m in messages:
        mid = (m.msg_id or "").strip()
        if mid and mid in seen_ids:
            removed += 1
            continue
        fp = (m.timestamp_ms, m.body_text or "", att_digest(m))
        if fp in seen_fingerprints:
            removed += 1
            continue
        if mid:
            seen_ids.add(mid)
        seen_fingerprints.add(fp)
        out.append(m)

    return out, removed

def combine_for_person(person_key: str, messages: List[ParsedMessage], outdir: str):
    # Deduplicate
    messages, dedup_removed = dedupe_messages(messages)
    # Sort
    messages.sort(key=lambda m: (m.timestamp_ms, m.msg_id or ""))

    # Dedup participants across the thread
    tmp_parts = []
    for m in messages:
        tmp_parts.extend(m.participants)
    dedup_parts = unique_participants(tmp_parts)

    # Group or 1:1
    is_group = len(dedup_parts) >= 2
    if is_group:
        label_elems = [canonical_name(p.get("name") or p.get("phone") or p.get("addr") or "unknown") for p in dedup_parts]
        subj_name = "Group: " + ", ".join(sorted(label_elems))
        labels = [safe_filename(p.get("phone") or p.get("addr") or p.get("name") or "unknown") for p in dedup_parts]
        labels = sorted(labels)
        label_for_files = "Group_" + "_".join(labels)
        name = None
        addr = None
        # Canonical thread key
        key_elems = sorted((p.get("phone") or p.get("addr") or p.get("name") or "unknown") for p in dedup_parts)
        final_key = "Group_" + "_".join(key_elems)
    else:
        names = [m.person_name for m in messages if m.person_name]
        name_counts = Counter(names)
        most_common_name = name_counts.most_common(1)[0][0] if name_counts else None
        unique = dedup_parts[0] if dedup_parts else {}
        addr = unique.get("addr")
        name = canonical_name(most_common_name or unique.get("name") or unique.get("phone") or addr)
        subj_name = name or addr or person_key
        label_for_files = (name or sanitize_phoneish(addr) or addr or person_key)
        ph = unique.get("phone")
        final_key = ph if ph else (addr or (unique.get("name") or person_key))

    # Self addr
    self_addrs = [m.self_addr for m in messages if m.self_addr]
    self_addr = self_addrs[0] if self_addrs else None

    # Skips
    if len(messages) <= 1:
        return None, None, "single_message_thread", dedup_removed
    if not is_group:
        counterpart = addr or name or person_key
        if is_improper_counterpart(counterpart):
            return None, None, "improper_number_thread", dedup_removed

    # Build EML
    combined = EmailMessage()
    combined['Subject'] = f"Combined SMS with {subj_name} ({len(messages)} messages)"
    combined['From'] = self_addr or 'me@local'
    combined['To'] = subj_name
    combined.set_content(f"Combined {len(messages)} messages in chronological order.\nThread: {subj_name}\nKey: {final_key}\n")
    for idx, pm in enumerate(messages, 1):
        combined.add_attachment(
            pm.raw_bytes,
            maintype='message',
            subtype='rfc822',
            filename=f"{idx:04d}_{safe_filename(pm.msg_id or 'message')}.eml",
        )

    eml_name = enforce_max_filename(f"{safe_filename(label_for_files)}_combined.eml")
    eml_path = os.path.join(outdir, eml_name)
    with open(eml_path, 'wb') as f:
        f.write(combined.as_bytes())

    # Build JSON
    json_obj: Dict[str, Any] = {
        "thread_key": final_key,
        "thread_label": subj_name,
        "person_name": name if not is_group else None,
        "person_address": addr if not is_group else None,
        "self_address": self_addr,
        "message_count": len(messages),
        "participants": dedup_parts,
        "messages": [],
        "deduplicated_messages_removed": dedup_removed,
    }
    for pm in messages:
        json_obj["messages"].append({
            "message_id": pm.msg_id,
            "direction": pm.direction,
            "timestamp_ms": pm.timestamp_ms,
            "timestamp_iso": pm.timestamp_iso,
            "body": pm.body_text,
            "sender": {
                "name": pm.sender_name,
                "addr": pm.sender_addr,
                "phone": pm.sender_phone,
                "is_self": pm.sender_is_self,
                "label": canonical_name(pm.sender_name or pm.sender_phone or pm.sender_addr or "unknown"),
            },
            "source_eml": pm.source_path,
            "attachments": [att.__dict__ for att in pm.attachments],
        })

    json_name = enforce_max_filename(f"{safe_filename(label_for_files)}_combined.json")
    json_path = os.path.join(outdir, json_name)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_obj, f, ensure_ascii=False, indent=2)

    return eml_path, json_path, None, dedup_removed

def main():
    ap = argparse.ArgumentParser(description="Combine SMS/MMS .eml files into per-thread EML+JSON (1:1 and group).")
    ap.add_argument('inputs', nargs='+', help="Input .eml files, globs, or directories")
    ap.add_argument('-o', '--outdir', default=None, help="Output directory (default: scriptname_YYMMDD_HHMMSS)")
    ap.add_argument('--self-email', action='append', default=[
        "mjbeisser@gmail.com",
        "beissemj@gmail.com",
        "mbeisser@fastmail.com",
        "mbeisser_archive@fastmail.com",
        "9412660605",
    ], help="Specify your own email address(es)/phone to help infer direction/person. Repeatable.")
    args = ap.parse_args()

    # Expand inputs into actual .eml files (dirs are recursive)
    paths: List[str] = []
    for p in args.inputs:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for fn in files:
                    if fn.lower().endswith(".eml"):
                        paths.append(os.path.join(root, fn))
        else:
            paths.extend(glob.glob(p))
    paths = [p for p in paths if os.path.isfile(p) and p.lower().endswith(".eml")]
    if not paths:
        print("No .eml files found from inputs:", args.inputs, file=sys.stderr)
        sys.exit(2)

    # Output dir: script name (no .py) + _YYMMDD_HHMMSS unless -o provided
    if args.outdir:
        outdir = args.outdir
    else:
        script_stem = os.path.splitext(os.path.basename(__file__))[0]
        ts = datetime.now().strftime('%y%m%d_%H%M%S')
        outdir = f'{script_stem}_{ts}'
    os.makedirs(outdir, exist_ok=True)

    # Parse & group per thread, with progress every 1000 files
    groups: Dict[str, List[ParsedMessage]] = defaultdict(list)
    count = 0
    for path in paths:
        try:
            pm = parse_eml_file(path, args.self_email)
            # Build parse-time grouping key (1:1 by person, group by deduped participants)
            pk = person_key_from(pm)
            if len(pm.participants) >= 2:
                parts = unique_participants(pm.participants)
                labels = sorted((p.get("phone") or p.get("addr") or p.get("name") or "unknown") for p in parts)
                pk = "Group_" + "_".join(labels)
            groups[pk].append(pm)
        except Exception as e:
            print(f"[WARN] Failed to parse {path}: {e}", file=sys.stderr)

        count += 1
        if count % 1000 == 0:
            print(f"Processed {count} files...")

    print(f"Finished processing {count} files total.")

    # Totals before writing
    total_messages = sum(len(msgs) for msgs in groups.values())
    total_threads = len(groups)

    # Combine each thread
    summary = []
    skipped = []  # list of dicts: {"thread": key, "reason": reason, "count": N}
    skipped_message_count = 0
    improper_number_threads = []  # threads skipped entirely due to non-10-digit number
    total_dedup_removed = 0

    for thread_key, msgs in groups.items():
        eml_path, json_path, reason, dedup_removed = combine_for_person(thread_key, msgs, outdir)
        total_dedup_removed += (dedup_removed or 0)
        if reason == "single_message_thread":
            skipped.append({"thread": thread_key, "reason": reason, "count": len(msgs)})
            skipped_message_count += len(msgs)
            continue
        if reason == "improper_number_thread":
            skipped.append({"thread": thread_key, "reason": reason, "count": len(msgs)})
            improper_number_threads.append(thread_key)
            skipped_message_count += len(msgs)
            continue
        summary.append((thread_key, eml_path, json_path, len(msgs), dedup_removed))

    # Emit a simple report
    print("Wrote:")
    for thread_key, eml_path, json_path, n, dedup_removed in summary:
        print(f"  - {thread_key} ({n} msgs, dedup_removed={dedup_removed}):")
        print(f"      EML : {eml_path}")
        print(f"      JSON: {json_path}")

    # Report skipped
    if skipped:
        print("\nSkipped:")
        for item in skipped:
            print(f"  - {item['thread']} -> {item['reason']} ({item['count']} msg)")

    # Write summary report JSON
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": outdir,
        "totals": {
            "files_input": len(paths),
            "threads_total": total_threads,
            "threads_written": len(summary),
            "threads_skipped": len(skipped),
            "messages_total": total_messages,
            "messages_written": sum(n for _,_,_,n,_ in summary) - sum(d for *_, d in summary),
            "messages_deduplicated_removed": total_dedup_removed,
            "messages_skipped": skipped_message_count,
            "threads_skipped_improper_number": len(improper_number_threads),
        },
        "threads_written": [
            {"thread_key": t, "eml": e, "json": j, "message_count": n, "dedup_removed": d}
            for (t, e, j, n, d) in summary
        ],
        "threads_skipped": skipped,
        "threads_skipped_improper_number": improper_number_threads,
    }
    with open(os.path.join(outdir, "summary_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()