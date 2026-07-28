# 3M Issue Tracker — Server Setup Guide

Everything runs on your existing Windows automation server (the one already running
SQL Server and your PowerShell capture script).

## Quick install (recommended)

Steps 2–7 below are automated by `install.ps1`. After installing Python 3.11+ and
the ODBC driver (step 1), copy this folder to the server and run from an
**elevated** PowerShell:

```powershell
cd C:\IssueTracker
powershell -ExecutionPolicy Bypass -File install.ps1
```

It creates the venv, installs packages, runs `schema.sql`, opens `config.ini` for
you to edit, adds the firewall rule, registers the app + both email scripts in Task
Scheduler, starts the app, and prompts for your admin account. Prefer a
double-clickable `setup.exe`? Compile `installer.iss` with Inno Setup on any
Windows machine — see the comments at the top of that file.

The manual steps below do the same thing, and are useful for troubleshooting.

## What's in this folder

| File | Purpose |
|---|---|
| `schema.sql` | Creates the `IssueTracker` database and tables |
| `app.py` | The Streamlit web app |
| `db.py`, `auth.py`, `mailer.py`, `reporting.py` | Shared modules |
| `send_reminders.py` | Thursday-morning reminder emails (Task Scheduler) |
| `send_digest.py` | Friday-morning weekly digest (Task Scheduler) |
| `create_admin.py` | One-time: create your admin account |
| `test_smtp.py` | One-time: verify the SMTP relay works |
| `config.example.ini` | Template — copy to `config.ini` and edit |

## 1. Install prerequisites (on the server)

1. **Python 3.11+** from python.org — check **"Add python.exe to PATH"** during install.
2. **Microsoft ODBC Driver 18 for SQL Server** — download from Microsoft if not already
   installed (SSMS installs often include it; check *Apps & Features*).

## 2. Copy the project and install packages

Copy this folder to the server, e.g. `C:\IssueTracker`, then in PowerShell:

```powershell
cd C:\IssueTracker
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

## 3. Create the database

Open `schema.sql` in SSMS and execute it (or `sqlcmd -S localhost -i schema.sql`).
It creates the `IssueTracker` database with `Users`, `Issues`, `IssueUpdates`, and
`EmailLog` tables. It will not touch your existing databases.

## 4. Configure

```powershell
copy config.example.ini config.ini
notepad config.ini
```

- `[database]` — defaults (localhost + Windows auth) usually work as-is on the box.
- `[smtp]` — set `host` to your relay's name. Port 25 / no auth is typical for
  internal relays; if yours needs TLS or a login, fill those in.
- `[app]` — set `app_url` to `http://<your-server-name>:8501`.
- Adjust `categories` to whatever buckets make sense for your 3M issues.

## 5. Create your admin account and test

```powershell
.\venv\Scripts\python create_admin.py
.\venv\Scripts\python test_smtp.py Mike@sauersec47.com
.\venv\Scripts\streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Browse to `http://localhost:8501`, log in, and create your team's accounts under
**Admin**. Then open the firewall so teammates can reach it:

```powershell
netsh advfirewall firewall add rule name="3M Issue Tracker" dir=in action=allow protocol=TCP localport=8501
```

## 6. Run the app as a Windows service

The simplest robust option is [NSSM](https://nssm.cc) (a small exe, no install):

```powershell
nssm install IssueTracker "C:\IssueTracker\venv\Scripts\streamlit.exe" "run C:\IssueTracker\app.py --server.address 0.0.0.0 --server.port 8501"
nssm set IssueTracker AppDirectory C:\IssueTracker
nssm start IssueTracker
```

(Alternative without NSSM: a Task Scheduler task set to run `streamlit.exe run ...`
**At startup**, "whether user is logged on or not".)

## 7. Schedule the emails (run in an elevated PowerShell)

Reminders go out **Thursday 9:00 AM** (updates due by 2:00 PM), digest goes out
**Friday 7:00 AM**:

```powershell
schtasks /Create /TN "IssueTracker Reminders" /SC WEEKLY /D THU /ST 09:00 /RU SYSTEM `
  /TR "C:\IssueTracker\venv\Scripts\python.exe C:\IssueTracker\send_reminders.py"

schtasks /Create /TN "IssueTracker Weekly Digest" /SC WEEKLY /D FRI /ST 07:00 /RU SYSTEM `
  /TR "C:\IssueTracker\venv\Scripts\python.exe C:\IssueTracker\send_digest.py"
```

Both scripts are safe to re-run (they check `EmailLog` before sending), so you can
test them manually anytime:

```powershell
.\venv\Scripts\python send_reminders.py
.\venv\Scripts\python send_digest.py
```

If you run the tasks as `SYSTEM` with Windows auth to SQL Server, make sure
`NT AUTHORITY\SYSTEM` has access to the `IssueTracker` database (it does by default
on a local default instance; otherwise grant it, or run the tasks as a service
account and grant that account access instead).

## How the weekly cycle works

- **Update deadline:** Thursday 2:00 PM Eastern, every week.
- **Thursday 9:00 AM:** anyone with an Open / In Progress issue that has no update
  since *last* Thursday 2:00 PM gets one reminder email listing their issues.
- **Friday 7:00 AM:** everyone gets the digest covering the Thursday-to-Thursday
  reporting week — new issues, resolved issues, all open issues with their latest
  update, and issues that missed the deadline highlighted in yellow.

> **Note:** timestamps are stored in SQL Server local time, and the deadline math
> assumes the server clock is Eastern time. If the server is set to a different
> timezone, tell me and I'll adjust the scripts.

## Troubleshooting

- **`pyodbc` can't connect** — confirm the driver name in `config.ini` matches what's
  installed (`Get-OdbcDriver` in PowerShell lists them; older boxes may have
  "ODBC Driver 17 for SQL Server").
- **Relay rejects mail** — many internal relays only accept mail from allowlisted IPs.
  Ask your mail admin to allow the server's IP for anonymous relay.
- **App unreachable from other machines** — check the firewall rule and that
  Streamlit was started with `--server.address 0.0.0.0`.
