"""Daily overdue-milestone reminder.

Emails each project owner the day one of their milestones goes overdue. Schedule
it daily; the once-per-milestone dedup (EmailLog) makes re-runs safe, so a
milestone is only ever emailed once. The weekly reminder job runs the same pass
as a fallback.
"""
import db
from send_reminders import send_milestone_reminders


def main():
    config = db.get_config()
    app_url = config["app"].get("app_url", "")
    send_milestone_reminders(config, app_url)


if __name__ == "__main__":
    main()
