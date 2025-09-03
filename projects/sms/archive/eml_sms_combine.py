import re
import argparse
import email
from pathlib import Path
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
import html
from collections import defaultdict

# =========================
# ALIASES – YOUR DATASET
# =========================
ALIASES_RAW = [
    "Akil Meade:407-613-0544,407-613-0936",
    "Amy Rivera,Amy Rivera NOT INTERESTED:407-435-6057",
    "Andrew Sung Chul McEwen:206-919-4975,713-480-1193,941-223-8191",
    "Caitlin Crosley,Caitlin Crozlin:407-803-2664",
    "Carrie Hollingsworth,Carrie Hollinsworth:407-432-7834,954-895-6047",
    "Cathy Arp:941-474-9141,941-809-6230",
    "Chris Hoeddinghau,Chris Hoeddinghaus:813-784-4924",
    "Jack West:407-468-3125,407-504-1773",
    "Leslie Barnett,Leslie Bennett:904-874-6263,941-716-1527",
    "Lisa Tomlin,Lisa Tomlin Ponson:941-237-1249",
    "Luke Cronland,Luke Cronlund:407-694-5738",
    "Mark Ronhaar,Mark Ronhar:407-489-0263,407-625-2823",
    "Megan Wasneechak,Megan Waznechak:716-510-5998",
    "Mom:309-213-6135,941-313-0870",
    "Nicole Ramsland:407-592-3293,865-851-3858",
    "Paola,Paola Londono:407-748-1215",
    "Robert McCroy Jr,Robert Mcroy Jr,mcroyr gmail com:321-246-2167",
    "Tiffany Goad:407-808-2908,727-504-3004",
    "Tori Hill:407-719-4436,407-755-7584",
]

# Parse into number_map and name_map
NUMBER_MAP = {}
NAME_MAP = {}
for entry in ALIASES_RAW:
    parts = entry.split(":")
    if len(parts) == 2:
        names_part, numbers_part = parts
    elif len(parts) == 3:
        names_part, numbers_part = parts[0] + "," + parts[1], parts[2]
    else:
        continue

    names = [n.strip() for n in names_part.split(",") if n.strip()]
    numbers = [n.strip() for n in numbers_part.split(",") if n.strip()]

    canonical = names[0]
    for n in numbers:
        NUMBER_MAP[n] = canonical
    for n in names:
        NAME_MAP[n] = canonical

# =========================
# HELPER FUNCTIONS
# =========================

MY_EMAILS = {"beissemj@gmail.com", "mjbeisser@gmail.com", "mbeisser_archive@bitrealm.dev"}
MY_NUMBERS = {"941-266-0605"}

def sanitize_number(num):
    if not num:
        return None
    digits = re.sub(r"\D", "", num)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return None

