#!/usr/bin/env python3
import os
import sys
import glob
import base64
import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from collections import defaultdict
import html

# Optional, used only for a fallback heuristic
YOUR_EMAILS = ["mjbeisser@gmail.com", "beissemj@gmail.com"]

# ---------- helpers: phone & label sanitation ----------

def sanitize_number(num: str | None) -> str | None:
    """Return XXX-XXX-XXXX (strip +1/leading 1) if a phone-like string; else None."""
    if not num:
        return None
    digits = re.sub(r"\D", "", num)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return None

def is_phone_only_label(label: str) -> bool:
    """True if the label is essentially just a phone number (with punctuation)."""
    if not label:
        return False
    if not re.fullmatch(r"\+?\d[\d\-\(\)\s\._]*", label):
        return False
    return sanitize_number(label) is not None

ARCHIVE_PREFIXES = [
    re.compile(r"^\s*SMS\s+archive\b\s*[-:]*\s*", re.IGNORECASE),  # "SMS archive - " / "SMS archive: "
    re.compile(r"^\s*SMS[_\s]*archive\b[_\s\-:]*", re.IGNORECASE), # "SMS_archive - " etc.
]

def strip_sms_archive_prefix(s: str) -> str:
    """Remove any 'SMS archive' prefix in common formats."""
    out = s or ""
    for rx in ARCHIVE_PREFIXES:
        out = rx.sub("", out)
    return out.strip()

def normalize_display_label(raw: str) -> str:
    """
    Strip 'SMS archive' prefix and pretty-print if it's a phone-only label.
    Always returns a user-facing label for the UI.
    """
    s = strip_sms_archive_prefix(raw or "")
    # if it still has the phrase (weird formatting), nuke it again
    s = re.sub(r"\bSMS\s*archive\b", "", s, flags=re.IGNORECASE).strip()
    if is_phone_only_label(s):
        sn = sanitize_number(s)
        if sn:
            return sn
    return s or "Unknown"

# ---------- helpers: HTML / CID handling ----------

CID_RE = re.compile(r"cid:<?([^>'\"\s]+)>?", flags=re.IGNORECASE)
BODY_RE = re.compile(r"(?is)<body[^>]*>(.*?)</body>")

def extract_inner_body(html_text: str) -> str:
    """If given a full HTML doc, return its <body> inner HTML; else return as-is."""
    if not html_text:
        return ""
    m = BODY_RE.search(html_text)
    return m.group(1) if m else html_text

def inline_cid_images(html_body: str, cid_map: dict) -> str:
    """Replace cid:... references with data: URIs when available."""
    if not html_body or not cid_map:
        return html_body or ""
    return CID_RE.sub(lambda m: cid_map.get(m.group(1), m.group(0)), html_body)

# ---------- EML parsing ----------

