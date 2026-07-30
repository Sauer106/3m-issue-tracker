"""Reporting-week date math: the Thursday 2 PM deadline logic."""
from datetime import timedelta

import reporting

CONFIG = {"app": {"timezone": "America/New_York"}}


def test_upcoming_deadline_is_thursday_2pm_in_future():
    now = reporting._now_local(CONFIG)
    d = reporting.upcoming_deadline(CONFIG)
    assert d.weekday() == reporting.DEADLINE_WEEKDAY   # Thursday
    assert (d.hour, d.minute, d.second) == (reporting.DEADLINE_HOUR, 0, 0)
    assert d >= now


def test_last_deadline_is_previous_thursday_2pm():
    now = reporting._now_local(CONFIG)
    last = reporting.last_deadline(CONFIG)
    assert last.weekday() == reporting.DEADLINE_WEEKDAY
    assert (last.hour, last.minute) == (reporting.DEADLINE_HOUR, 0)
    assert last <= now


def test_deadlines_are_one_week_apart():
    assert reporting.upcoming_deadline(CONFIG) - reporting.last_deadline(CONFIG) == timedelta(days=7)
