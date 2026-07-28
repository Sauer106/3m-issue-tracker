"""Reporting-week math.

The team's update deadline is Thursday 2:00 PM Eastern. A "reporting week" runs
from one Thursday 2:00 PM to the next. The Friday digest covers the week that
just closed; Thursday reminders cover the week about to close.

Timestamps in the database are SQL Server local time, so datetimes returned
here are naive local times (the server clock is assumed to match the timezone
configured in config.ini -- America/New_York by default).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DEADLINE_WEEKDAY = 3   # Thursday (Monday = 0)
DEADLINE_HOUR = 14     # 2:00 PM


def _now_local(config):
    tz = ZoneInfo(config["app"].get("timezone", "America/New_York"))
    return datetime.now(tz).replace(tzinfo=None)


def upcoming_deadline(config):
    """The next Thursday 2:00 PM at or after now."""
    now = _now_local(config)
    days_ahead = (DEADLINE_WEEKDAY - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=DEADLINE_HOUR, minute=0, second=0, microsecond=0
    )
    if candidate < now:
        candidate += timedelta(days=7)
    return candidate


def last_deadline(config):
    """The most recent Thursday 2:00 PM at or before now."""
    return upcoming_deadline(config) - timedelta(days=7)
