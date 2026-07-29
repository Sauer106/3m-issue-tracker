# 3M Issues & Projects Tracker

A small internal web app the HIM Business Solutions team at UHS uses to keep track of issues and projects around our 3M work. It runs on one Windows server, talks to SQL Server, and stays inside the company network. Nothing fancy, but it does the job and it keeps a clean record of who changed what.

## What it does

People log in, file an issue or start a project, and everyone can follow it as it moves along. Each item carries a status, the Solventum and ServiceDesk ticket numbers it relates to, and the regions and facilities it touches. You can attach files, leave comments, and propose a fix that the assigned analyst then accepts or turns down. Every edit gets written into a history timeline with a name and a timestamp, so months later you can still see how something played out.

Issues move through Open, In Progress, Waiting on Solventum, Hold, and Closed. Projects have their own set of states, since project work doesn't really "resolve" the way a issue does. Anything flagged major gets an extra prompt when it closes, asking whether the fix went out to every region, and that answer lands in the record too.

## Signing in

Login is a username and password plus a code from an authenticator app. The first time you get in, or after an admin resets you, the app makes you choose your own password before it lets you through. Too many bad attempts and it locks the account for a little while. Sessions last about half a day so a page refresh doesn't bounce you back to the login screen, and everything runs over HTTPS with a certificate from our internal CA.

## How it's built

The app is Python and Streamlit. Data lives in SQL Server, reached through pyodbc. Passwords are hashed with PBKDF2, the session cookie is signed with itsdangerous, and the authenticator support uses pyotp. There's no big framework underneath, just a handful of files. app.py is the whole interface. db.py holds every database call. auth.py does the password and token work. send_reminders.py and send_digest.py run on a schedule and handle the email. schema.sql builds and upgrades the database and is safe to run again any time.

## Running it

Clone the repo onto the server and run install.ps1 from an elevated PowerShell. It creates the Python environment, installs the packages, builds the database, sets up a certificate, opens the firewall, registers the scheduled tasks, and starts the app. The first run walks you through making an admin account. SETUP.md has the longer version, including the certificate and reverse proxy notes, if you need them.

Once it's up, the team reaches it at https://3mtracking.uhsinc.com.

## Email

Two jobs run on a schedule. One goes out Thursday morning and reminds people about issues that haven't moved. The other goes out Friday with a summary of the week. Both read their settings from config.ini and send through the internal relay.

## Backups

The database backs itself up every night, checks the file is good, and keeps two weeks of history. Attachments live inside the database, so they get saved right along with everything else.

## Config

config.ini holds the database and mail settings and never goes into git. Copy config.example.ini to get started. The certificate files and the session signing key are specific to each server and also stay out of the repo.
