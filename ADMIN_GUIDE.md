# 3M Issues & Projects Tracker — Admin Guide

For administrators. This covers everything a regular user can do (see the **User Guide** for those features) plus the extra powers admins have: managing users, curating the regions and facilities list, moderating content, and keeping the app healthy.

For installing, TLS certificates, the reverse proxy, and other server work, see **SETUP.md**. This guide focuses on what you do from inside the app.

---

## Contents

1. [Who is an admin](#who-is-an-admin)
2. [The Admin page](#the-admin-page)
3. [Managing users](#managing-users)
4. [Managing regions and facilities](#managing-regions-and-facilities)
5. [Moderating issues, projects, and updates](#moderating-issues-projects-and-updates)
6. [Fix proposals and edit locks](#fix-proposals-and-edit-locks)
7. [Emails](#emails)
8. [Backups](#backups)
9. [Handling common user problems](#handling-common-user-problems)
10. [Security notes](#security-notes)

---

## Who is an admin

Admins have an **Admin** card in their sidebar that regular users don't see. The first admin is created when the app is installed. After that, any admin can promote or demote others.

The rule of thumb: keep admin rights to the few people who actually need to manage accounts and settings. Everything destructive (deleting issues, taking over locks, resetting accounts) is available to every admin.

---

## The Admin page

Click **Admin** in the sidebar. The page has two parts:

- **User management** — create accounts and manage existing ones.
- **Regions & Facilities** — curate the list of regions and facilities that everyone tags issues and projects with.

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

---

## Moderating issues, projects, and updates

Regular users can delete their own updates, and the person who created an issue or project can delete that item. As an admin, you can delete **anything**:

- **Delete a single history entry** — open any issue or project; each timeline entry has a 🗑 button. Use this to remove a mistaken or inappropriate comment or change.
- **Delete an entire issue or project** — near the title there's a **🗑 Delete** button with a confirmation step. This removes the item and its whole history.

Deletions are permanent and are not themselves logged. Treat them as a real cleanup tool, not an undo button, and lean on deactivating users rather than deleting their work where you can.

---

## Fix proposals and edit locks

Two things admins can always do, regardless of assignment:

- **Accept or decline any fix proposal.** Normally only the analyst an issue is assigned to sees the Accept/Decline buttons on a proposal. Admins see them on every proposal, which is handy for unassigned issues or when the assignee is out. Accepting moves the issue to In Progress.
- **Take over an edit lock.** When someone else is editing an issue or project, you'll see a **🔓 Take over editing** button under the read-only banner. Click it and the lock is yours immediately; the other person drops to read-only. Use this when someone left an item open and others need to work on it, rather than waiting for the 10-minute idle timeout.

---

## Emails

The app sends two scheduled emails, both to the addresses on active user accounts:

- **Reminder** — Thursday morning. Lists each person's open issues that haven't been updated since the previous Thursday 2:00 PM deadline.
- **Digest** — Friday morning. A summary of the reporting week for everyone.

They run as scheduled tasks on the server and send through the internal mail relay. Settings (the relay host, the from address, and any extra digest recipients) live in `config.ini`. Both scripts are safe to run by hand for testing and won't double-send, because they check what's already gone out.

If emails aren't arriving, the most common cause is the mail relay not permitting the server to send. That's a relay-side allowlist, handled by whoever runs the mail system, not something in the app.

---

## Backups

The database backs itself up automatically every night, verifies each backup file, and keeps two weeks of history on the server. Because attachments are stored inside the database, they're included in every backup.

Two things worth knowing:

- The backups sit on the same server. That protects against mistakes and corruption, but not against the server's disk failing. Ideally those backup files also get swept to a network location by whatever backup system your infrastructure team runs.
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
