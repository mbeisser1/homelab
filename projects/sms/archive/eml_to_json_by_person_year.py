#!/usr/bin/env python3
# eml_to_json_by_person_year_v7.py
# Fix: ensure text/plain content is properly decoded (quoted-printable, UTF-8) and saved into JSON

import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

YOUR_EMAILS = {"mjbeisser@gmail.com", "beissemj@gmail.com", "mbeisser@bitrealm.dev"}
YOUR_NUMBERS = {"9412660605"}  # normalized to digits only

ALIASES = {
    "Akil Meade": {"names": ["akil meade"], "numbers": ["4076130544", "4076130936"]},
    "Robert McCroy Jr": {
        "names": ["robert mccroy jr", "robert mcroy jr", "mcroyr gmail com"],
        "numbers": ["3212462167"],
    },
    # ... (other aliases omitted for brevity, can be expanded)
}

NAME_TO_CANON, NUM_TO_CANON = {}, {}
for canon, v in ALIASES.items():
    for n in v.get("names", []):
        NAME_TO_CANON[n.lower()] = canon
    for d in v.get("numbers", []):
        NUM_TO_CANON[d] = canon


def norm_digits(s):
    if not s:
        return None
    d = re.sub(r"\D", "", s)
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else None


def pretty_phone(d):
    return f"{d[:3]}-{d[3:6]}-{d[6:]}" if d and len(d) == 10 else d


def safe_filename(s):
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)


