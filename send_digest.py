"""Weekly issue digest email. Schedule with Windows Task Scheduler for Friday mornings.

Covers the reporting week that closed at Thursday 2:00 PM: new issues,
closed issues, all open issues with their latest update, and any open issues
that missed the update deadline.
Safe to re-run: it skips sending if a digest already went out since the cutoff.
"""
import sys
from datetime import timedelta

import db
import email_style as es
import reporting
from mailer import send_email

OPEN_STATUSES = ["Open", "In Progress", "Waiting on Solventum", "Hold"]


def latest_update_map(issue_ids):
    if not issue_ids:
        return {}
    placeholders = ",".join("?" for _ in issue_ids)
    rows = db.query(
        f"""SELECT u.IssueId AS IID, u.Comment, u.CreatedAt, usr.DisplayName AS AuthorName
            FROM IssueUpdates u
            JOIN Users usr ON usr.Id = u.AuthorId
            WHERE u.Id IN (
                SELECT MAX(Id) FROM IssueUpdates
                WHERE IssueId IN ({placeholders}) GROUP BY IssueId
            )""",
        tuple(issue_ids),
    )
    return {r["IID"]: r for r in rows}


def build_html(open_issues, new_issues, resolved, missed, updates, cutoff, week_start, app_url):
    inner = (
        es.tiles_row(
            es.stat_tile(len(open_issues), "Open", "#1565c0"),
            es.stat_tile(len(new_issues), "New this week", "#00897b"),
            es.stat_tile(len(resolved), "Closed this week", "#2e7d32"),
            es.stat_tile(len(missed), "Missing update", "#e65100" if missed else "#9ca3af"),
        )
        + es.section_row("Open Issues")
        + es.table_row(es.item_table(open_issues, updates, cutoff, flag_stale=True))
        + es.section_row("Closed This Week")
        + es.table_row(es.item_table(resolved, updates, cutoff), bottom=4)
    )
    footer = (f"Reporting week closed {cutoff:%A, %B %d} at 2:00 PM Eastern. "
              "Rows highlighted in amber are missing an update this week. "
              "This is an automated message from the 3M Issues &amp; Projects Tracker.")
    subtitle = (f"Weekly Issue Digest &nbsp;&middot;&nbsp; "
                f"{week_start:%B %d} &ndash; {cutoff:%B %d, %Y}")
    link = app_url.rstrip("/") + "/?page=Issues"
    return es.shell(subtitle, inner, link, footer, button_text="Open Issues", title="3M Issues")


def render(config):
    """Build the digest for the current reporting week. Returns (subject, html)."""
    cutoff = reporting.last_deadline(config)       # Thursday 2 PM that just passed
    week_start = cutoff - timedelta(days=7)
    app_url = config["app"].get("app_url", "")

    open_issues = db.list_issues(statuses=OPEN_STATUSES)
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
    html = build_html(open_issues, new_issues, resolved, missed, updates, cutoff, week_start, app_url)
    subject = f"3M Weekly Issue Digest {cutoff:%B %d, %Y}"
    return subject, html


def main():
    config = db.get_config()
    cutoff = reporting.last_deadline(config)
    if db.email_already_sent("digest", "__digest__", cutoff):
        print("Issue digest already sent for this reporting week. Exiting.")
        return

    subject, html = render(config)
    recipients = db.digest_recipients()
    if not recipients:
        print("No digest recipients. Exiting.", file=sys.stderr)
        sys.exit(1)

    send_email(config, recipients, subject, html)
    db.log_email("digest", "__digest__")
    for addr in recipients:
        db.log_email("digest", addr)
    print(f"Issue digest sent to {len(recipients)} recipient(s).")


if __name__ == "__main__":
    main()