def parse_eml(filepath: str) -> dict:
    with open(filepath, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    subject = (msg.get("Subject") or "Unknown").strip()
    sender = msg.get("From", "") or ""
    recipient = msg.get("To", "") or ""
    date_header = msg.get("Date")
    date = parsedate_to_datetime(date_header) if date_header else None

    # Derive a clean display label, prioritizing Subject but normalizing hard
    label_from_subject = normalize_display_label(subject)

    # If the subject was useless, try headers
    if not label_from_subject or label_from_subject.lower() in {"sms archive", "unknown"}:
        cand = recipient if any(e.lower() in sender.lower() for e in YOUR_EMAILS) else sender
        cand = (cand or "").strip()
        if "<" in cand and ">" in cand:
            cand = cand.split("<")[0].strip()
        phone_num = (msg.get("X-smssync-address", "") or "").strip()
        label_from_headers = normalize_display_label(cand or phone_num or "Unknown")
        contact_label = label_from_headers
    else:
        contact_label = label_from_subject

    html_body, plain_body, cid_map = extract_body_and_images(msg)

    # Prefer HTML; otherwise render escaped plain text
    if html_body:
        body = inline_cid_images(extract_inner_body(html_body), cid_map)
    else:
        safe = html.escape(plain_body or "").replace("\n", "<br>")
        body = f"<div>{safe}</div>"

    return {
        "thread_id": subject or contact_label,   # stable key per file
        "subject": subject,
        "contact_label": contact_label,          # already normalized for UI
        "from": sender,
        "to": recipient,
        "date": date,
        "body": body,                            # already HTML-safe
    }

def extract_body_and_images(msg):
    """
    Returns (html_body, plain_body, cid_map) where:
      - html_body: str or None (raw HTML from first text/html part)
      - plain_body: str or None (from text/plain)
      - cid_map: { content-id (without < >): data_uri_string }
    """
    html_body = None
    plain_body = None
    cid_map = {}

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = (part.get_content_type() or "").lower()

            if ctype == "text/html" and html_body is None:
                try:
                    html_body = part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    html_body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")

            elif ctype == "text/plain" and plain_body is None:
                try:
                    plain_body = part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    plain_body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")

            elif ctype.startswith("image/"):
                try:
                    data = part.get_content()
                    if isinstance(data, str):
                        data = data.encode("utf-8")
                except Exception:
                    data = part.get_payload(decode=True) or b""
                b64 = base64.b64encode(data).decode("utf-8")
                cid = (part.get("Content-ID", "") or "").strip().strip("<>")
                if cid:
                    cid_map[cid] = f"data:{ctype};base64,{b64}"
    else:
        ctype = (msg.get_content_type() or "").lower()
        if ctype == "text/html":
            try:
                html_body = msg.get_content()
            except Exception:
                payload = msg.get_payload(decode=True) or b""
                html_body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        elif ctype == "text/plain":
            try:
                plain_body = msg.get_content()
            except Exception:
                payload = msg.get_payload(decode=True) or b""
                plain_body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

    return html_body, plain_body, cid_map

# ---------- HTML generation ----------

def safe_id(s: str) -> str:
    """Make a safe DOM id from any string."""
    sid = re.sub(r"[^A-Za-z0-9_\-]", "_", s or "conv")
    if sid and sid[0].isdigit():
        sid = "_" + sid
    return sid

def generate_html(conversations: dict) -> str:
    # Build sortable rows: (thread_id, msgs, display_label, phone_only, num_key, name_key)
    conv_rows = []
    for thread_id, msgs in conversations.items():
        # Normalize again from the stored, already-normalized label (defensive)
        display_label = normalize_display_label(msgs[0]['contact_label'] or msgs[0]['subject'] or "Unknown")
        phone_only = is_phone_only_label(display_label)

        # numeric sort key for phone-only: compare by last 10 digits
        digits = re.sub(r"\D", "", display_label) if phone_only else ""
        if phone_only and len(digits) >= 10:
            if len(digits) == 11 and digits.startswith("1"):
                digits = digits[1:]
            digits = digits[-10:]
        num_key = digits.zfill(10) if phone_only else ""

        name_key = display_label.lower()
        conv_rows.append((thread_id, msgs, display_label, phone_only, num_key, name_key))

    # Sort: phone-only first; within group sort by num_key or name_key
    conv_rows.sort(key=lambda r: (0 if r[3] else 1, r[4] if r[3] else r[5]))

    html_out = [
        "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>SMS Archive</title>",
        "<style>",
        "html, body { height: 100%; }",
        "body { font-family: Arial, sans-serif; display: flex; height: 100vh; margin: 0; }",
        "#sidebar { width: 320px; background: #f7f7f7; overflow-y: auto; border-right: 1px solid #ccc; }",
        "#sidebar div { padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #e5e5e5; }",
        "#sidebar div:hover { background: #ececec; }",
        "#content { flex: 1; padding: 20px; overflow-y: auto; }",
        ".message { margin-bottom: 18px; }",
        ".date { color: gray; font-size: 0.85em; }",
        ".images img { max-width: 300px; display: block; margin-top: 5px; }",
        "</style></head><body>",
        "<div id='sidebar'>"
    ]

    # Sidebar items (numbers-first)
    for thread_id, _msgs, display_label, _phone_only, _num_key, _name_key in conv_rows:
        chat_name = html.escape(display_label)
        tid = safe_id(thread_id)
        html_out.append(f"<div onclick=\"showConversation('{tid}')\">{chat_name}</div>")

    html_out.append("</div><div id='content'><h2>Select a conversation</h2></div>")

    # Hidden conversation markup
    for thread_id, msgs, display_label, _phone_only, _num_key, _name_key in conv_rows:
        tid = safe_id(thread_id)
        header_name = html.escape(display_label)
        html_out.append(f"<div id='conv_{tid}' style='display:none;'>")
        html_out.append(f"<h2>{header_name}</h2>")
        for msg in sorted(msgs, key=lambda m: m['date'] or ""):
            sender = html.escape(msg['from'] or "")
            date_str = msg['date'].strftime("%Y-%m-%d %H:%M:%S") if msg['date'] else ''
            html_out.append(f"<div class='message'><div><b>{sender}</b> <span class='date'>{date_str}</span></div>")
            html_out.append(f"<div>{msg['body']}</div>")
            html_out.append("</div>")
        html_out.append("</div>")

    html_out.append("""
    <script>
    function showConversation(id) {
        var src = document.getElementById('conv_' + id);
        document.getElementById('content').innerHTML = src ? src.innerHTML : '<p>Not found.</p>';
        window.scrollTo(0, 0);
    }
    </script>
    """)

    html_out.append("</body></html>")
    return "\n".join(html_out)

# ---------- main ----------

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} /path/to/eml/folder output.html")
        sys.exit(1)

    input_folder = sys.argv[1]
    output_file = sys.argv[2]

    conversations = defaultdict(list)

    for filepath in glob.glob(os.path.join(input_folder, "*.eml")):
        msg_data = parse_eml(filepath)
        conversations[msg_data['thread_id']].append(msg_data)

    html_content = generate_html(conversations)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"HTML archive written to {output_file}")

if __name__ == "__main__":
    main()
