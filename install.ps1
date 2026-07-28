# 3M Issue Tracker - automated installer
# Run from an elevated PowerShell in the app folder:
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Options:
#   -Port 8501     port for the web app
#   -SkipSchema    don't run schema.sql (already created the database)
#   -SkipTasks     don't create the scheduled tasks
#Requires -RunAsAdministrator
param(
    [string]$Port = "8501",
    [switch]$SkipSchema,
    [switch]$SkipTasks
)
$ErrorActionPreference = "Stop"
$AppDir = $PSScriptRoot
Set-Location $AppDir

Write-Host "=== 3M Issue Tracker installer ===" -ForegroundColor Cyan
Write-Host "Installing from: $AppDir"

# --- 1. Python ---------------------------------------------------------------
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python not found on PATH. Install Python 3.11+ from python.org (check 'Add python.exe to PATH'), then re-run."
}
$okVersion = (& python -c "import sys; print(sys.version_info >= (3, 11))").Trim()
if ($okVersion -ne "True") {
    throw "Python 3.11 or newer is required. Found: $(& python --version)"
}

# --- 2. ODBC driver check ----------------------------------------------------
$drivers = Get-OdbcDriver -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "ODBC Driver 1? for SQL Server" }
if (-not $drivers) {
    Write-Warning "No 'ODBC Driver 17/18 for SQL Server' found. Install it from Microsoft before using the app."
} elseif (-not ($drivers.Name -contains "ODBC Driver 18 for SQL Server")) {
    Write-Warning "Driver 18 not found but $($drivers[0].Name) is - update the 'driver' line in config.ini to match."
}

# --- 3. venv + packages ------------------------------------------------------
if (-not (Test-Path "$AppDir\venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv "$AppDir\venv"
}
$pip = "$AppDir\venv\Scripts\pip.exe"
if (Test-Path "$AppDir\wheels") {
    Write-Host "Installing packages from bundled wheels (offline)..."
    & $pip install --no-index --find-links "$AppDir\wheels" -r requirements.txt
} else {
    Write-Host "Installing packages from PyPI..."
    & $pip install -r requirements.txt
}

# --- 4. Database schema ------------------------------------------------------
if (-not $SkipSchema) {
    if (Get-Command sqlcmd -ErrorAction SilentlyContinue) {
        Write-Host "Creating IssueTracker database (schema.sql is idempotent)..."
        sqlcmd -S localhost -E -i "$AppDir\schema.sql"
    } else {
        Write-Warning "sqlcmd not found - open schema.sql in SSMS and execute it manually before first use."
    }
}

# --- 5. Config ---------------------------------------------------------------
if (-not (Test-Path "$AppDir\config.ini")) {
    Copy-Item "$AppDir\config.example.ini" "$AppDir\config.ini"
    Write-Host ""
    Write-Host "Opening config.ini - set your SMTP relay host and app_url, then SAVE and CLOSE Notepad to continue." -ForegroundColor Yellow
    Start-Process notepad "$AppDir\config.ini" -Wait
}

# --- 6. Firewall -------------------------------------------------------------
if (-not (Get-NetFirewallRule -DisplayName "3M Issue Tracker" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "3M Issue Tracker" -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $Port | Out-Null
    Write-Host "Firewall rule added for TCP $Port."
}

# --- 7. Scheduled tasks ------------------------------------------------------
if (-not $SkipTasks) {
    $python    = "$AppDir\venv\Scripts\python.exe"
    $streamlit = "$AppDir\venv\Scripts\streamlit.exe"

    Write-Host "Registering scheduled tasks..."
    schtasks /Create /F /TN "IssueTracker App" /SC ONSTART /RU SYSTEM `
        /TR "`"$streamlit`" run `"$AppDir\app.py`" --server.address 0.0.0.0 --server.port $Port" | Out-Null
    schtasks /Create /F /TN "IssueTracker Reminders" /SC WEEKLY /D THU /ST 09:00 /RU SYSTEM `
        /TR "`"$python`" `"$AppDir\send_reminders.py`"" | Out-Null
    schtasks /Create /F /TN "IssueTracker Weekly Digest" /SC WEEKLY /D FRI /ST 07:00 /RU SYSTEM `
        /TR "`"$python`" `"$AppDir\send_digest.py`"" | Out-Null

    Write-Host "Starting the app..."
    schtasks /Run /TN "IssueTracker App" | Out-Null
}

# --- 8. Admin account --------------------------------------------------------
Write-Host ""
$hasAdmin = & "$AppDir\venv\Scripts\python.exe" -c "import db; print(any(u['IsAdmin'] for u in db.list_users()))" 2>$null
if ($hasAdmin.Trim() -ne "True") {
    Write-Host "Create your admin account:" -ForegroundColor Yellow
    & "$AppDir\venv\Scripts\python.exe" "$AppDir\create_admin.py"
}

Write-Host ""
Write-Host "=== Install complete ===" -ForegroundColor Green
Write-Host "App:            http://localhost:$Port  (team: http://$env:COMPUTERNAME`:$Port)"
Write-Host "Test the relay: .\venv\Scripts\python test_smtp.py you@yourdomain.com"
Write-Host "Emails:         reminders Thu 9:00 AM, digest Fri 7:00 AM (Task Scheduler)"
