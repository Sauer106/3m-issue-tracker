# 3M Issues & Projects Tracker — User Guide

Everything a team member needs to use the app. If you administer the app (creating users, managing regions, moderating content), see the **Admin Guide** as well.

The app lives at **https://3mtracking.uhsinc.com**. It works in any modern browser on a company machine. Bookmark it.

---

## Contents

1. [First-time login](#first-time-login)
2. [Two-factor authentication](#two-factor-authentication)
3. [Signing in day to day](#signing-in-day-to-day)
4. [Getting around](#getting-around)
5. [Issues](#issues)
6. [Projects](#projects)
7. [Milestones](#milestones)
8. [Calendar](#calendar)
9. [Regions and facilities](#regions-and-facilities)
10. [The history timeline](#the-history-timeline)
11. [Attachments](#attachments)
12. [The dashboard](#the-dashboard)
13. [Working at the same time as others](#working-at-the-same-time-as-others)
14. [Emails and notifications](#emails-and-notifications)
15. [Getting help and reporting a bug](#getting-help-and-reporting-a-bug)
16. [Frequently asked questions](#frequently-asked-questions)

---

## First-time login

An administrator creates your account and gives you a temporary password. The first time you sign in:

1. Go to the app URL and enter your username and the temporary password.
2. You'll be asked to **choose your own password** right away. Pick something at least 8 characters that you haven't used here before. The temporary one stops working once you set your own.
3. Next you'll set up two-factor authentication (below).

The same "choose a new password" step happens any time an administrator resets your password.

**Locked out?** Five wrong password or code attempts in a row lock your account for 15 minutes. Wait it out, or ask an administrator to reset you.

---

## Two-factor authentication

After your password, the app asks for a six-digit code from an authenticator app. This is a one-time setup, then a quick code entry at each login.

**Setting it up (first login):**

1. On your phone, install an authenticator app if you don't have one. **Microsoft Authenticator** is the usual choice, but Google Authenticator or any similar app works.
2. In the app, a QR code appears. In your authenticator, choose to add an account and scan it. It will show up as **3M Tracker**.
3. Can't scan? There's a text key under the QR code you can type into the authenticator by hand.
4. Enter the six-digit code your app is showing and confirm. That's it, you're in.

**Every login after that:** enter your username and password, then the current six-digit code from your authenticator. The code changes every 30 seconds; the app accepts the one just before and after too, so a few seconds of clock drift is fine.

**Lost or replaced your phone?** Ask an administrator to reset your 2FA. Your next login will walk you through enrolling again from scratch.

---

## Signing in day to day

Username, password, six-digit code, and you're in. Once signed in you stay signed in for about half a day, so refreshing the page or coming back a bit later won't throw you back to the login screen. Close the browser and come back the next morning and you'll sign in fresh.

There's a **Log out** button at the bottom of the sidebar whenever you want to end your session immediately.

---

## Getting around

The sidebar on the left is your navigation. It shows a card for each area:

- **Issues** — the running list of issues.
- **Projects** — the running list of projects.
- **Calendar** — a month view of scheduled events (go-lives, deadlines).
- **Dashboard** — metrics and charts across all the work.
- **Admin** — only appears if you're an administrator.

Click a card to switch areas. The card you're on is highlighted. Your name and the current update deadline show at the top of the sidebar.

At the very bottom of every page there's a small footer showing the version and two links: **❓ Help & FAQ** and **🐛 Report a Bug** (see [Getting help](#getting-help-and-reporting-a-bug)).

---

## Issues

An issue is a problem, request, or item of work being tracked. The Issues page is a list of cards, newest first.

### Reading the list

Each card shows the issue number and title, plus quick badges:

- A colored **status** badge (Open, In Progress, and so on).
- A red **Major** badge if the issue is flagged major.
- A **due date** badge, which turns into a red **⏰ Overdue** badge once the date passes on an open issue.
- **Solventum** and **ServiceDesk** ticket numbers, if they've been entered.
- The **regions** it covers, and a count if only some facilities in those regions are selected.
- A line showing who it's assigned to, who reported it, and when it was last touched.

### Filtering and searching

At the top of the list:

- **Status** — pick which statuses to show. By default you see everything that isn't closed.
- **Search** — type to match the title or description.
- **Mine only** — show just the issues where you're one of the assignees.
- **Needs update** — show only the Open / In Progress issues with no update since the last Thursday 2:00 PM deadline (the same ones the reminder email chases).

### Creating an issue

Click **➕ New Issue** at the top right of the Issues page. A window opens where you fill in:

- **Title** and **Description** (both required).
- **Regions and Facilities** (see that section below).
- **Have all regions been checked for this issue?** — a required **Yes / No / N/A**. If you pick **No** or **N/A**, briefly explain why. This makes sure region coverage is considered up front.
- **Assignee(s)** — assign one or more people (leave empty for unassigned). Everyone assigned sees it under Mine only and gets the assignment and reminder emails.
- **Solventum Ticket #** and **ServiceDesk Ticket #** — optional, add them if the issue relates to a vendor or help-desk ticket.
- **Major issue** — check this if it's a significant, widespread issue. Checking it opens a short **leadership brief** right here (see [Major issues](#major-issues)): an **Impact** (required) and the **Current action**. The affected regions come from your Regions/Facilities selection.
- **Due date** — optional target date. Once it passes on an open issue, the card shows a red Overdue badge.

Submit and the issue appears in the list. If you assign it to someone, they get an email letting them know.

### Opening and updating an issue

Click **Open** on any card. The detail view shows the full description, the badges, and the history. To make a change, use the **Add an update** form:

- Type a **comment** about what's happening. Mention a teammate with **@username** and they'll get an email pointing them to the issue.
- Change the **status** or the **assignee(s)** (newly-added people are emailed).
- Update the **Solventum** or **ServiceDesk** ticket numbers.
- Toggle the **Major** flag or set a **due date**.

Save the update and everything you changed is recorded in the history, with your name and the time. You don't have to write a comment just to change a field; a field change on its own is recorded too.

Use the **← All issues** link to go back to the list.

### Bulk actions

Need to act on several issues at once? Open **Bulk actions** at the top of the Issues page, pick the issues from the list, choose **Change status** or **Reassign**, and click Apply. Each change is recorded on those issues just like a normal update. (Closing isn't a bulk action — every close goes through the region-rollout check below, so you close issues one at a time.)

### Statuses

Issues move through these:

- **Open** — logged, not yet being worked.
- **In Progress** — someone is actively on it.
- **Waiting on Solventum** — the ball is in Solventum's court. **This status requires a Solventum ticket number.** If you set it without one, the app won't save until you add the ticket #.
- **Hold** — intentionally paused.
- **Closed** — done. **Closing always asks the region-rollout question** (below).

### Closing an issue — region rollout

Whenever you close **any** issue, the app stops and asks: **is the fix applied across all regions?**

- **Has been** — it's already everywhere.
- **Will be** — planned; you enter the **date** it will reach the other regions.
- **No** — you must briefly explain which regions are excluded and why.

Your answer (and the date or reason) goes into the history and onto the issue. This makes sure a fix is either confirmed everywhere, scheduled, or documented where it wasn't.

### Major issues

Check the **Major** flag for a significant issue that affects many sites. Major issues wear a red badge so they stand out in the list, and they carry a **leadership brief**.

- The brief has an **Impact**, the **Current action**, and the **affected regions** (taken automatically from the issue's Regions/Facilities).
- You can fill it in when you create the issue, or on the issue afterward — the brief is an editable section on every Major issue.
- Saving the brief notifies leadership — **Matt Obenrader, Carly Auriemma, Giovanna Ferro, and Lauren Hartman**. (Email delivery is being finalized; until then the app shows the notification as queued.)

### Proposing a fix

If you have an idea for how to fix an issue, click **💡 Propose Fix** on the issue and describe it. Your proposal lands in the history with an amber **Fix proposal** badge.

The person the issue is assigned to (or an administrator) then sees **✅ Accept** and **❌ Decline** buttons on your proposal:

- **Accept** turns the badge green and, if the issue isn't already In Progress, moves it there.
- **Decline** turns the badge red.

Either way the decision is recorded with who made it.

---

## Projects

Projects work almost exactly like issues, with a few differences. Use the **Projects** card in the sidebar, and **➕ New Project** to create one.

What's different from issues:

- Projects have a **Summary** instead of a description.
- Their statuses are **Planned, In Progress, On Hold, Completed, Cancelled**.
- There's no Major flag and no fix proposals (those are for issues).
- The person who made it is the **creator** rather than a reporter.

- Projects can have **milestones** (see below); issues use a single due date instead.
- Projects can record the **internal teams + analysts** and the **vendors** involved (see below).

Everything else is the same: assignee, Solventum and ServiceDesk tickets, regions and facilities, attachments, the update form, and the history timeline all behave just like issues.

**Teams and vendors.** Open a project to find the collapsible **👥 Internal Teams** and **🏢 Vendors** sections. Each team or vendor is added **once** (the picker only offers ones not already on the project), then you add its **people inside it** — click a team or vendor to open it and add **analysts** (for teams) or **contacts** (for vendors) with their **name, email, and phone**. A vendor also carries a **role and status**. Add/remove is recorded in the project history. Administrators curate the master team and vendor lists on the Admin page.

---

## Milestones

A project can have as many **milestones** as you like — named checkpoints, each with an optional target date (for example "Build complete", "UAT", "Go-Live"). Open a project to find the **🎯 Milestones** section.

- **Add one** with the small form at the bottom: type a name, optionally pick a target date, and click **Add**.
- **Mark it done** with the **Done** button when it's finished (it turns into a green ✓). Changed your mind? **Reopen** it.
- **Remove one** with the 🗑 button.

On the Projects list, each project card shows its **next open milestone** as a chip — red if the date has already passed. Adding, completing, or removing a milestone is recorded in the project's history, and overdue milestones show up on the dashboard and in the weekly project digest (their owner also gets an email the day one slips past its date).

---

## Calendar

The **Calendar** card is a month view of scheduled **events** — things like go-lives and deadlines, optionally tied to one or more projects.

- Move between months with **◀ Prev** / **Next ▶**, or jump back with **Today**. Today's date is outlined.
- Each event shows as a small colored bar on its day: **green** Go-Live, **red** Deadline, **orange** Projected Go-Live, **blue** Testing Event, **purple** Update. Click a bar to open the event. Below the grid, an **Agenda** lists the month's events with an **Open** button on each.
- **➕ New Event** creates one: a title, a date, a category, and a **required resource** — one or more people from the user list. Optionally set a **start and end time** (12-hour). For a **multi-day** event, set an end date and choose which **days of the week** it runs, so a weekday-only window skips weekends on the grid. You can also add a description and link projects.
- Events show their **resource(s)** as 👤 chips on the agenda, the dashboard, and the event view.
- Opening an event shows its details and a button to **open each linked project**. From a project, the **📅 Calendar** section lists its linked events with a button to open each — so you can hop between an event and its projects in either direction.

You can edit or delete an event you created; administrators can edit any. Others see it read-only.

---

## Regions and facilities

Issues and projects can be tagged with the regions and facilities they affect. You'll see two dropdown buttons, **🌎 Regions** and **🏥 Facilities**, each opening a list of checkboxes.

How it works:

- **Pick your regions first.** The Facilities button stays greyed out until at least one region is checked.
- Once you check a region, the Facilities list fills in with just that region's facilities, grouped under the region name.
- **All Regions** checks every region (and every facility) in one click. **All Facilities** checks everything within the regions you've selected.
- Unchecking a region removes its facilities automatically. Unchecking a region's last remaining facility removes the region too, so the tag always reflects reality.

Below the buttons, a summary shows your chosen regions as chips. If you selected only some of a region's facilities, you'll also see a small "x of y facilities" note; if you took all of them, just the region shows.

To fix a wrong pick, open the dropdown and uncheck the box. No need to hunt for a tiny remove icon.

---

## The history timeline

Every issue and project keeps a running history. Each entry is a card on a vertical timeline showing:

- **Who** made it, as a colored initials avatar, and **when**, in your own timezone with a friendly "3 hrs ago" style time.
- A badge telling you what kind of entry it is: **💬 Comment**, **💡 Fix proposal**, or **✏️ Details** when fields were changed.
- **Status changes** shown as colored chips, like `Open → In Progress`.
- **Field changes** listed out, so you can see exactly what changed, from what, to what (for example a ticket number being added, or the assignee changing). This is the audit trail: it always shows who changed each field.

Times adjust to whoever is looking. If a teammate is in Central time and you're in Eastern, you each see the times in your own zone.

### Removing your own entries

You can delete an update you posted using the 🗑 button next to it. You can also delete an entire issue or project you created (there's a **🗑 Delete** button with a confirmation near the title). Administrators can delete anything. Deleting an issue or project moves it to a recycle bin rather than erasing it, so an administrator can restore it if it was a mistake.

---

## Attachments

Every issue and project has a **📎 Attachments** area under its description.

- **Add files** by dropping them into the uploader or browsing, then clicking Upload. You can add several at once. Each file can be up to 25 MB.
- **Download** any attachment with the ⬇ button.
- **Delete** files you uploaded with the 🗑 button (administrators can delete any).

Uploads and deletions show up in the history, so there's a record of what was attached and when.

---

## The dashboard

The **Dashboard** card gives you the big picture across all issues and projects:

- Headline numbers: open issues, overdue issues, closed this week, needing an update, active projects, and overdue milestones.
- How old the open issues are, on average and at the oldest.
- **⚠️ Overdue milestones** — any project milestone that's past its date, with how many days overdue and a button to open the project.
- **Upcoming — next 30 days** — the calendar events coming up, each linking to the event.
- Charts of issues by status, open issues by region and by assignee, and projects by status.
- An **Export** section with buttons to download the issues or projects as a spreadsheet (they open in Excel), handy for status reports.

---

## Working at the same time as others

The app updates live, so you don't need to refresh. New issues, comments, and status changes from your teammates appear on their own within a few seconds.

**Seeing who else is here:** when you open an issue or project, a blue **👀 is viewing** chip shows anyone else who has it open at the same time.

**Editing locks:** to keep two people from overwriting each other, only one person edits an item at a time. The first person to open it can edit; anyone who opens it after that sees a read-only view with a note saying who's editing. You can still read everything and download attachments in read-only mode.

The lock frees up on its own:

- When the person editing leaves the page, the lock releases within a few seconds and a waiting viewer's page switches to editable automatically.
- If the person editing just sits idle for 10 minutes without doing anything, the lock passes to someone who's waiting.

Administrators can take over a lock immediately if they need to.

---

## Emails and notifications

**Scheduled emails:**

- **Thursday morning reminder** — if you have an open issue with no update since last week's deadline, you get a note listing them. Updates are due by **Thursday 2:00 PM**. The button drops you straight onto your overdue issues.
- **Friday morning issue digest** — a summary of the week's issues to everyone: what's open, new, closed, and missing an update.
- **Friday morning project digest** — a separate summary of active and recently completed projects.

The Friday project digest also flags any **overdue milestones** and the **upcoming events** for the next 30 days.

**Notifications (sent right away):**

- **Assignment** — when an issue or project is assigned to you (one of possibly several assignees), you get an email with a link to it.
- **Mention** — when someone writes **@yourusername** in a comment, you get an email with the comment and a link.
- **Overdue milestone** — if a project assigned to you has a milestone slip past its date, you get an email (once per milestone) with a link to the project.

Every email button takes you straight to the relevant issue, project, or list. An administrator can control who receives the digests and reminders.

---

## Getting help and reporting a bug

Every page has a small footer at the very bottom with two links:

- **❓ Help & FAQ** — a quick reference with answers to the most common questions (signing in, 2FA, statuses, regions, and more). Good for a fast refresher without leaving the page.
- **🐛 Report a Bug** — found something wrong? Tell us here. Pick where it happened and how bad it is, describe what you expected versus what happened, and optionally attach a screenshot. It goes straight to the administrators (and you get a copy), with a reference number so it can be followed up.

---

## Frequently asked questions

**I forgot my password.** Ask an administrator to reset it. You'll set a new one at your next login.

**I got a new phone and my authenticator codes don't work.** Ask an administrator to reset your 2FA, then re-enroll at your next login.

**The page says I'm locked out.** Five failed attempts locks the account for 15 minutes. Wait, then try again, or ask an administrator.

**I opened an issue and everything is greyed out.** Someone else is editing it. You're in read-only mode until they leave or go idle. Their name is in the banner at the top.

**A refresh logged me out.** That shouldn't happen within about half a day of signing in. If it does, sign in again; if it keeps happening, tell an administrator.

**Can I edit a ticket number after creating the issue?** Yes. Open the issue and change it in the update form. The change is recorded in the history.

**Why can't I set "Waiting on Solventum"?** That status needs a Solventum ticket number. Enter one in the update form, then save.

**Who can see my issues?** Everyone with an account sees all issues and projects. This is a shared team tool.

**How do I get someone's attention on an issue?** Assign it to them, or write **@theirusername** in a comment. Either one emails them a link.

**Can I get a due date reminder?** Issues with a due date show an Overdue badge once the date passes, and overdue issues are counted on the Dashboard. The Thursday reminder still keys off the weekly update deadline, not the due date.
