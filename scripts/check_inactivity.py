"""Check for stale floors and send inactivity alert emails via Gmail SMTP."""

import json
import os
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EST = timezone(timedelta(hours=-5))
ALERT_COOLDOWN_DAYS = 7


def load_alerts_sent(data_dir):
    path = os.path.join(data_dir, "alerts_sent.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_alerts_sent(data_dir, alerts):
    path = os.path.join(data_dir, "alerts_sent.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2)


def load_recipients(data_dir):
    path = os.path.join(data_dir, "alert_recipients.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def should_send_alert(alerts_sent, key, now):
    if key not in alerts_sent:
        return True
    try:
        last_sent = datetime.fromisoformat(alerts_sent[key])
        return (now - last_sent).days >= ALERT_COOLDOWN_DAYS
    except Exception:
        return True


def build_alert_email(project_name, floor_name, last_activity, open_tasks, pages_url):
    last_act_display = "Unknown"
    if last_activity:
        try:
            dt = datetime.fromisoformat(last_activity)
            last_act_display = dt.astimezone(EST).strftime("%b %d, %Y %I:%M %p EST")
        except Exception:
            last_act_display = last_activity

    task_list = ""
    for t in open_tasks:
        task_list += f"<li>{t}</li>"
    if not task_list:
        task_list = "<li>No open task details available</li>"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#1a1d27;color:#d8dae5;padding:24px;border-radius:12px;">
      <h2 style="color:#ef4444;">Inactivity Alert</h2>
      <p><strong>Project:</strong> {project_name}</p>
      <p><strong>Floor:</strong> {floor_name}</p>
      <p><strong>Last Activity:</strong> {last_act_display}</p>
      <p>This floor has had <strong>no updates for 7+ days</strong>.</p>
      <h3 style="color:#fca5a5;margin-top:16px;">Open Tasks on This Floor</h3>
      <ul style="color:#9ca3af;">{task_list}</ul>
      <br>
      <a href="{pages_url}" style="display:inline-block;padding:10px 20px;background:#818cf8;color:#111318;border-radius:8px;text-decoration:none;font-weight:600;">View Dashboard</a>
    </div>
    """
    return html


def send_alert(gmail_address, gmail_app_password, recipients, subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["From"] = gmail_address
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, recipients, msg.as_string())
        print(f"  Alert sent to: {', '.join(recipients)}")
    except Exception as e:
        print(f"  ERROR: Failed to send alert: {e}")


def check_inactivity(data_dir, gmail_address, gmail_app_password, pages_base_url=""):
    now = datetime.now(timezone.utc)
    alerts_sent = load_alerts_sent(data_dir)
    extra_recipients = load_recipients(data_dir)
    recipients = [gmail_address] + [r for r in extra_recipients if r != gmail_address]
    alerts_count = 0

    for entry in sorted(os.listdir(data_dir)):
        summary_path = os.path.join(data_dir, entry, "summary.json")
        if not os.path.isfile(summary_path):
            continue

        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
        except Exception as e:
            print(f"WARNING: Failed to read {summary_path}: {e}")
            continue

        project_name = summary.get("project_name", entry)
        if not summary.get("has_stale_floors"):
            continue

        slug = entry
        project_url = f"{pages_base_url}/project-{slug}.html" if pages_base_url else ""

        for floor in summary.get("floors", []):
            if not floor.get("is_stale"):
                continue

            floor_name = floor.get("name", "Unknown")
            key = f"{project_name}__{floor_name}"

            if not should_send_alert(alerts_sent, key, now):
                print(f"  Skipping alert for {key} (already sent recently)")
                continue

            print(f"Sending inactivity alert: {project_name} / {floor_name}")

            open_tasks = []
            csv_dir = os.path.join(data_dir, entry)
            csvs = sorted([f for f in os.listdir(csv_dir) if f.endswith(".csv")])
            if csvs:
                import csv as csv_mod
                latest_csv = os.path.join(csv_dir, csvs[-1])
                try:
                    with open(latest_csv, "r", encoding="utf-8-sig") as f:
                        reader = csv_mod.DictReader(f)
                        for row in reader:
                            loc = row.get("Location", "")
                            status = row.get("Status", "")
                            if loc.startswith(floor_name) and status not in ("Verified", "Device Mounted"):
                                open_tasks.append(row.get("Task Name", row.get("Task name", "Unknown")))
                except Exception:
                    pass

            subject = f"Inactivity Alert — {project_name} — {floor_name} — 7 Days No Updates"
            html = build_alert_email(project_name, floor_name, floor.get("last_activity"), open_tasks, project_url)
            send_alert(gmail_address, gmail_app_password, recipients, subject, html)

            alerts_sent[key] = now.isoformat()
            alerts_count += 1

    save_alerts_sent(data_dir, alerts_sent)
    print(f"Inactivity check complete. {alerts_count} alert(s) sent.")
    return alerts_count


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(__file__))
    check_inactivity(
        os.path.join(base, "data"),
        os.environ["GMAIL_ADDRESS"],
        os.environ["GMAIL_APP_PASSWORD"],
    )
