# 3M Issues & Projects Tracker — Admin Guide

For administrators. This covers everything a regular user can do (see the **User Guide** for those features) plus the extra powers admins have: managing users, curating the regions and facilities list, moderating content, and keeping the app healthy.

For installing, TLS certificates, the reverse proxy, and other server work, see **SETUP.md**. This guide focuses on what you do from inside the app.

---

## Contents

1. [Who is an admin](#who-is-an-admin)
2. [The Admin page](#the-admin-page)
3. [Bug reports and diagnostics](#bug-reports-and-diagnostics)
4. [Managing users](#managing-users)
5. [Managing regions and facilities](#managing-regions-and-facilities)
6. [Moderating and the recycle bin](#moderating-and-the-recycle-bin)
7. [Fix proposals and edit locks](#fix-proposals-and-edit-locks)
8. [Reassigning work](#reassigning-work)
9. [Email recipients and tools](#email-recipients-and-tools)
10. [The audit log](#the-audit-log)
11. [Reporting and exports](#reporting-and-exports)
12. [Backups](#backups)
13. [Handling common user problems](#handling-common-user-problems)
14. [Security notes](#security-notes)

---

## Who is an admin

Admins have an **Admin** card in their sidebar that regular users don't see. The first admin is created when the app is installed. After that, any admin can promote or demote others.

The rule of thumb: keep admin rights to the few people who actually need to manage accounts and settings. Everything destructive (deleting issues, taking over locks, resetting accounts) is available to every admin.

---

## The Admin page

Click **Admin** in the sidebar. It gathers everything admin-only in one place:

- **User management** — create accounts and manage existing ones.
- **Reassign work** — move a person's open items to someone else.
- **Email recipients** — control who gets the digests and reminders.
- **Regions & Facilities** — curate the region/facility list.
- **Internal Teams** and **Vendors** — curate the master lists tagged on projects.
- **Email tools** — test or send the digests on demand.
- **Recycle bin** — restore or permanently remove deleted items.
- **Audit log** — a record of deletions and admin actions.
- **System diagnostics** — a health readout (see below).

There's also a **Dashboard** card (visible to everyone) with metrics, charts, and spreadsheet exports.

---

## Bug reports and diagnostics

**Where bug reports go.** Any user can file a bug from the **🐛 Report a Bug** link in the page footer. Each report is emailed to **all active administrators** (and copied to the reporter), and recorded in the audit log with a reference number. The email includes what they described, the severity and page they chose, any screenshot they attached, and an **Environment** block (app version and build, Python/Streamlit/pyodbc versions, the configured and installed ODBC drivers, and the SQL Server version) — so you can usually diagnose without going back and forth.

**System diagnostics.** On the Admin page, expand **🩺 System diagnostics** for a live health readout:

- **Application** — version and build (the git commit and deploy date), plus Python, Streamlit, and pyodbc versions, and the server's local time.
- **Database** — the configured ODBC driver, which SQL Server drivers are actually installed, and the SQL Server version.
- **Backups** — when the last database backup ran, how many exist, their total size, and a ⚠️ flag if the newest is more than about a day old.
- **Scheduled tasks** — click **Check task status** to see whether each of the app's scheduled tasks is running/ready.

This is the first place to look if something seems off (emails not sending, the app behaving oddly) — it surfaces the driver/version mismatches and stale-backup conditions that cause most problems.

---

## Managing users

### Creating a user

Under **Create a new user**, fill in:

- **Username** — what they log in with. Must be unique.
- **Display name** — how their name shows throughout the app.
- **Email** — where their reminder and digest emails go.
- **Temporary password** — hand this to the person however you normally share a starting password.
- **Administrator** — check this only if they should have admin rights.

When they first log in with the temporary password, the app forces them to set their own password, then enroll in two-factor authentication. You don't do anything else for that; it's automatic.

### The buttons on each user

Every user in the list has controls:

- **Reset password** — type a new temporary password and click reset. They'll be forced to choose their own at next login. Use this when someone is locked out or forgot their password.
- **Reset 2FA** — clears their authenticator setup. Use this when someone gets a new phone or loses access to their codes. They re-enroll at next login.
- **Deactivate / Reactivate** — deactivating blocks login without deleting the account or its history. Use this when someone leaves. Reactivate to restore access.
- **Make admin / Remove admin** — grants or removes admin rights. You can't remove your own admin rights (this prevents the last admin from accidentally locking everyone out of administration). Another admin can demote you if needed.

A role change takes effect the next time that person's browser refreshes. A newly promoted user just needs to reload to see the Admin card appear.

### If someone is locked out

Five failed password or code attempts lock an account for 15 minutes. You have two options: tell them to wait it out, or reset their password (which also clears the lock) so they can get in right away.

---

## Managing regions and facilities

The regions and facilities that everyone picks from when tagging issues and projects are fully editable here, so you never need a developer to add a new hospital or rename a region.

On the Admin page, under **Regions & Facilities**:

- **Add a region** with the box at the top.
- Each region is an expandable panel showing its facility count. Inside you can:
  - **Rename** the region.
  - **Delete** the region (this also removes its facilities).
  - **Edit** a facility's name or code, or **Delete** it.
  - **Add** a new facility with a name and a code.

Changes take effect immediately for everyone the next time they open a picker.

**Important:** items already tagged keep their original text. If you rename "Vegas" to "Nevada," an issue that was tagged "Vegas" still displays "Vegas" in its history and on its card. This is on purpose, so historical records reflect what was true at the time. New tagging uses the new name. If you ever need existing records mass-updated to a new name, that's a database change a developer would make.

**Internal Teams and Vendors** work the same way — the sections just below Regions & Facilities let you add, rename, and delete the entries that people pick from in a project's Internal Teams and Vendors sections. As with regions, renaming or deleting one doesn't change projects already tagged with it.

---

## Moderating and the recycle bin

Regular users can delete their own updates, and the person who created an issue or project can delete that item. As an admin, you can delete **anything**:

- **Delete a single history entry** — open any issue or project; each timeline entry has a 🗑 button. Use this to remove a mistaken or inappropriate comment or change. This one is immediate and permanent.
- **Delete an entire issue or project** — near the title there's a **🗑 Delete** button with a confirmation step. This moves the item (and its history) to the **recycle bin** rather than erasing it.

### The recycle bin

Deleted issues and projects collect in the **Recycle bin** section of the Admin page, showing who deleted each one and when. For each you can:

- **Restore** — bring it back to the normal lists, exactly as it was.
- **Delete forever** — a permanent purge (with a confirmation) that also removes its updates and attachments. Use this sparingly; it can't be undone.

Every deletion, restore, and purge is written to the audit log, so there's always a record of who removed or recovered something.

---

## Fix proposals and edit locks

Two things admins can always do, regardless of assignment:

- **Accept or decline any fix proposal.** Normally only the analyst an issue is assigned to sees the Accept/Decline buttons on a proposal. Admins see them on every proposal, which is handy for unassigned issues or when the assignee is out. Accepting moves the issue to In Progress.
- **Take over an edit lock.** When someone else is editing an issue or project, you'll see a **🔓 Take over editing** button under the read-only banner. Click it and the lock is yours immediately; the other person drops to read-only. Use this when someone left an item open and others need to work on it, rather than waiting for the 10-minute idle timeout.

---

## Reassigning work

When someone changes roles or leaves, their open items shouldn't stay stuck to them. Under **Reassign work**, pick the person to move work **From**, the person to move it **To**, and click Reassign. It shows how many open issues and projects that person holds and moves them all at once. The action is audit-logged. (This is the bulk version of what you can also do one item at a time from the update form.)

---

## Email recipients and tools

### Who gets the emails

Under **Email recipients**, every active user has two checkboxes:

- **Digests** — include them on the weekly issue and project digests.
- **Reminders** — include them in the Thursday update nudge.

Toggle either off and that person stops getting that email. Below the list, **Additional digest recipients** lets you add managers or distribution lists that aren't app users (an email plus an optional label) so they receive the digests too. This fully replaces the old config-file recipient list.

The app also sends **immediate notifications** — an assignment email when an issue/project is assigned to someone, a mention email when a user is written as `@username` in a comment, and an **overdue-milestone** email to a project's owner the day one of its milestones slips past its date (once per milestone). Those always go to the affected person, subject to their Reminders setting for the milestone one.

**Major-issue leadership brief.** When a Major issue's brief (Impact / affected regions / current action) is saved, the app notifies a fixed leadership group — **Matt Obenrader, Carly Auriemma, Giovanna Ferro, and Lauren Hartman**. The email content/formatting is being finalized, so for now the app records the notification as *queued* rather than sent; once wiring is complete it becomes a real send. To change the leadership recipients, edit `LEADERSHIP` at the top of `app.py`.

### Testing and sending on demand

Under **Email tools**:

- **Test issue digest / project digest / reminder to me** — sends the real thing to your own address so you can see it, without emailing anyone else and without affecting the scheduled run.
- **Send now to everyone** — fires the real digest to all recipients immediately. It still respects the once-per-week guard, so it won't double up on top of the scheduled Friday send.

### How the scheduled emails run

Scheduled tasks run on the server and send through the internal relay: the **reminder** (Thursday), the **issue digest** (Friday), the **project digest** (Friday, a few minutes later), and a daily **milestone reminder** (each morning) that emails owners about milestones that have just gone overdue. If emails aren't arriving, the usual cause is the mail relay not permitting the server to send — a relay-side allowlist handled by whoever runs the mail system, not something in the app.

---

## The audit log

The **Audit log** section lists the accountability-relevant actions, most recent first: deletions and restores, user management (create, reset password, reset 2FA, activate/deactivate, promote/demote), region and facility deletes, recipient changes, lock takeovers, reassignments, manual email sends, calendar event and milestone changes, and bug reports. Each entry shows who did it and when.

It doesn't record ordinary edits (those already live in each item's own history) — it's the record of the powerful and destructive actions, the things you'd want to answer "who did that?" about later.

---

## Reporting and exports

- **Dashboard** — the Dashboard card (open to everyone) shows counts, aging, and charts by status, region, and assignee.
- **Spreadsheet export** — the Export buttons on the Dashboard download issues or projects as CSV for status reports and leadership decks.
- **Grafana / BI** — the database ships with read-only reporting views (`vw_IssuesFlat`, `vw_IssuesByRegion`, `vw_IssuesByFacility`, `vw_ProjectsFlat`) that flatten the region/facility tags so a dashboard tool can group by region without parsing JSON. Point Grafana at the database with a read-only SQL login and query those. (Standing up Grafana itself is an infrastructure task.)
- **ServiceDesk** — a read-only pull of CA Service Desk Manager ticket status is scaffolded but not yet live; it's waiting on API access. Nothing appears in the app until it's configured.

---

## Backups

The database backs itself up automatically every night, verifies each backup file, and keeps two weeks of history on the server. Because attachments are stored inside the database, they're included in every backup.

Two things worth knowing:

- The backups sit on the same server. That protects against mistakes and corruption, but not against the server's disk failing. The backup script accepts an off-site option (`backup_db.ps1 -OffsiteDir "\\server\share\..."`) to copy each verified backup to a network share — ask your infrastructure team for a share the server can write to, then enable it (see SETUP.md).
- The nightly job is a scheduled task set up during installation. If you ever need to restore, that's a database operation for someone comfortable with SQL Server.

---

## Handling common user problems

**"I forgot my password."** Reset their password on the Admin page. They set a new one at next login.

**"My authenticator stopped working / I got a new phone."** Reset their 2FA. They re-enroll at next login.

**"I'm locked out."** Reset their password to clear the lock, or have them wait 15 minutes.

**"I can't edit an issue, it's greyed out."** Someone else has it open. They can wait for that person to leave, or you can take over the lock if it's urgent.

**"Someone left the company."** Deactivate their account. This keeps all their history intact but blocks login. Don't delete them unless you have a specific reason to.

**"We need a new facility added."** Add it yourself under Regions & Facilities. No developer needed.

---

## Security notes

A few things to keep in mind as the person responsible for the app:

- Everyone with an account can see every issue and project. There's no per-item privacy. Keep that in mind for anything sensitive.
- Access is username + password + two-factor, with a lockout after repeated failures, over HTTPS. Deactivating an account cuts off access, and resetting a password or 2FA immediately invalidates that person's existing signed-in session.
- Attachments are stored as-is and are not scanned for malware. Treat uploads from the same trust level as email attachments from a colleague.
- Keep the admin group small. Every admin can delete any content and reset any account.
- Deleting an issue or project is now recoverable (recycle bin) and every deletion, restore, and purge is written to the audit log — so destructive actions leave a trail and aren't instantly irreversible.
