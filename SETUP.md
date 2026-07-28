# 3M Issues & Projects Tracker — Server Setup Guide

Everything runs on one Windows server with SQL Server (Express is fine). Current
production install: `KOP-3MERDP01`, app at **https://kop-3merdp01:8501**
(pending DNS: `https://3mtracking.uhsinc.com:8501`).

## Quick install (recommended)

After installing the prerequisites (step 1), copy this folder to the server and run
from an **elevated** PowerShell:

```powershell
cd C:\path\to\3m-issue-tracker
powershell -ExecutionPolicy Bypass -File install.ps1
```

`install.ps1` creates the venv, installs packages, runs `schema.sql` (idempotent —
safe to re-run for upgrades), opens `config.ini` for editing on first install, adds
the firewall rule, registers the scheduled tasks (app, reminder emails, digest,
nightly DB backup), starts the app, and prompts for the first admin account.

HTTPS is on by default (see TLS below). Flags: `-NoTls` serves plain HTTP instead
(not recommended — credentials cross the wire in clear), `-Port` (default 8501),
`-SkipSchema`, `-SkipTasks`.

## What's in this folder

| File | Purpose |
|---|---|
| `schema.sql` | Creates/upgrades the `IssueTracker` database (idempotent) |
| `app.py` | The Streamlit web app (login, 2FA, issues, projects, admin) |
| `db.py`, `auth.py`, `mailer.py`, `reporting.py` | Shared modules |
| `send_reminders.py` | Thursday-morning reminder emails (Task Scheduler) |
| `send_digest.py` | Friday-morning weekly digest (Task Scheduler) |
| `backup_db.ps1` | Nightly database backup (Task Scheduler, 2:00 AM) |
| `gen_cert.py` | Generates a self-signed TLS cert into `certs\` (placeholder until a CA cert) |
| `create_admin.py` | One-time: create the first admin account |
| `test_smtp.py` | Verify the SMTP relay works |
| `config.example.ini` | Template — copied to `config.ini` on first install |

Not in git (per-server, see `.gitignore`): `config.ini` (credentials),
`certs\` (TLS key/cert), `session_secret.key` (session-cookie signing key —
delete it to force-log-out everyone), `venv\`.

## 1. Prerequisites

1. **Python 3.11+** from python.org — check **"Add python.exe to PATH"**.
2. **Microsoft ODBC Driver 17 or 18 for SQL Server** — the installer detects which
   is present and warns if `config.ini` needs its `driver` line adjusted.
3. **SQL Server** (Express OK) on the same box, Windows auth.

## 2. Configuration (`config.ini`)

- `[database]` — localhost + Windows auth by default. The app and scheduled tasks
  run as SYSTEM; `schema.sql` grants `NT AUTHORITY\SYSTEM` read/write/backup on the
  database automatically.
- `[smtp]` — internal relay host, port 25, no auth. **The relay must allowlist this
  server's IP** or connections will open and then hang with no banner — that's a
  relay-side allowlist ticket, not an app problem. Test with
  `.\venv\Scripts\python test_smtp.py you@yourdomain.com`.
- `[app]` — `app_url` is what email links point at; keep it matching the real URL
  (scheme included). `timezone` is the server's zone (timestamps are stored in it;
  the UI converts to each viewer's browser zone automatically).

## 3. TLS

The app serves HTTPS from `certs\cert.pem` + `certs\key.pem` by default (disable
with `install.ps1 -NoTls`).

- **CA-issued cert (production):** generate a CSR with `certreq` (key stays on the
  server, mark it `Exportable = TRUE`), have your PKI team issue it, then
  `certreq -accept -machine` the response, export a PFX, and convert to
  `cert.pem`/`key.pem` (chain included in cert.pem). The current cert (UHS Issuing
  CA 03) covers `KOP-3MERDP01.corp.uhsinc.biz`, `KOP-3MERDP01`, and
  `3mtracking.uhsinc.com`; **expires July 2028**.
- **Self-signed (placeholder):** `.\venv\Scripts\python gen_cert.py` creates the
  pair; clients then need `certs\3m-tracker.cer` imported into Trusted Root or
  they'll see warnings.
- Swapping certs is drop-in: replace the two PEM files and restart the
  "IssueTracker App" scheduled task.

## 4. Scheduled tasks (created by install.ps1, run as SYSTEM)

| Task | Schedule | What |
|---|---|---|
| IssueTracker App | At startup | Streamlit, headless, port 8501 (+TLS flags when enabled) |
| IssueTracker Reminders | Thu 9:00 AM | Nags owners of Open/In Progress issues with no update this week |
| IssueTracker Weekly Digest | Fri 7:00 AM | Digest of the Thu-2PM-to-Thu-2PM reporting week to all active users |
| IssueTracker DB Backup | Daily 2:00 AM | `backup_db.ps1` → `C:\SQLBackups\IssueTracker`, verified, 14-day retention |

Restart the app after code/config changes:
`schtasks /End /TN "IssueTracker App"` then `schtasks /Run /TN "IssueTracker App"`.
The email scripts are safe to re-run manually (they check `EmailLog` first).

## 5. App features (admin crib sheet)

- **Auth:** username/password (PBKDF2) + TOTP 2FA (authenticator app, shows as
  "3M Tracker"). New users and password resets force a password change at next
  login. 5 failed attempts lock an account for 15 minutes. Sessions persist across
  refreshes via a signed 12-hour cookie.
- **Admin page:** create users, reset passwords, reset 2FA, activate/deactivate,
  promote/demote admins (not yourself), and manage the Regions & Facilities lists
  (seeded once by `schema.sql`, DB-managed thereafter).
- **Issues:** status Open / In Progress / Waiting on Solventum (requires a Solventum
  ticket #) / Hold / Closed; Major flag (closing a Major issue forces the
  "applied to all regions?" prompt); fix proposals with accept/decline by the
  assigned analyst (accept moves the issue to In Progress); Solventum + ServiceDesk
  ticket badges; region/facility tagging; attachments (25 MB each, stored in the DB).
- **Projects:** same shape, own lifecycle (Planned / In Progress / On Hold /
  Completed / Cancelled).
- **Collaboration:** lists and histories live-refresh; presence chips show who else
  is viewing; first viewer holds the edit lock, others are read-only; idle holders
  (10 min without interacting) lose the lock to a waiting viewer; admins can take
  a lock over. Every field change is audited in the item's history with author and
  old → new values.

## Troubleshooting

- **`pyodbc` IM002 "data source not found"** — the `driver` line in `config.ini`
  doesn't match an installed ODBC driver (`Get-OdbcDriver` lists them).
- **Login failed for `NT AUTHORITY\SYSTEM`** — re-run `schema.sql`; it grants the
  SYSTEM account its database roles.
- **App runs but nothing listens on the port** — the task must include
  `--server.headless true`, or Streamlit silently waits on a first-run prompt.
- **SMTP connects then times out with no banner** — the relay's IP allowlist
  doesn't include this server yet.
- **Client sees certificate warnings** — self-signed placeholder in use, or the
  URL's hostname isn't in the cert's SANs.
- **Emergency log-out of all users** — delete `session_secret.key` and restart the
  app task (it regenerates; every session cookie becomes invalid).
