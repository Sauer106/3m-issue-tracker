"""Email rendering: HTML escaping (XSS) and the digest/reminder builders."""
from datetime import datetime, timedelta

import email_style as es
import send_digest
import send_reminders


def test_pill_escapes_html():
    out = es.pill("<script>alert(1)</script>", "#000000")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_status_pill_colors():
    assert es.STATUS_PILL["Open"] in es.status_pill("Open")
    # Unknown status falls back to the default grey, never raises.
    assert es.status_pill("Nonsense Status")


def test_item_table_empty_and_escaping():
    assert "Nothing here" in es.item_table([], {})
    issue = {"Id": 1, "Title": "<b>bad</b>", "Status": "Open", "AssignedToName": None}
    html = es.item_table([issue], {})
    assert "&lt;b&gt;bad&lt;/b&gt;" in html
    assert "<b>bad</b>" not in html
    assert "Unassigned" in html


def test_shell_includes_title_and_button():
    html = es.shell("subtitle here", "<tr><td>body</td></tr>",
                    "https://example.test", "footer", button_text="Open Issues", title="3M Issues")
    assert "3M Issues" in html
    assert "subtitle here" in html
    assert "Open Issues" in html
    assert "https://example.test" in html


def test_issue_digest_build_html_renders():
    now = datetime(2026, 7, 23, 14, 0)
    html = send_digest.build_html([], [], [], [], {}, now, now - timedelta(days=7),
                                  "https://example.test")
    assert "3M Issues" in html
    assert "Weekly Issue Digest" in html
    assert "Open Issues" in html


def test_reminder_build_body_renders():
    # Empty issue list avoids any database access via latest_update_map.
    body = send_reminders.build_body("Jane Doe", [], reporting_deadline(), "https://example.test")
    assert "3M Issues" in body
    assert "Jane Doe" in body
    assert "Open My Issues" in body


def reporting_deadline():
    import reporting
    return reporting.upcoming_deadline({"app": {"timezone": "America/New_York"}})
