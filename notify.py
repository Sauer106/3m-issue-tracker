"""Immediate email notifications for assignments and @mentions.

These are best-effort: a mail failure is logged but never breaks the user action
that triggered it.
"""
import re
import sys
from html import escape

import db
import email_style as es
import mailer

_MENTION_RE = re.compile(r"@([A-Za-z0-9._-]+)")


def _link(app_url, kind, item_id):
    page = "Issues" if kind == "issue" else "Projects"
    return app_url.rstrip("/") + f"/?page={page}&amp;{kind}={item_id}"


def _send(config, to_email, subject, subtitle, body_para, link, kind):
    try:
        title = "3M Issues" if kind == "issue" else "3M Projects"
        inner = es.intro_row(body_para)
        footer = "This is an automated message from the 3M Issues &amp; Projects Tracker."
        html = es.shell(subtitle, inner, link, footer,
                        button_text=f"Open {kind}", title=title)
        mailer.send_email(config, [to_email], subject, html)
    except Exception as exc:  # noqa: BLE001 - never break the triggering action
        print(f"notify: failed to email {to_email}: {exc}", file=sys.stderr)


def notify_assignment(config, kind, item_id, title, assignee, actor_name, actor_id):
    """Email the assignee that an issue/project was assigned to them."""
    if not assignee or not assignee["IsActive"] or not assignee["Email"]:
        return
    if assignee["Id"] == actor_id:   # don't notify someone who assigned it to themselves
        return
    app_url = config["app"].get("app_url", "")
    subject = f"3M {kind.title()} #{item_id} assigned to you"
    para = (f"{escape(actor_name)} assigned {kind} <b>#{item_id} — {escape(title)}</b> to you.")
    _send(config, assignee["Email"], subject, f"{kind.title()} assignment", para,
          _link(app_url, kind, item_id), kind)


def find_mentions(comment, exclude_id=None):
    """Active users named with @username in the text (excluding the author)."""
    names = _MENTION_RE.findall(comment or "")
    if not names:
        return []
    users = {u["Username"].lower(): u for u in db.list_users(active_only=True)}
    seen, out = set(), []
    for n in names:
        u = users.get(n.lower())
        if u and u["Email"] and u["Id"] != exclude_id and u["Id"] not in seen:
            seen.add(u["Id"])
            out.append(u)
    return out


def notify_mentions(config, kind, item_id, title, comment, actor_name, actor_id):
    """Email anyone @mentioned in a comment."""
    app_url = config["app"].get("app_url", "")
    excerpt = escape((comment or "")[:200])
    for u in find_mentions(comment, exclude_id=actor_id):
        subject = f"3M You were mentioned in {kind} #{item_id}"
        para = (f"{escape(actor_name)} mentioned you in {kind} "
                f"<b>#{item_id} — {escape(title)}</b>:<br><br><i>{excerpt}</i>")
        _send(config, u["Email"], subject, f"Mention in {kind} #{item_id}", para,
              _link(app_url, kind, item_id), kind)
