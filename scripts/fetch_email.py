"""Fetch Fieldwire CSV report emails from Gmail via IMAP."""

import imaplib
import email
import os
import re
import urllib.request
from email.header import decode_header
from datetime import datetime, timezone


def decode_subject(subject_raw):
    parts = decode_header(subject_raw)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def slugify(name):
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


def extract_project_name(subject):
    match = re.search(r"Project\s+(.+?)\s*[-\u2013\u2014]\s*Task\s+Report", subject, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"Project\s+(.+?)\s*[-\u2013\u2014]\s*.*Report", subject, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    cleaned = re.sub(r"\s*[-\u2013\u2014]\s*.*Report.*$", "", subject, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(Re:|Fwd?:)\s*", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else "unknown-project"


def fetch_emails(gmail_address, gmail_app_password, data_dir):
    results = []

    print("Connecting to Gmail IMAP...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(gmail_address, gmail_app_password)
    except Exception as e:
        print(f"ERROR: Failed to connect to Gmail: {e}")
        raise SystemExit(1)

    try:
        mail.select("Fieldwire")
        status, message_ids = mail.search(
            None, '(UNSEEN FROM "support@fieldwire.com" SUBJECT "report")'
        )

        if status != "OK" or not message_ids[0]:
            print("No new Fieldwire report emails found.")
            return results

        ids = message_ids[0].split()
        print(f"Found {len(ids)} new report email(s).")

        for msg_id in ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    print(f"WARNING: Failed to fetch email {msg_id}")
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = decode_subject(msg.get("Subject", ""))
                project_name = extract_project_name(subject)
                project_slug = slugify(project_name)
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                print(f"Processing: {subject} -> project '{project_name}'")

                found = False

                # Method 1: Look for CSV attachment
                for part in msg.walk():
                    content_disposition = str(part.get("Content-Disposition", ""))
                    if "attachment" not in content_disposition:
                        continue
                    filename = part.get_filename()
                    if not filename or not filename.lower().endswith(".csv"):
                        continue
                    project_dir = os.path.join(data_dir, project_slug)
                    os.makedirs(project_dir, exist_ok=True)
                    csv_path = os.path.join(project_dir, f"{today}.csv")
                    with open(csv_path, "wb") as f:
                        f.write(part.get_payload(decode=True))
                    print(f"  Saved CSV attachment: {csv_path}")
                    results.append({
                        "project_name": project_name,
                        "project_slug": project_slug,
                        "csv_path": csv_path,
                        "date": today,
                    })
                    found = True
                    break

                # Method 2: Look for download link in email body
                if not found:
                    body_text = ""
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type in ("text/plain", "text/html"):
                            body_text += part.get_payload(decode=True).decode("utf-8", errors="replace")
                    match = re.search(r'https://files\.us\.fieldwire\.com/\S+', body_text)
                    if match:
                        url = match.group(0).rstrip('">')
                        print(f"  Found download link: {url}")
                        project_dir = os.path.join(data_dir, project_slug)
                        os.makedirs(project_dir, exist_ok=True)
                        csv_path = os.path.join(project_dir, f"{today}.csv")
                        urllib.request.urlretrieve(url, csv_path)
                        print(f"  Downloaded CSV from link: {csv_path}")
                        results.append({
                            "project_name": project_name,
                            "project_slug": project_slug,
                            "csv_path": csv_path,
                            "date": today,
                        })
                        found = True

                if not found:
                    print(f"  WARNING: No CSV found in email: {subject}")

                mail.store(msg_id, "+FLAGS", "\\Seen")

            except Exception as e:
                print(f"ERROR: Failed to process email {msg_id}: {e}")
                continue

    finally:
        mail.logout()

    print(f"Fetched {len(results)} CSV(s).")
    return results


if __name__ == "__main__":
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    fetch_emails(
        os.environ["GMAIL_ADDRESS"],
        os.environ["GMAIL_APP_PASSWORD"],
        data_dir,
    )
