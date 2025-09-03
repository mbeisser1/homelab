#!/usr/bin/env python3
import subprocess
import datetime
import socket
import tempfile
import os

MAIL_TO = "snapraid@bitrealm.dev"
DEVICES = ["/dev/sdb", "/dev/sdc", "/dev/sdd", "/dev/sde"]  # adjust if needed

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
    try:
        out = subprocess.check_output(
            ["sudo", "smartctl", "-A", "-d", "sat", dev],
            stderr=subprocess.STDOUT
        ).decode()
    except subprocess.CalledProcessError:
        out = subprocess.check_output(
            ["sudo", "smartctl", "-A", "-d", "sat,12", dev],
            stderr=subprocess.STDOUT
        ).decode()
    return out

def parse_attrs(output):
    attrs = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 10 and parts[0].isdigit():
            name = parts[1]
            raw = parts[-1]
            if name in KEY_ATTRS:
                attrs[KEY_ATTRS[name]] = raw
    return attrs

def get_model(output):
    for line in output.splitlines():
        if "Device Model:" in line:
            return line.split(":",1)[1].strip()
    return "Unknown"

def build_html_table(results):
    headers = ["Drive", "Model"] + list(KEY_ATTRS.values())
    html = ["<table border='1' cellpadding='6' cellspacing='0' style='border-collapse: collapse; font-family: monospace;'>"]
    html.append("<tr style='background:#333;color:#fff;'>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>")
    for r in results:
        cells = []
        for h in headers:
            val = r.get(h,"-")
            if h in ["Realloc","Pending","Uncorr","Reported","CRC"] and val.isdigit() and int(val) > 0:
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

def main():
    host = socket.gethostname()
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []
    overall_ok = True

    for dev in DEVICES:
        out = run_smartctl(dev)
        model = get_model(out)
        attrs = parse_attrs(out)
        row = {"Drive": os.path.basename(dev), "Model": model}
        row.update(attrs)
        results.append(row)
        for key in ["Realloc","Pending","Uncorr","Reported","CRC"]:
            val = attrs.get(key,"0")
            if val.isdigit() and int(val) > 0:
                overall_ok = False

    table_html = build_html_table(results)
    status = "OK" if overall_ok else "ALERT"
    subject = f"SMART Report {status} - {host}"

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
    <h2>SMART Health Report</h2>
    <p><b>Host:</b> {host}<br>
       <b>Date:</b> {date}<br>
       <b>Status:</b> {"<span style='color:green'>All drives healthy</span>" if overall_ok else "<span style='color:red'>Issues detected!</span>"}</p>
    {table_html}
    </body>
    </html>
    """

    # write html to temp file
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html") as f:
        f.write(html_body)
        html_file = f.name

    # send email with mailx, attach Content-type header
    subprocess.run(
        ["mailx", "-a", "Content-type: text/html", "-s", subject, MAIL_TO],
        input=html_body.encode(),
        check=False
    )

    print(f"SMART report sent to {MAIL_TO} ({status})")
    os.unlink(html_file)

if __name__ == "__main__":
    main()

