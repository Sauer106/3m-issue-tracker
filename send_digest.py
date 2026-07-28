"""Weekly digest email. Schedule with Windows Task Scheduler for Friday mornings.

Covers the reporting week that closed at Thursday 2:00 PM: new issues,
resolved issues, all open issues with their latest update, and any open
issues that missed the update deadline.
Safe to re-run: it skips sending if a digest already went out since the cutoff.
"""
import sys
from datetime import timedelta
from html import escape

import db
import reporting
from mailer import send_email


def latest_update_map(issue_ids):
    if not issue_ids:
        return {}
    placeholders = ",".join("?" for _ in issue_ids)
    rows = db.query(
        f"""SELECT u.IssueId, u.Comment, u.CreatedAt, usr.DisplayName AS AuthorName
            FROM IssueUpdates u
            JOIN Users usr ON usr.Id = u.AuthorId
            WHERE u.Id IN (
                SELECT MAX(Id) FROM IssueUpdates
                WHERE IssueId IN ({placeholders}) GROUP BY IssueId
            )""",
        tuple(issue_ids),
    )
    return {r["IssueId"]: r for r in rows}


def issue_table(issues, updates, cutoff):
    if not issues:
        return "<p><i>None.</i></p>"
    rows = ""
    for i in issues:
        upd = updates.get(i["Id"])
        if upd:
            comment = upd["Comment"][:300] + ("..." if len(upd["Comment"]) > 300 else "")
            last = (f"{escape(upd['AuthorName'])} ({upd['CreatedAt']:%m/%d}): "
                    f"{escape(comment)}")
            missed = ' style="background:#fff3cd"' if upd["CreatedAt"] < cutoff - timedelta(days=7) else ""
        else:
            last = "<i>No updates yet</i>"
            missed = ' style="background:#fff3cd"'
        assignee = escape(i["AssignedToName"]) if i["AssignedToName"] else "<i>Unassigned</i>"
        rows += (
            f"<tr{missed}><td>#{i['Id']}</td><td>{escape(i['Title'])}</td>"
            f"<td>{escape(i['Status'])}</td><td>{assignee}</td><td>{last}</td></tr>"
        )
    return (
        '<table border="1" cellpadding="6" cellspacing="0">'
        "<tr><th>ID</th><th>Title</th><th>Status</th>"
        "<th>Assigned To</th><th>Latest Update</th></tr>" + rows + "</table>"
    )


def main():
    config = db.get_config()
    cutoff = reporting.last_deadline(config)       # Thursday 2 PM that just passed
    week_start = cutoff - timedelta(days=7)
    app_url = config["app"].get("app_url", "")

    if db.email_already_sent("digest", "__digest__", cutoff):
        print("Digest already sent for this reporting week. Exiting.")
        return

    open_issues = db.list_issues(statuses=["Open", "In Progress", "Waiting on Solventum", "Hold"])
    new_issues = [i for i in open_issues if i["CreatedAt"] >= week_start]
    resolved = [
        i for i in db.list_issues(statuses=["Closed"])
        if i["ResolvedAt"] and i["ResolvedAt"] >= week_start
    ]
    updates = latest_update_map([i["Id"] for i in open_issues + resolved])
    missed = [
        i for i in open_issues
        if i["Id"] not in updates or updates[i["Id"]]["CreatedAt"] < week_start
    ]

    html = f"""
    <h2>3M Issues & Projects Tracker — Weekly Digest</h2>
    <p>Reporting week: {week_start:%B %d} – {cutoff:%B %d, %Y} (2:00 PM EST cutoff)</p>
    <p><b>{len(open_issues)}</b> open &nbsp;|&nbsp; <b>{len(new_issues)}</b> new this week
    &nbsp;|&nbsp; <b>{len(resolved)}</b> closed this week
    &nbsp;|&nbsp; <b>{len(missed)}</b> missing updates (highlighted below)</p>
    <h3>Open Issues</h3>
    {issue_table(open_issues, updates, cutoff)}
    <h3>Closed This Week</h3>
    {issue_table(resolved, updates, cutoff)}
    <p><a href="{app_url}">Open the 3M Issues & Projects Tracker</a></p>
    """

    recipients = sorted({u["Email"] for u in db.list_users(active_only=True) if u["Email"]})
    extra = config["digest"].get("extra_recipients", "")
    recipients += [e.strip() for e in extra.split(",") if e.strip()]
    if not recipients:
        print("No recipients configured. Exiting.", file=sys.stderr)
        sys.exit(1)

    subject = f"[3M Issues & Projects Tracker] Weekly Digest — {cutoff:%B %d, %Y}"
    send_email(config, recipients, subject, html)
    db.log_email("digest", "__digest__")
    for addr in recipients:
        db.log_email("digest", addr)
    print(f"Digest sent to {len(recipients)} recipient(s).")


if __name__ == "__main__":
    main()
