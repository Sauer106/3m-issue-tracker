"""Weekly project digest email. Schedule with Windows Task Scheduler for Friday mornings.

A snapshot of project work: active projects with their latest update, projects
started this week, and projects completed this week. Sent separately from the
issue digest so each reads cleanly on its own.
Safe to re-run: it skips sending if a project digest already went out since the cutoff.
"""
import sys
from datetime import datetime, timedelta

import db
import email_style as es
import reporting
from mailer import send_email

ACTIVE_STATUSES = ["Planned", "In Progress", "On Hold"]
UPCOMING_DAYS = 30
EVENT_PILL_COLORS = {"Go-Live": "#2e7d32", "Deadline": "#c62828", "Projected Go-Live": "#e65100"}


def upcoming_table(events):
    """An email-safe table of upcoming calendar events."""
    if not events:
        return ""
    rows = sorted(events, key=lambda e: (e["EventDate"], e["EventTime"] or datetime.min.time()))
    th = (f'padding:8px 10px;font-family:{es.FONT};font-size:11px;color:{es.MUTED};'
          f'text-transform:uppercase;letter-spacing:.03em;text-align:left;'
          f'background:#f3f4f6;border-bottom:2px solid {es.BORDER};')
    body = ""
    for idx, e in enumerate(rows):
        td = (f'padding:9px 10px;font-family:{es.FONT};font-size:13px;color:{es.INK};'
              f'border-bottom:1px solid {es.BORDER};vertical-align:top;')
        bg = "#ffffff" if idx % 2 == 0 else "#fafbfc"
        when = f"{e['EventDate']:%a %b %d}" + (f" {e['EventTime']:%#I:%M %p}" if e["EventTime"] else "")
        what = es.pill(e["Category"], EVENT_PILL_COLORS.get(e["Category"], "#546e7a"))
        title = es.escape(e["Title"])
        if e["EndDate"] and e["EndDate"] != e["EventDate"]:
            title += f' <span style="color:{es.MUTED};">(through {e["EndDate"]:%b %d})</span>'
        projects = ", ".join(p["Title"] for p in db.list_event_projects(e["Id"]))
        body += (f'<tr style="background:{bg};">'
                 f'<td style="{td}white-space:nowrap;color:{es.MUTED};">{when}</td>'
                 f'<td style="{td}white-space:nowrap;">{what}</td>'
                 f'<td style="{td}font-weight:bold;">{title}</td>'
                 f'<td style="{td}color:{es.MUTED};">{es.escape(projects)}</td>'
                 f'</tr>')
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;border:1px solid {es.BORDER};">'
        f'<tr><th style="{th}">When</th><th style="{th}">Type</th><th style="{th}">What</th>'
        f'<th style="{th}">Projects</th></tr>{body}</table>'
    )


def latest_update_map(project_ids):
    if not project_ids:
        return {}
    placeholders = ",".join("?" for _ in project_ids)
    rows = db.query(
        f"""SELECT u.ProjectId AS PID, u.Comment, u.CreatedAt, usr.DisplayName AS AuthorName
            FROM ProjectUpdates u
            JOIN Users usr ON usr.Id = u.AuthorId
            WHERE u.Id IN (
                SELECT MAX(Id) FROM ProjectUpdates
                WHERE ProjectId IN ({placeholders}) GROUP BY ProjectId
            )""",
        tuple(project_ids),
    )
    return {r["PID"]: r for r in rows}


def completed_this_week_ids(week_start):
    """Projects whose status changed to Completed within the reporting week."""
    rows = db.query(
        """SELECT DISTINCT ProjectId AS Id FROM ProjectUpdates
           WHERE StatusChange LIKE '%-> Completed' AND CreatedAt >= ?""",
        (week_start,),
    )
    return {r["Id"] for r in rows}


def build_html(active, new_projects, completed, on_hold, updates, upcoming_html,
               cutoff, week_start, app_url):
    upcoming_section = ""
    if upcoming_html:
        upcoming_section = (es.section_row(f"Upcoming — Next {UPCOMING_DAYS} Days")
                            + es.table_row(upcoming_html))
    inner = (
        es.tiles_row(
            es.stat_tile(len(active), "Active", "#1565c0"),
            es.stat_tile(len(new_projects), "New this week", "#00897b"),
            es.stat_tile(len(completed), "Completed this week", "#2e7d32"),
            es.stat_tile(len(on_hold), "On hold", "#e65100" if on_hold else "#9ca3af"),
        )
        + upcoming_section
        + es.section_row("Active Projects")
        + es.table_row(es.item_table(active, updates))
        + es.section_row("Completed This Week")
        + es.table_row(es.item_table(completed, updates), bottom=4)
    )
    footer = (f"A snapshot of project work as of {cutoff:%A, %B %d}. "
              "This is an automated message from the 3M Issues &amp; Projects Tracker.")
    subtitle = (f"Weekly Project Digest &nbsp;&middot;&nbsp; "
                f"{week_start:%B %d} &ndash; {cutoff:%B %d, %Y}")
    link = app_url.rstrip("/") + "/?page=Projects"
    return es.shell(subtitle, inner, link, footer, button_text="Open Projects", title="3M Projects")


def render(config):
    """Build the project digest for the current reporting week. Returns (subject, html)."""
    cutoff = reporting.last_deadline(config)
    week_start = cutoff - timedelta(days=7)
    app_url = config["app"].get("app_url", "")

    active = db.list_projects(statuses=ACTIVE_STATUSES)
    new_projects = [p for p in active if p["CreatedAt"] >= week_start]
    on_hold = [p for p in active if p["Status"] == "On Hold"]
    done_ids = completed_this_week_ids(week_start)
    completed = [p for p in db.list_projects(statuses=["Completed"]) if p["Id"] in done_ids]
    updates = latest_update_map([p["Id"] for p in active + completed])
    up_start = cutoff.date()
    up_end = up_start + timedelta(days=UPCOMING_DAYS)
    upcoming_html = upcoming_table(db.list_events(up_start, up_end))
    html = build_html(active, new_projects, completed, on_hold, updates, upcoming_html,
                      cutoff, week_start, app_url)
    subject = f"3M Weekly Project Digest {cutoff:%B %d, %Y}"
    return subject, html


def main():
    config = db.get_config()
    cutoff = reporting.last_deadline(config)
    if db.email_already_sent("project_digest", "__pdigest__", cutoff):
        print("Project digest already sent for this reporting week. Exiting.")
        return

    subject, html = render(config)
    recipients = db.digest_recipients()
    if not recipients:
        print("No digest recipients. Exiting.", file=sys.stderr)
        sys.exit(1)

    send_email(config, recipients, subject, html)
    db.log_email("project_digest", "__pdigest__")
    for addr in recipients:
        db.log_email("project_digest", addr)
    print(f"Project digest sent to {len(recipients)} recipient(s).")


if __name__ == "__main__":
    main()
