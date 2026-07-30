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

## 3a. Clean URL via IIS reverse proxy (production)

By default the app is reached at `https://<host>:8501`. To serve it on a clean
no-port URL (`https://3mtracking.uhsinc.com`), IIS on port 443 reverse-proxies to
Streamlit on 8501. This is **IIS server config, not part of the app repo or
install.ps1** — if the box is rebuilt, redo these steps. It is a *reverse proxy*
(browser stays on the clean URL), not a redirect (which would expose `:8501`).

On this server, IIS 443 is shared with an existing RD Web Access site. The steps
below add a **separate** site with an SNI host-header binding, so RD Web (its
`*:443:` catch-all) is untouched — http.sys routes by SNI hostname.

1. **Install the modules** (one-time). WebSockets is a Windows feature; URL Rewrite
   and ARR are MSIs from Microsoft (Streamlit needs the WebSocket passthrough):
   ```powershell
   Install-WindowsFeature Web-WebSockets
   # URL Rewrite 2.1 + Application Request Routing 3.0 (download + silent install)
   msiexec /i rewrite_amd64_en-US.msi /qn /norestart
   msiexec /i requestRouter_amd64.msi /qn /norestart
   ```
2. **Enable ARR proxying + preserve host header** (host header must reach Streamlit
   so its XSRF/Origin check passes):
   ```powershell
   $appcmd = "$env:windir\System32\inetsrv\appcmd.exe"
   & $appcmd set config -section:system.webServer/proxy /enabled:"true" /commit:apphost
   & $appcmd set config -section:system.webServer/proxy /preserveHostHeader:"true" /commit:apphost
   ```
3. **Create the site** with an SNI HTTPS binding and bind the cert. The proxy target
   uses `kop-3merdp01` (a SAN on the cert) so backend TLS validates:
   ```powershell
   New-Item -ItemType Directory -Force C:\inetpub\3mtracking   # holds web.config below
   & $appcmd add site /name:"3M Tracker" /physicalPath:"C:\inetpub\3mtracking" `
       /bindings:"https/*:443:3mtracking.uhsinc.com"
   & $appcmd set site "3M Tracker" `
       "/bindings.[protocol='https',bindingInformation='*:443:3mtracking.uhsinc.com'].sslFlags:1"
   # bind the cert that covers 3mtracking.uhsinc.com (thumbprint from Cert:\LocalMachine\My)
   netsh http add sslcert hostnameport=3mtracking.uhsinc.com:443 certhash=<THUMBPRINT> `
       appid="{4dc3e181-e14b-4a21-b022-59fc669b0914}" certstorename=MY
   & $appcmd start site "3M Tracker"
   ```
4. **`C:\inetpub\3mtracking\web.config`** — the reverse-proxy rule:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <configuration>
     <system.webServer>
       <rewrite><rules>
         <rule name="ProxyToStreamlit" stopProcessing="true">
           <match url="(.*)" />
           <action type="Rewrite" url="https://kop-3merdp01:8501/{R:1}" />
         </rule>
       </rules></rewrite>
     </system.webServer>
   </configuration>
   ```
5. Set `app_url = https://3mtracking.uhsinc.com` in `config.ini` (no port) so email
   links use the clean URL, and restart the "IssueTracker App" task.

Verify: `https://3mtracking.uhsinc.com` returns 200, the RD Web URL still returns
200, and a browser login works (confirms the WebSocket proxies). The direct
`https://<host>:8501` keeps working as a fallback.

## 4. Scheduled tasks (created by install.ps1, run as SYSTEM)

| Task | Schedule | What |
|---|---|---|
| IssueTracker App | At startup | Streamlit, headless, port 8501 (+TLS flags when enabled) |
| IssueTracker Reminders | Thu 9:00 AM | Nags owners of Open/In Progress issues with no update this week |
| IssueTracker Weekly Digest | Fri 7:00 AM | Issue digest of the Thu-2PM-to-Thu-2PM reporting week |
| IssueTracker Project Digest | Fri 7:05 AM | Project digest (active + completed this week) |
| IssueTracker DB Backup | Daily 2:00 AM | `backup_db.ps1` → `C:\SQLBackups\IssueTracker`, verified, 14-day retention |

Digest/reminder recipients are managed in-app (Admin → Email recipients), not in
config. For an off-site backup copy, edit the DB Backup task to add
`-OffsiteDir "\\server\share\IssueTracker"` (the SYSTEM/computer account needs write
access to that share).

Restart the app after code/config changes:
`schtasks /End /TN "IssueTracker App"` then `schtasks /Run /TN "IssueTracker App"`.
The email scripts are safe to re-run manually (they check `EmailLog` first).

## 5. App features (admin crib sheet)

- **Auth:** username/password (PBKDF2) + TOTP 2FA (authenticator app, shows as
  "3M Tracker"). New users and password resets force a password change at next
  login. 5 failed attempts lock an account for 15 minutes. Sessions persist across
  refreshes via a signed 12-hour cookie.
- **Admin page:** create users, reset passwords, reset 2FA, activate/deactivate,
  promote/demote admins (not yourself); manage Regions & Facilities (seeded once by
  `schema.sql`, DB-managed thereafter); manage email recipients; reassign a person's
  open work in bulk; email test/send tools; recycle bin (restore/purge); audit log.
- **Issues:** status Open / In Progress / Waiting on Solventum (requires a Solventum
  ticket #) / Hold / Closed; Major flag (closing a Major issue forces the
  "applied to all regions?" prompt); optional due date (overdue badge); fix proposals
  with accept/decline by the assigned analyst (accept moves the issue to In Progress);
  Solventum + ServiceDesk ticket badges; region/facility tagging; attachments (25 MB
  each, stored in the DB); a "Needs update" filter and a "Bulk actions" panel.
- **Projects:** same shape, own lifecycle (Planned / In Progress / On Hold /
  Completed / Cancelled).
- **Dashboard:** metrics, aging, and bar charts (by status/region/assignee), plus
  CSV export of issues and projects. Visible to all users.
- **Notifications:** immediate emails on assignment and on `@username` mentions;
  every email button deep-links to the exact item (via `?page=/?issue=/?project=/`
  query params the app reads on load).
- **Soft-delete:** deleting an issue/project moves it to the recycle bin; deletions,
  restores, and purges (plus admin actions) are recorded in the audit log.
- **Collaboration:** lists and histories live-refresh; presence chips show who else
  is viewing; first viewer holds the edit lock, others are read-only; idle holders
  (10 min without interacting) lose the lock to a waiting viewer; admins can take
  a lock over. Every field change is audited in the item's history with author and
  old → new values.
- **Reporting views:** `vw_IssuesFlat`, `vw_IssuesByRegion`, `vw_IssuesByFacility`,
  `vw_ProjectsFlat` flatten the JSON tags for Grafana/BI (point it at the DB with a
  read-only login). `[servicedesk]` config + `servicedesk.py` scaffold a future
  read-only CA SDM pull (pending API access).

## 6. Tests

DB-free unit tests (auth, reporting date math, email rendering) live in `tests/`.
Install and run:
```powershell
.\venv\Scripts\pip install -r requirements-dev.txt
.\venv\Scripts\python -m pytest
```

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
