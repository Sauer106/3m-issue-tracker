"""Update-reminder email. Schedule with Windows Task Scheduler for Thursday mornings.

Finds open issues with no update since the previous Thursday 2:00 PM deadline
and emails the responsible person (assignee, falling back to reporter).
Safe to re-run: it skips anything already reminded today via EmailLog.
"""
import sys
from collections import defaultdict
from html import escape

import db
import email_style as es
import reporting
from mailer import send_email
from send_digest import latest_update_map


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


def main():
    config = db.get_config()
    deadline = reporting.upcoming_deadline(config)
    week_start = reporting.last_deadline(config)
    today_start = reporting._now_local(config).replace(hour=0, minute=0, second=0, microsecond=0)
    app_url = config["app"].get("app_url", "")

    issues = find_delinquent_issues(week_start)
    if not issues:
        print("No delinquent issues. Nothing to send.")
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


if __name__ == "__main__":
    main()
