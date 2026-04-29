# Fieldwire Dashboard

Automated project dashboard that reads Fieldwire CSV report emails from Gmail, generates a static site, and sends inactivity alerts.

## How It Works

1. **Daily at 6am EST**, GitHub Actions runs the pipeline
2. Reads unread Fieldwire report emails from Gmail via IMAP
3. Processes CSV attachments into per-project summaries
4. Generates a static dashboard site (GitHub Pages)
5. Sends email alerts for floors with 7+ days of inactivity

## Setup

### 1. Create the GitHub Repository

```bash
gh repo create fieldwire-dashboard --public --source=. --push
```

### 2. Enable GitHub Pages

1. Go to **Settings > Pages**
2. Set Source to **Deploy from a branch**
3. Set Branch to **main**, folder to **/docs**
4. Click Save

### 3. Add GitHub Secrets

Go to **Settings > Secrets and variables > Actions** and add:

| Secret | Value |
|---|---|
| `GMAIL_ADDRESS` | Your Gmail address that receives Fieldwire emails |
| `GMAIL_APP_PASSWORD` | Gmail App Password (not your regular password) |

`GITHUB_TOKEN` is provided automatically by GitHub Actions.

### 4. Generate a Gmail App Password

1. Go to https://myaccount.google.com/apppasswords
2. Select **Mail** and **Other (Custom name)**
3. Enter "Fieldwire Dashboard" and click Generate
4. Copy the 16-character password into the `GMAIL_APP_PASSWORD` secret

> **Note:** You must have 2-Factor Authentication enabled on your Google account.

### 5. Configure Fieldwire Email Reports

In Fieldwire, set up scheduled CSV task reports to be emailed to your `GMAIL_ADDRESS`. The email subject should follow the pattern: `Project [NAME] - Task Report`.

### 6. Manual Test Run

Go to **Actions > Daily Dashboard Update > Run workflow** to test immediately.

## Alert Recipients

To send inactivity alerts to additional people, create `data/alert_recipients.json`:

```json
["person1@example.com", "person2@example.com"]
```

## File Structure

```
fieldwire-dashboard/
├── .github/workflows/daily_update.yml   # Cron job
├── scripts/
│   ├── fetch_email.py                   # Gmail IMAP reader
│   ├── process_csv.py                   # CSV → JSON processor
│   ├── generate_site.py                 # JSON → HTML generator
│   ├── check_inactivity.py              # Stale floor alerting
│   └── main.py                          # Orchestrator
├── data/                                # Project data (auto-managed)
├── docs/                                # GitHub Pages site
│   ├── index.html                       # Homepage
│   ├── dashboard.html                   # Boss's existing dashboard
│   └── project-*.html                   # Per-project pages
└── requirements.txt                     # PyGithub only
```