def normalize_name_key(s):
    if not s:
        return None
    s = s.strip()
    s = re.sub(r"[,.;:()\[\]{}<>\"']", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s or None


def extract_display_name(hdr_value):
    name, addr = parseaddr(hdr_value or "")
    return name.strip() or None


def parse_date(date_hdr, x_val, backup_time, file_path):
    if x_val:
        try:
            ts = int(x_val)
            if ts > 1e12:
                ts = ts / 1000
            return dt.datetime.utcfromtimestamp(ts).replace(tzinfo=dt.timezone.utc)
        except:
            pass
    if date_hdr:
        try:
            return parsedate_to_datetime(date_hdr)
        except:
            pass
    if backup_time:
        try:
            return parsedate_to_datetime(backup_time)
        except:
            pass
    try:
        ts = os.path.getmtime(file_path)
        return dt.datetime.utcfromtimestamp(ts).replace(tzinfo=dt.timezone.utc)
    except:
        pass
    return None


def extract_text_and_images(msg, attach_dir: Path):
    """
    Extract SMS/MMS plain text and image attachments from an .eml.
    Always returns plain text suitable for JSON.
    """
    text_content = None
    images = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue

            ctype = (part.get_content_type() or "").lower()
            payload = part.get_payload(decode=True)

            if payload is None:
                raw = part.get_payload()
                if isinstance(raw, str):
                    payload = raw.encode(
                        part.get_content_charset() or "utf-8", "replace"
                    )
                else:
                    payload = b""

            if ctype == "text/plain" and text_content is None:
                try:
                    text_content = payload.decode(
                        part.get_content_charset() or "utf-8", "replace"
                    ).strip()
                except Exception:
                    text_content = payload.decode("utf-8", "replace").strip()

            elif ctype.startswith("image/"):
                sha = hashlib.sha256(payload).hexdigest()
                ext = {
                    "image/jpeg": ".jpg",
                    "image/jpg": ".jpg",
                    "image/png": ".png",
                    "image/gif": ".gif",
                    "image/webp": ".webp",
                    "image/bmp": ".bmp",
                    "image/heic": ".heic",
                    "image/heif": ".heif",
                }.get(ctype, ".bin")
                fname = f"{sha[:16]}{ext}"
                attach_dir.mkdir(parents=True, exist_ok=True)
                fpath = attach_dir / fname
                if not fpath.exists():
                    with open(fpath, "wb") as f:
                        f.write(payload)
                images.append(
                    {
                        "path": f"attachments/{fname}",
                        "sha256": sha,
                        "mime": ctype,
                        "size": len(payload),
                    }
                )

    else:
        ctype = (msg.get_content_type() or "").lower()
        payload = msg.get_payload(decode=True)
        if payload is None:
            raw = msg.get_payload()
            if isinstance(raw, str):
                payload = raw.encode(msg.get_content_charset() or "utf-8", "replace")
            else:
                payload = b""
        try:
            text_content = payload.decode(
                msg.get_content_charset() or "utf-8", "replace"
            ).strip()
        except Exception:
            text_content = payload.decode("utf-8", "replace").strip()

    return text_content, images


def direction(from_hdr, to_hdr):
    f, t = (from_hdr or "").lower(), (to_hdr or "").lower()
    if any(e in f for e in YOUR_EMAILS):
        return "out"
    if any(e in t for e in YOUR_EMAILS):
        return "in"
    return None


def subject_partner(subject):
    m = re.match(r"(?i)\s*SMS\s+with\s+(.+)\s*$", (subject or "").strip())
    return m.group(1).strip() if m else None


def find_any_number_in_headers(*hdrs):
    for h in hdrs:
        name, addr = parseaddr(h or "")
        for candidate in (addr, name):
            d = norm_digits(candidate or "")
            if d:
                return d
    return None


def choose_name(preferred_list):
    for x in preferred_list:
        if x and x.strip():
            return x.strip()
    return None


def main():
    if len(sys.argv) < 2:
        print(
            f"Usage: {sys.argv[0]} INPUT_DIR [OUTPUT_DIR] [--phonebook=PATH] [--glob=PATTERN]"
        )
        sys.exit(1)

    inp = Path(sys.argv[1])
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = (
        Path(sys.argv[2])
        if len(sys.argv) >= 3 and not sys.argv[2].startswith("--")
        else Path(f"./eml_to_json_{timestamp}")
    )

    patt = "*.eml"
    phonebook_path = Path("./phonebook.json")
    for arg in sys.argv[2:]:
        if arg.startswith("--glob="):
            patt = arg.split("=", 1)[1]
        if arg.startswith("--phonebook="):
            phonebook_path = Path(arg.split("=", 1)[1])

    phonebook = {}
    if phonebook_path.exists():
        try:
            phonebook = json.load(open(phonebook_path, "r", encoding="utf-8"))
        except Exception:
            phonebook = {}

    learned_names = defaultdict(Counter)
    files = list(inp.rglob(patt))
    buckets = {}
    global_summary = {}
    parsed_count = 0
    written_count = 0
    dupe_count = 0

    for i, p in enumerate(files, 1):
        try:
            msg = BytesParser(policy=policy.default).parse(open(p, "rb"))
        except Exception as e:
            print(f"[WARN] Cannot parse {p}: {e}")
            continue
        parsed_count += 1

        subject = msg.get("Subject", "")
        from_hdr = msg.get("From", "")
        to_hdr = msg.get("To", "")
        x_addr = msg.get("X-smssync-address", "")
        x_date = msg.get("X-smssync-date", "")
        backup = msg.get("X-smssync-backup-time", "")
        dtm = parse_date(msg.get("Date"), x_date, backup, str(p))
        year = str(dtm.year) if dtm else "unknown"
        ts = dtm.astimezone().isoformat() if dtm else None

        num = norm_digits(x_addr) or find_any_number_in_headers(from_hdr, to_hdr)
        name_from_subject = subject_partner(subject)
        name_from_headers = extract_display_name(
            from_hdr if direction(from_hdr, to_hdr) != "out" else to_hdr
        )

        subj_key = normalize_name_key(name_from_subject) or ""
        hdr_key = normalize_name_key(name_from_headers) or ""

        canon = None
        if num and num in NUM_TO_CANON:
            canon = NUM_TO_CANON[num]
        if not canon and subj_key in NAME_TO_CANON:
            canon = NAME_TO_CANON[subj_key]
        if not canon and hdr_key in NAME_TO_CANON:
            canon = NAME_TO_CANON[hdr_key]
        if not canon and num and num in phonebook:
            canon = phonebook[num]
        if not canon:
            canon = choose_name([name_from_subject, name_from_headers])
        if not canon and num:
            canon = pretty_phone(num) or num
        if not canon:
            canon = "Unknown"

        learned_name = choose_name([name_from_subject, name_from_headers])
        if num and learned_name:
            learned_names[num][learned_name] += 1

        person_dir = out_root / safe_filename(canon)
        attach_dir = person_dir / "attachments"

        text, imgs = extract_text_and_images(msg, attach_dir)
        dirn = direction(from_hdr, to_hdr)

        bucket = buckets.setdefault(
            (canon, year),
            {
                "contact": {
                    "canonical_id": canon,
                    "display_name": canon,
                    "numbers": [],
                    "emails": [],
                },
                "meta": {
                    "message_count": 0,
                    "first_timestamp": None,
                    "last_timestamp": None,
                },
                "messages": [],
                "seen": set(),
            },
        )

        if num:
            pp = pretty_phone(num)
            if pp and pp not in bucket["contact"]["numbers"]:
                bucket["contact"]["numbers"].append(pp)
        for hdr in (from_hdr, to_hdr):
            name, addr = parseaddr(hdr or "")
            if addr:
                addr = addr.lower()
                if addr not in YOUR_EMAILS and addr not in bucket["contact"]["emails"]:
                    bucket["contact"]["emails"].append(addr)

        rec = {
            "timestamp": ts,
            "direction": dirn,
            "from": from_hdr,
            "to": to_hdr,
            "text": text,
            "attachments": imgs,
            "file": str(p),
        }
        key = (ts, dirn, text)
        if key in bucket["seen"]:
            dupe_count += 1
            continue
        bucket["seen"].add(key)
        bucket["messages"].append(rec)
        bucket["meta"]["message_count"] += 1
        written_count += 1
        if ts:
            if (
                not bucket["meta"]["first_timestamp"]
                or ts < bucket["meta"]["first_timestamp"]
            ):
                bucket["meta"]["first_timestamp"] = ts
            if (
                not bucket["meta"]["last_timestamp"]
                or ts > bucket["meta"]["last_timestamp"]
            ):
                bucket["meta"]["last_timestamp"] = ts

        if i % 1000 == 0:
            print(f"...processed {i}/{len(files)} files")

    for num, counts in learned_names.items():
        if num in NUM_TO_CANON:
            continue
        best_name, _ = counts.most_common(1)[0]
        if best_name:
            if num not in phonebook:
                phonebook[num] = best_name
            else:
                existing = phonebook[num]
                if normalize_name_key(existing) == normalize_name_key(
                    pretty_phone(num)
                ):
                    phonebook[num] = best_name

    for (canon, year), blob in buckets.items():
        blob["messages"].sort(key=lambda m: m["timestamp"] or "")
        person_dir = out_root / safe_filename(canon)
        person_dir.mkdir(parents=True, exist_ok=True)
        jpath = person_dir / f"{safe_filename(canon)}_{year}.json"
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(
                {k: v for k, v in blob.items() if k != "seen"},
                f,
                indent=2,
                ensure_ascii=False,
            )
        print(f"Wrote {jpath.name} ({len(blob['messages'])} messages)")

    with open(out_root / "summary.json", "w", encoding="utf-8") as f:
        json.dump(global_summary, f, indent=2, ensure_ascii=False)

    if phonebook_path:
        try:
            with open(phonebook_path, "w", encoding="utf-8") as f:
                json.dump(phonebook, f, indent=2, ensure_ascii=False)
            print(f"Updated phonebook: {phonebook_path}")
        except Exception as e:
            print(f"[WARN] Could not write phonebook {phonebook_path}: {e}")

    print(f"Processed {len(files)} .eml files")
    print(f"Parsed messages: {parsed_count}")
    print(f"Written messages: {written_count}")
    print(f"Duplicates skipped: {dupe_count}")


if __name__ == "__main__":
    main()
