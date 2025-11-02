#!/usr/bin/env python3
import datetime
import os
import re
import socket
import subprocess
import tempfile

MAIL_TO = "snapraid@bitrealm.dev"
DEVICES = ["/dev/sdb", "/dev/sdc", "/dev/sdd", "/dev/sde"]  # adjust as needed

KEY_ATTRS = {
    "Reallocated_Sector_Ct": "Realloc",
    "Current_Pending_Sector": "Pending",
    "Offline_Uncorrectable": "Uncorr",
    "Reported_Uncorrect": "Reported",
    "UDMA_CRC_Error_Count": "CRC",
    "Temperature_Celsius": "Temp",
    "Power_On_Hours": "POH",
}


def run_smartctl(dev):
    """Run smartctl and return decoded output string."""
    try:
        out = subprocess.check_output(
            ["sudo", "smartctl", "-A", "-d", "sat", dev], stderr=subprocess.STDOUT
        ).decode()
    except subprocess.CalledProcessError:
        out = subprocess.check_output(
            ["sudo", "smartctl", "-A", "-d", "sat,12", dev], stderr=subprocess.STDOUT
        ).decode()
    return out


def parse_attrs(output):
    """Extract key attributes into dict."""
    attrs = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 10 and parts[0].isdigit():
            name = parts[1]
            raw = parts[-1]
            if name in KEY_ATTRS:
                # Clean temperature values like "35 (Min/Max 31/39)" or "22/50"
                if name == "Temperature_Celsius":
                    raw = re.split(r"[ /()]", raw)[0]
                attrs[KEY_ATTRS[name]] = raw
    return attrs


def get_model(output):
    """Extract model name."""
    for line in output.splitlines():
        if "Device Model:" in line:
            return line.split(":", 1)[1].strip()
        if "Model Family:" in line:
            return line.split(":", 1)[1].strip()
    return "Unknown"


def build_html_table(results):
    headers = ["Drive", "Model"] + list(KEY_ATTRS.values())
    html = [
        "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse: collapse; font-family: monospace;'>"
    ]
    html.append(
        "<tr style='background:#333;color:#fff;'>"
        + "".join(f"<th>{h}</th>" for h in headers)
        + "</tr>"
    )
    for r in results:
        cells = []
        for h in headers:
            val = r.get(h, "-")
            # Highlight alert fields
            if (
                h in ["Realloc", "Pending", "Uncorr", "Reported", "CRC"]
                and val.isdigit()
                and int(val) > 0
            ):
                cells.append(f"<td style='color:red;font-weight:bold;'>{val}</td>")
            elif h == "Temp" and val.isdigit():
                v = int(val)
                if v >= 50:
                    cells.append(f"<td style='color:red;font-weight:bold;'>{val}</td>")
                elif v >= 40:
                    cells.append(f"<td style='color:orange;'>{val}</td>")
                else:
                    cells.append(f"<td>{val}</td>")
            else:
                cells.append(f"<td>{val}</td>")
        html.append("<tr>" + "".join(cells) + "</tr>")
    html.append("</table>")
    return "\n".join(html)


def build_summary(results):
    summary_html = "<h3>Drive Summary</h3><ul>"
    for r in results:
        summary_html += (
            f"<li><b>{r['Drive']} ({r['Model']}):</b> "
            f"Realloc={r.get('Realloc','-')}, "
            f"Pending={r.get('Pending','-')}, "
            f"Uncorr={r.get('Uncorr','-')}, "
            f"Reported={r.get('Reported','-')}, "
            f"CRC={r.get('CRC','-')}, "
            f"Temp={r.get('Temp','-')}°C, "
            f"POH={r.get('POH','-')}</li>"
        )
    summary_html += "</ul>"
    return summary_html


def main():
    host = socket.gethostname()
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []
    overall_ok = True

    # combined raw log file
    combined_file = tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt")
    combined_path = combined_file.name

    for dev in DEVICES:
        out = run_smartctl(dev)
        model = get_model(out)
        attrs = parse_attrs(out)
        row = {"Drive": os.path.basename(dev), "Model": model}
        row.update(attrs)
        results.append(row)

        combined_file.write(f"=== RAW SMART OUTPUT for {dev} ({model}) ===\n")
        combined_file.write(out)
        combined_file.write("\n\n")

        # Check alerts
        for key in ["Realloc", "Pending", "Uncorr", "Reported", "CRC"]:
            val = attrs.get(key, "0")
            if val.isdigit() and int(val) > 0:
                overall_ok = False

    combined_file.close()

    table_html = build_html_table(results)
    summary_html = build_summary(results)
    status = "OK" if overall_ok else "ALERT"
    subject = f"SMART Report {status} - {host}"

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
    <h2>SMART Health Report</h2>
    <p><b>Host:</b> {host}<br>
       <b>Date:</b> {date}<br>
       <b>Status:</b> {"<span style='color:green'>All drives healthy</span>" if overall_ok else "<span style='color:red'>Issues detected!</span>"}</p>
    {summary_html}
    {table_html}
    </body>
    </html>
    """

    # Use mailx with HTML header and single attachment
    cmd = [
        "mailx",
        "-a",
        "Content-Type: text/html; charset=UTF-8",
        "-A",
        combined_path,
        "-s",
        subject,
        MAIL_TO,
    ]
    # cmd = ["mailx", "-a", "Content-type: text/html", "-A", combined_path, "-s", subject, MAIL_TO]
    subprocess.run(cmd, input=html_body.encode(), check=False)

    os.unlink(combined_path)
    print(f"SMART report sent to {MAIL_TO} ({status})")


if __name__ == "__main__":
    main()
