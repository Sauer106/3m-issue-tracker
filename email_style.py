"""Shared email-safe HTML styling for the reminder and digest emails.

Everything is inline styles and table layout so it renders consistently in
Outlook (Word engine) and Gmail alike. Callers build a list of table rows and
hand them to shell(), which wraps them in the branded frame.
"""
from datetime import timedelta
from html import escape

FONT = "Arial, Helvetica, sans-serif"
INK = "#1f2933"
MUTED = "#6b7280"
BORDER = "#e5e7eb"
HEADER_BG = "#22313f"
PAGE_BG = "#f4f5f7"
ACCENT = "#1565c0"

# Status pill colors, darkened from the app palette so white text stays readable.
STATUS_PILL = {
    # issue statuses
    "Open": "#1565c0", "In Progress": "#6a1b9a", "Waiting on Solventum": "#2e7d32",
    "Hold": "#e65100", "Closed": "#546e7a",
    # project statuses
    "Planned": "#1565c0", "On Hold": "#e65100", "Completed": "#2e7d32", "Cancelled": "#546e7a",
}


def pill(text, color):
    return (f'<span style="display:inline-block;padding:2px 9px;border-radius:11px;'
            f'background:{color};color:#ffffff;font-size:11px;font-weight:bold;'
            f'font-family:{FONT};white-space:nowrap;">{escape(str(text))}</span>')


def status_pill(status):
    return pill(status, STATUS_PILL.get(status, "#546e7a"))


def stat_tile(number, label, color):
    return (
        f'<td width="25%" align="center" valign="top" style="padding:0 5px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:#ffffff;border:1px solid {BORDER};border-top:3px solid {color};">'
        f'<tr><td align="center" style="padding:14px 6px;font-family:{FONT};">'
        f'<div style="font-size:30px;line-height:1;font-weight:bold;color:{color};">{number}</div>'
        f'<div style="font-size:11px;color:{MUTED};text-transform:uppercase;'
        f'letter-spacing:.03em;padding-top:6px;">{escape(label)}</div>'
        f'</td></tr></table></td>'
    )


def tiles_row(*tiles):
    return (f'<tr><td style="padding:22px 21px 4px;">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{"".join(tiles)}</tr></table></td></tr>')


def section_row(title):
    return (f'<tr><td style="font-family:{FONT};font-size:15px;font-weight:bold;color:{INK};'
            f'padding:20px 26px 8px;">{escape(title)}</td></tr>')


def intro_row(html):
    return (f'<tr><td style="font-family:{FONT};font-size:14px;color:{INK};line-height:1.55;'
            f'padding:20px 26px 0;">{html}</td></tr>')


def table_row(table_html, bottom=0):
    return f'<tr><td style="padding:0 26px {bottom}px;">{table_html}</td></tr>'


def item_table(items, updates, cutoff=None, flag_stale=False):
    """A styled table of issues or projects. `updates` maps item Id to its latest
    update row (AuthorName, Comment, CreatedAt). With flag_stale, rows with no
    recent update get an amber highlight."""
    if not items:
        return (f'<p style="font-family:{FONT};font-size:13px;color:{MUTED};'
                f'font-style:italic;margin:2px 0 0;">Nothing here.</p>')
    th = (f'padding:8px 10px;font-family:{FONT};font-size:11px;color:{MUTED};'
          f'text-transform:uppercase;letter-spacing:.03em;text-align:left;'
          f'background:#f3f4f6;border-bottom:2px solid {BORDER};')
    rows = ""
    for idx, i in enumerate(items):
        upd = updates.get(i["Id"])
        if upd:
            comment = upd["Comment"][:200] + ("…" if len(upd["Comment"]) > 200 else "")
            last = (f'<b style="color:{INK};">{escape(upd["AuthorName"])}</b> '
                    f'<span style="color:{MUTED};">({upd["CreatedAt"]:%m/%d})</span> '
                    f'{escape(comment)}')
            stale = flag_stale and cutoff is not None and upd["CreatedAt"] < cutoff - timedelta(days=7)
        else:
            last = f'<span style="color:{MUTED};font-style:italic;">No updates yet</span>'
            stale = flag_stale
        row_bg = "#fff8e1" if stale else ("#ffffff" if idx % 2 == 0 else "#fafbfc")
        accent = "#e6a100" if stale else "transparent"
        assignee = (escape(i["AssignedToName"]) if i["AssignedToName"]
                    else f'<span style="color:{MUTED};font-style:italic;">Unassigned</span>')
        td = (f'padding:9px 10px;font-family:{FONT};font-size:13px;color:{INK};'
              f'border-bottom:1px solid {BORDER};vertical-align:top;')
        rows += (
            f'<tr style="background:{row_bg};">'
            f'<td style="{td}border-left:3px solid {accent};color:{MUTED};white-space:nowrap;">#{i["Id"]}</td>'
            f'<td style="{td}font-weight:bold;">{escape(i["Title"])}</td>'
            f'<td style="{td}white-space:nowrap;">{status_pill(i["Status"])}</td>'
            f'<td style="{td}white-space:nowrap;">{assignee}</td>'
            f'<td style="{td}color:{MUTED};">{last}</td>'
            f'</tr>'
        )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;border:1px solid {BORDER};">'
        f'<tr><th style="{th}">#</th><th style="{th}">Title</th><th style="{th}">Status</th>'
        f'<th style="{th}">Assigned</th><th style="{th}">Latest update</th></tr>'
        f'{rows}</table>'
    )


def shell(subtitle, inner_rows, app_url, footer_html, button_text="Open the Tracker",
          title="3M Issues &amp; Projects Tracker"):
    return f"""\
<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:{PAGE_BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG};">
<tr><td align="center" style="padding:24px 12px;">
  <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:640px;max-width:640px;background:#ffffff;border:1px solid {BORDER};">
    <tr><td style="background:{HEADER_BG};padding:22px 26px;font-family:{FONT};">
      <div style="color:#ffffff;font-size:19px;font-weight:bold;">{title}</div>
      <div style="color:#a9bccd;font-size:13px;padding-top:3px;">{subtitle}</div>
    </td></tr>
    {inner_rows}
    <tr><td align="center" style="padding:22px 26px 26px;">
      <table role="presentation" cellpadding="0" cellspacing="0"><tr>
        <td style="background:{ACCENT};"><a href="{app_url}" style="display:inline-block;padding:12px 28px;font-family:{FONT};font-size:14px;font-weight:bold;color:#ffffff;text-decoration:none;">{escape(button_text)} &rarr;</a></td>
      </tr></table>
    </td></tr>
    <tr><td style="background:#f9fafb;border-top:1px solid {BORDER};padding:15px 26px;font-family:{FONT};font-size:11px;color:{MUTED};line-height:1.5;">{footer_html}</td></tr>
  </table>
</td></tr>
</table>
</body></html>"""