def extract_number_from_text(text):
    if not text:
        return None
    match = re.search(r"\+?1?\D?(\d{3})\D?(\d{3})\D?(\d{4})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None

def is_my_address(email_addr, phone_num):
    if email_addr and email_addr.lower() in MY_EMAILS:
        return True
    phone_sanitized = sanitize_number(phone_num)
    if phone_sanitized and phone_sanitized in MY_NUMBERS:
        return True
    return False

def parse_eml(filepath):
    with open(filepath, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    from_name, from_addr = email.utils.parseaddr(msg.get("From", ""))
    to_name, to_addr = email.utils.parseaddr(msg.get("To", ""))

    from_number = sanitize_number(msg.get("X-smssync-address", from_addr))
    to_number = sanitize_number(msg.get("X-smssync-address", to_addr))

    if not from_number:
        from_number = extract_number_from_text(from_name) or extract_number_from_text(from_addr)
    if not to_number:
        to_number = extract_number_from_text(to_name) or extract_number_from_text(to_addr)

    from_number = sanitize_number(from_number)
    to_number = sanitize_number(to_number)

    # Direction detection
    if is_my_address(from_addr, from_number):
        from_me = True
        contact_name = to_name.strip('"') or None
        contact_number = to_number
    elif is_my_address(to_addr, to_number):
        from_me = False
        contact_name = from_name.strip('"') or None
        contact_number = from_number
    else:
        from_me = False
        contact_name = from_name.strip('"') or None
        contact_number = from_number

    if not contact_number and not contact_name:
        contact_number = (from_addr or "").lower()

    try:
        date_obj = email.utils.parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
    except Exception:
        date_obj = None
    if not date_obj:
        date_obj = datetime.min

    body_text = None
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and body_text is None:
                try:
                    body_text = part.get_content()
                except Exception:
                    body_text = part.get_payload(decode=True).decode(errors="ignore")
            elif part.get_filename():
                attachments.append(part)
    else:
        if msg.get_content_type() == "text/plain":
            body_text = msg.get_content()

    return {
        "date": date_obj,
        "from_me": from_me,
        "text": body_text or "",
        "attachments": attachments,
        "contact_name": contact_name,
        "contact_number": contact_number,
        "file_path": filepath
    }

def canonicalize(contact_name, contact_number):
    # Rule 1: number first
    if contact_number and contact_number in NUMBER_MAP:
        return NUMBER_MAP[contact_number]
    # Rule 2: name fallback
    if contact_name and contact_name in NAME_MAP:
        return NAME_MAP[contact_name]
    return contact_name or contact_number or "Unknown"

def build_combined_eml_html(contact_name, messages):
    messages.sort(key=lambda m: m["date"])
    top_msg = MIMEMultipart("mixed")
    top_msg["From"] = email.utils.formataddr((contact_name, ""))
    top_msg["To"] = email.utils.formataddr(("", ""))
    top_msg["Subject"] = f"SMS archive {contact_name}"
    top_msg["Date"] = email.utils.format_datetime(messages[0]["date"])
    related = MIMEMultipart("related")
    html_parts = [
        "<html><body style='background-color:#f5f5f5;font-family:sans-serif;'>",
        f"<h2 style='text-align:center;'>{contact_name}</h2>"
    ]
    prev_date_str = None
    inline_images = []
    other_files = []
    used_filenames = set()

    for idx, m in enumerate(messages):
        msg_date_str = m["date"].strftime("%Y-%m-%d") if m["date"] != datetime.min else "Unknown"
        if prev_date_str != msg_date_str:
            html_parts.append(f"<div style='text-align:center;margin:10px 0;color:#555;font-size:0.9em;border-bottom:1px solid #ccc;'>{msg_date_str}</div>")
            prev_date_str = msg_date_str

        ts = m["date"].strftime("%Y-%m-%d %H:%M:%S") if m["date"] != datetime.min else "Unknown time"
        sender = "Me" if m["from_me"] else contact_name
        align = "right" if m["from_me"] else "left"
        bubble_color = "#0b93f6" if m["from_me"] else "#e5e5ea"
        text_color = "#fff" if m["from_me"] else "#000"

        html_parts.append(f"<div style='text-align:{align};color:#999;font-size:0.75em;margin:5px 10px;'>{ts} - {sender}</div>")

        bubble_style = f"background-color:{bubble_color};color:{text_color};padding:8px 12px;border-radius:18px;max-width:60%;display:inline-block;word-wrap:break-word;"

        bubble_content = []
        if m["text"]:
            bubble_content.append(f"<p style='margin:0;white-space:pre-wrap'>{html.escape(m['text'])}</p>")

        for att_idx, att in enumerate(m["attachments"], start=1):
            cid = f"att_{idx}_{att_idx}"
            maintype, subtype = att.get_content_type().split("/", 1)
            payload = att.get_payload(decode=True)
            base_filename = att.get_filename() or f"file_{cid}.{subtype}"
            fname = base_filename
            counter = 1
            while fname in used_filenames:
                fname = f"{Path(base_filename).stem}_{counter}{Path(base_filename).suffix}"
                counter += 1
            used_filenames.add(fname)
            if maintype == "image":
                img_part = MIMEImage(payload, _subtype=subtype)
                img_part.add_header("Content-ID", f"<{cid}>")
                img_part.add_header("Content-Disposition", "inline", filename=fname)
                inline_images.append(img_part)
                bubble_content.append(f"<img src='cid:{cid}' width='300' style='max-width:300px;height:auto;border-radius:12px;margin-top:5px;'>")
            else:
                base_part = MIMEBase(maintype, subtype)
                base_part.set_payload(payload)
                encoders.encode_base64(base_part)
                base_part.add_header("Content-Disposition", "attachment", filename=fname)
                other_files.append(base_part)
                bubble_content.append(f"<p style='margin:0;'>[Attachment: {fname}]</p>")

        if bubble_content:
            html_parts.append(f"<div style='text-align:{align};margin:2px 10px;'><div style='{bubble_style}'>" + "".join(bubble_content) + "</div></div>")

    html_parts.append("</body></html>")
    html_body = MIMEText("\r\n".join(html_parts), "html", "utf-8")
    related.attach(html_body)
    for img_part in inline_images:
        related.attach(img_part)
    top_msg.attach(related)
    for file_part in other_files:
        top_msg.attach(file_part)
    return top_msg

def dedupe_messages(messages):
    unique_msgs, duplicates, prev = [], [], None
    for m in messages:
        att_names = sorted([att.get_filename() or "" for att in m["attachments"]])
        comparable = (m["from_me"], m["text"], m["date"], tuple(att_names))
        if prev and comparable == prev:
            duplicates.append(m)
        else:
            unique_msgs.append(m)
            prev = comparable
    return unique_msgs, duplicates

def safe_write_eml(eml_msg, name, output_dir):
    safe_base = re.sub(r"[^A-Za-z0-9_\-]", "_", f"SMS archive - {name}")
    out_path = output_dir / f"{safe_base}.eml"
    counter = 2
    while out_path.exists():
        out_path = output_dir / f"{safe_base}_{counter}.eml"
        counter += 1
    with open(out_path, "wb") as f:
        f.write(eml_msg.as_bytes(policy=policy.SMTP))
    return out_path

def main():
    parser = argparse.ArgumentParser(description="Combine EML SMS messages into one file per canonical person")
    parser.add_argument("input_dir", help="Folder containing .eml files")
    args = parser.parse_args()

    files = sorted(Path(args.input_dir).glob("*.eml"))
    grouped = defaultdict(list)
    total_dupes = 0

    for idx, file in enumerate(files, start=1):
        data = parse_eml(file)
        canonical = canonicalize(data["contact_name"], data["contact_number"])
        grouped[canonical].append(data)
        if idx % 1000 == 0 or idx == len(files):
            print(f"Processed {idx}/{len(files)}")

    output_dir = Path(f"output_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}")
    output_dir.mkdir(exist_ok=True)

    for name, msgs in grouped.items():
        msgs.sort(key=lambda m: m["date"])
        unique_msgs, dupes = dedupe_messages(msgs)
        total_dupes += len(dupes)
        eml_msg = build_combined_eml_html(name, unique_msgs)
        out_path = safe_write_eml(eml_msg, name, output_dir)
        print(f"Wrote: {out_path.name} (messages: {len(unique_msgs)}, dupes removed: {len(dupes)})")

    print(f"\nTotal duplicates removed: {total_dupes}")
    print(f"Styled HTML EMLs written to: {output_dir}")

if __name__ == "__main__":
    main()
