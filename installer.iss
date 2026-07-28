; Inno Setup script - builds a double-clickable setup.exe for the 3M Issue Tracker.
;
; To build (on any Windows machine):
;   1. Install Inno Setup 6 (free): https://jrsoftware.org/isinfo.php
;   2. Open this file in the Inno Setup Compiler and press Build (Ctrl+F9).
;   3. Result: Output\IssueTrackerSetup.exe - copy to the server and run.
;
; The setup.exe copies the files to C:\IssueTracker and then runs install.ps1,
; which does the real work (venv, packages, database, firewall, scheduled
; tasks, admin account). Python and the ODBC driver must already be installed
; on the server - install.ps1 checks and says so if they're missing.
;
; Optional offline install: on a machine with internet, run
;   pip download -r requirements.txt -d wheels
; and place the resulting "wheels" folder next to this script before building.
; install.ps1 will then install packages without touching the internet.

[Setup]
AppName=3M Issue Tracker
AppVersion=1.0
AppPublisher=Your Team
DefaultDirName=C:\IssueTracker
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputBaseFilename=IssueTrackerSetup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "app.py";              DestDir: "{app}"
Source: "db.py";               DestDir: "{app}"
Source: "auth.py";             DestDir: "{app}"
Source: "mailer.py";           DestDir: "{app}"
Source: "reporting.py";        DestDir: "{app}"
Source: "send_reminders.py";   DestDir: "{app}"
Source: "send_digest.py";      DestDir: "{app}"
Source: "create_admin.py";     DestDir: "{app}"
Source: "test_smtp.py";        DestDir: "{app}"
Source: "schema.sql";          DestDir: "{app}"
Source: "requirements.txt";    DestDir: "{app}"
Source: "config.example.ini";  DestDir: "{app}"
Source: "install.ps1";         DestDir: "{app}"
Source: "SETUP.md";            DestDir: "{app}"
; Uncomment if you bundled offline wheels:
; Source: "wheels\*";          DestDir: "{app}\wheels"

[Run]
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\install.ps1"""; \
    StatusMsg: "Running setup (packages, database, scheduled tasks)..."; \
    Flags: waituntilterminated

[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""IssueTracker App"""; Flags: runhidden; RunOnceId: "DelApp"
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""IssueTracker Reminders"""; Flags: runhidden; RunOnceId: "DelRem"
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""IssueTracker Weekly Digest"""; Flags: runhidden; RunOnceId: "DelDig"
; Note: uninstall leaves the IssueTracker database untouched on purpose.
