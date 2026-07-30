"""Update-reminder email. Schedule with Windows Task Scheduler for Thursday mornings.

Finds open issues with no update since the previous Thursday 2:00 PM deadline
and emails the responsible person (assignee, falling back to reporter).
Safe to re-run: it skips anything already reminded today via EmailLog.
"""
import sys
from collections import defaultdict
from datetime import datetime
from html import escape

import db
import email_style as es
import reporting
from mailer import send_email
from send_digest import latest_update_map

# Far-past cutoff: milestone-overdue notices fire once per milestone, ever.
_EVER = datetime(2000, 1, 1)


def find_delinquent_issues(week_start):
    return db.query(
        db.ISSUE_SELECT
        + """ WHERE i.Status IN ('Open', 'In Progress')
              AND i.DeletedAt IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM IssueUpdates u
                  WHERE u.IssueId = i.Id AND u.CreatedAt >= ?
              )
              ORDER BY i.Id""",
        (week_start,),
    )


def build_body(user_name, issues, deadline, app_url):
    updates = latest_update_map([i["Id"] for i in issues])
    count = len(issues)
    intro = (
        f"Hi {escape(user_name)}, you have <b>{count} issue{'s' if count != 1 else ''}</b> "
        "assigned to you (or reported by you and unassigned) with <b>no update this week</b>. "
        f"Please add an update by <b>{deadline:%A, %B %d} at 2:00 PM Eastern</b> "
        "so they make Friday's digest."
    )
    inner = (
        es.intro_row(intro)
        + es.section_row("Needs an update from you")
        + es.table_row(es.item_table(issues, updates), bottom=4)
    )
    footer = ("You are receiving this because these issues are assigned to you or you "
              "reported them. This is an automated message from the 3M Issues &amp; Projects Tracker.")
    subtitle = f"Update Reminder &nbsp;&middot;&nbsp; due {deadline:%B %d}"
    link = app_url.rstrip("/") + "/?page=Issues&amp;mine=1&amp;needsupdate=1"
    return es.shell(subtitle, inner, link, footer, button_text="Open My Issues",
                    title="3M Issues")


def build_milestone_body(user_name, rows, today, app_url):
    th = (f'padding:8px 10px;font-family:{es.FONT};font-size:11px;color:{es.MUTED};'
          f'text-transform:uppercase;letter-spacing:.03em;text-align:left;'
          f'background:#f3f4f6;border-bottom:2px solid {es.BORDER};')
    body = ""
    for idx, m in enumerate(rows):
        td = (f'padding:9px 10px;font-family:{es.FONT};font-size:13px;color:{es.INK};'
              f'border-bottom:1px solid {es.BORDER};vertical-align:top;')
        bg = "#ffffff" if idx % 2 == 0 else "#fafbfc"
        days = (today - m["DueDate"]).days
        body += (f'<tr style="background:{bg};">'
                 f'<td style="{td}font-weight:bold;">{escape(m["ProjectTitle"])}</td>'
                 f'<td style="{td}">{escape(m["Name"])}</td>'
                 f'<td style="{td}white-space:nowrap;color:{es.MUTED};">{m["DueDate"]:%b %d, %Y}</td>'
                 f'<td style="{td}white-space:nowrap;color:#c62828;font-weight:bold;">'
                 f'{days} day{"s" if days != 1 else ""}</td></tr>')
    table = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
             f'style="border-collapse:collapse;border:1px solid {es.BORDER};">'
             f'<tr><th style="{th}">Project</th><th style="{th}">Milestone</th>'
             f'<th style="{th}">Due</th><th style="{th}">Overdue</th></tr>{body}</table>')
    count = len(rows)
    intro = (f"Hi {escape(user_name)}, you have <b>{count} overdue milestone"
             f"{'s' if count != 1 else ''}</b> on project(s) assigned to you. "
             "Please update the target date or mark them done.")
    inner = (es.intro_row(intro) + es.section_row("Overdue Milestones")
             + es.table_row(table, bottom=4))
    footer = ("You are receiving this because these projects are assigned to you. "
              "This is an automated message from the 3M Issues &amp; Projects Tracker.")
    link = app_url.rstrip("/") + "/?page=Projects"
    return es.shell("Overdue Milestones", inner, link, footer, button_text="Open Projects",
                    title="3M Projects")


def send_milestone_reminders(config, app_url):
    """Email each project owner once about any milestone that has gone overdue."""
    overdue = db.list_overdue_milestones()
    if not overdue:
        print("No overdue milestones.")
        return
    today = reporting._now_local(config).date()
    users = {u["Id"]: u for u in db.list_users()}
    by_owner = defaultdict(list)
    for m in overdue:
        owner = users.get(m["AssignedTo"]) if m["AssignedTo"] else None
        if not (owner and owner["IsActive"] and owner["Email"] and owner["ReceivesReminders"]):
            print(f"Skipping milestone #{m['Id']}: owner inactive, unassigned, no email, "
                  "or reminders off.")
            continue
        if not db.email_already_sent("milestone_overdue", owner["Email"], _EVER, m["Id"]):
            by_owner[m["AssignedTo"]].append(m)

    sent = 0
    for owner_id, rows in by_owner.items():
        owner = users[owner_id]
        try:
            send_email(config, [owner["Email"]], "3M Overdue Milestones",
                       build_milestone_body(owner["DisplayName"], rows, today, app_url))
        except Exception as exc:
            print(f"FAILED milestone reminder to {owner['Email']}: {exc}", file=sys.stderr)
            continue
        for m in rows:
            db.log_email("milestone_overdue", owner["Email"], m["Id"])
        sent += 1
        print(f"Reminded {owner['Email']} about {len(rows)} overdue milestone(s).")
    print(f"{sent} milestone reminder email(s) sent.")


def main():
    config = db.get_config()
    deadline = reporting.upcoming_deadline(config)
    week_start = reporting.last_deadline(config)
    today_start = reporting._now_local(config).replace(hour=0, minute=0, second=0, microsecond=0)
    app_url = config["app"].get("app_url", "")

    issues = find_delinquent_issues(week_start)
    if not issues:
        print("No delinquent issues.")
        send_milestone_reminders(config, app_url)
        return

    users = {u["Id"]: u for u in db.list_users()}
    by_user = defaultdict(list)
    for issue in issues:
        owner_id = issue["AssignedTo"] or issue["ReportedBy"]
        owner = users.get(owner_id)
        if owner and owner["IsActive"] and owner["Email"] and owner["ReceivesReminders"]:
            by_user[owner_id].append(issue)
        else:
            print(f"Skipping issue #{issue['Id']}: owner inactive, no email, or reminders off.")

    sent = 0
    for owner_id, owner_issues in by_user.items():
        owner = users[owner_id]
        to_send = [
            i for i in owner_issues
            if not db.email_already_sent("reminder", owner["Email"], today_start, i["Id"])
        ]
        if not to_send:
            continue
        subject = "3M Update Reminder"
        try:
            send_email(config, [owner["Email"]], subject,
                       build_body(owner["DisplayName"], to_send, deadline, app_url))
        except Exception as exc:
            print(f"FAILED sending to {owner['Email']}: {exc}", file=sys.stderr)
            continue
        for issue in to_send:
            db.log_email("reminder", owner["Email"], issue["Id"])
        sent += 1
        print(f"Reminded {owner['Email']} about {len(to_send)} issue(s).")

    print(f"Done. {sent} reminder email(s) sent for {len(issues)} delinquent issue(s).")
    send_milestone_reminders(config, app_url)


if __name__ == "__main__":
    main()
