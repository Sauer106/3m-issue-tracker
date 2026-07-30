"""3M Issues & Projects Tracker — Streamlit app.

Run with:  streamlit run app.py --server.address 0.0.0.0 --server.port 8501
"""
import calendar
import csv
import glob
import html
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pyotp
import qrcode
import streamlit as st
import streamlit.components.v1 as components

import auth
import db
import email_style as es
import mailer
import notify
import reporting
import send_digest
import send_project_digest
import send_reminders

STATUSES = ["Open", "In Progress", "Waiting on Solventum", "Hold", "Closed"]
PROJECT_STATUSES = ["Planned", "In Progress", "On Hold", "Completed", "Cancelled"]

# Managed from the Admin page (Regions/Facilities tables); reloaded every rerun.
REGIONS = db.get_region_map()

st.set_page_config(page_title="3M Issues & Projects Tracker", page_icon="🎯", layout="wide")

APP_VERSION = "1.1.0"
REPO_URL = "https://github.com/Sauer106/3m-issue-tracker"
PY_VERSION = "%d.%d.%d" % sys.version_info[:3]
ST_VERSION = st.__version__
BACKUP_DIR = r"C:\SQLBackups\IssueTracker"


def _build_info():
    """(short_sha, deploy_date) read straight from .git — no git binary needed,
    so it works under the SYSTEM scheduled task. Best-effort: (None, None) if it
    can't be determined. The ref's mtime is when this commit was checked out here,
    i.e. the deploy date."""
    try:
        gitdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".git")
        head = open(os.path.join(gitdir, "HEAD"), encoding="utf-8").read().strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1].strip()
            ref_path = os.path.join(gitdir, *ref.split("/"))
            if os.path.exists(ref_path):
                sha = open(ref_path, encoding="utf-8").read().strip()
                stamp = os.path.getmtime(ref_path)
            else:  # ref is packed
                sha = stamp = None
                packed = os.path.join(gitdir, "packed-refs")
                for line in open(packed, encoding="utf-8"):
                    if line.rstrip().endswith(ref):
                        sha, stamp = line.split()[0], os.path.getmtime(packed)
                        break
        else:  # detached HEAD
            sha, stamp = head, os.path.getmtime(os.path.join(gitdir, "HEAD"))
        if not sha:
            return (None, None)
        date = datetime.fromtimestamp(stamp).strftime("%b %d") if stamp else None
        return (sha[:7], date)
    except Exception:  # noqa: BLE001 - build stamp is cosmetic
        return (None, None)


BUILD_SHA, BUILD_DATE = _build_info()
BUILD_STR = (f"{BUILD_SHA} ({BUILD_DATE})" if BUILD_DATE else BUILD_SHA) if BUILD_SHA else None


STATUS_COLORS = {"Open": "#1976d2", "In Progress": "#7b1fa2", "Resolved": "#388e3c", "Closed": "#616161",
                 "Waiting on Solventum": "#2e7d32", "Hold": "#f57c00",
                 "Planned": "#1976d2", "On Hold": "#f57c00", "Completed": "#388e3c", "Cancelled": "#616161"}
NEUTRAL = "#607d8b"


def chip(text, color=NEUTRAL):
    # `color` is interpolated into the style attribute WITHOUT escaping; only ever
    # pass trusted constants (hex codes) here, never user-controlled data.
    return (f"<span class='chip' style='background:{color}22; color:{color}; "
            f"border:1px solid {color}55'>{html.escape(str(text))}</span>")


def solventum_chip(text):
    return (f"<span class='chip' style='background:#023129; color:#05dd4d; "
            f"border:1px solid #05dd4d'>{html.escape(str(text))}</span>")


def servicedesk_chip(text):
    return (f"<span class='chip' style='background:#cfe8ff; color:#0d47a1; "
            f"border:1px solid #1565c0'>{html.escape(str(text))}</span>")


def is_overdue(issue):
    d = issue.get("DueDate")
    return bool(d and issue["Status"] != "Closed" and d < datetime.now().date())


def due_chip(issue):
    d = issue.get("DueDate")
    if not d:
        return ""
    if is_overdue(issue):
        return chip(f"⏰ Overdue {d:%b %d}", "#d32f2f")
    return chip(f"Due {d:%b %d}", "#607d8b")


# Calendar event categories and their colors (also used for the project-target marker).
EVENT_CATEGORIES = ["Go-Live", "Deadline", "Projected Go-Live"]
EVENT_COLORS = {"Go-Live": "#388e3c", "Deadline": "#d32f2f", "Projected Go-Live": "#f57c00"}
PROJECT_TARGET_COLOR = "#00796b"


def milestone_chip(m):
    """Chip for a milestone: green ✓ when done, red when past-due and still open."""
    if m["Done"]:
        return chip(f"✓ {m['Name']}", "#388e3c")
    d = m["DueDate"]
    label = f"🎯 {m['Name']}" + (f" · {d:%b %d}" if d else "")
    if d and d < datetime.now().date():
        return chip(label + " (past)", "#d32f2f")
    return chip(label, PROJECT_TARGET_COLOR)


def next_milestone_chip(m):
    """Compact chip for a project card: its next open milestone (may be None)."""
    if not m:
        return ""
    d = m["DueDate"]
    label = f"🎯 {m['Name']}" + (f" · {d:%b %d}" if d else "")
    color = "#d32f2f" if (d and d < datetime.now().date()) else PROJECT_TARGET_COLOR
    return chip(label, color)


AVATAR_COLORS = ["#1976d2", "#7b1fa2", "#388e3c", "#f57c00", "#d32f2f", "#00796b", "#5d4037", "#455a64"]


def _initials(name):
    parts = name.split()
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else name[:2].upper()


def _avatar(name):
    color = AVATAR_COLORS[sum(ord(c) for c in name) % len(AVATAR_COLORS)]
    return f"<span class='tl-avatar' style='background:{color}'>{html.escape(_initials(name))}</span>"


# Timestamps are stored in the server's local time (config [app] timezone).
SERVER_TZ = ZoneInfo(db.get_config()["app"].get("timezone", "America/New_York"))


def _viewer_tz():
    """The browser's timezone, so everyone reads times in their own zone."""
    try:
        return ZoneInfo(st.context.timezone) if st.context.timezone else SERVER_TZ
    except (KeyError, ValueError):
        return SERVER_TZ


def to_viewer(dt):
    return dt.replace(tzinfo=SERVER_TZ).astimezone(_viewer_tz())


def fmt_dt(dt):
    """Jul 28, 2026 · 2:14 PM EDT — 12-hour, viewer's timezone, zone labeled."""
    return f"{to_viewer(dt):%b %d, %Y · %#I:%M %p %Z}"


def _rel_time(dt):
    delta = datetime.now() - dt
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins}min ago"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs}hr{'s' if hrs != 1 else ''} ago"
    days = mins // (60 * 24)
    return f"{days} day{'s' if days != 1 else ''} ago" if days < 30 else f"{dt:%b %d, %Y}"


ALL_FACILITIES = [f for facs in REGIONS.values() for f in facs]


def region_facility_picker(key_prefix, default_regions=None, default_facilities=None):
    """Checkbox pickers (in dropdown popovers) for regions and their facilities.

    The selections live in plain session state (sel_r / sel_f), and the checkbox
    widget values are written from that state on every run. Widget state alone
    can't be trusted here: Streamlit discards the state of widgets that weren't
    rendered, and facility checkboxes disappear whenever their region is
    unchecked, so reading them directly resurrects stale values.
    """
    kp = key_prefix
    sel_r_key, sel_f_key, ver_key = f"{kp}_sel_r", f"{kp}_sel_f", f"{kp}_ver"

    if sel_r_key not in st.session_state:
        dr, df = set(default_regions or []), set(default_facilities or [])
        st.session_state[sel_r_key] = [r for r in REGIONS if r in dr]
        st.session_state[sel_f_key] = [f for f in ALL_FACILITIES if f in df]
        st.session_state[ver_key] = 0

    def _store(regions, facilities):
        st.session_state[sel_r_key] = [r for r in REGIONS if r in regions]
        st.session_state[sel_f_key] = [f for f in ALL_FACILITIES if f in facilities]
        # New version -> new widget keys next run. Checkboxes remount with values
        # from the store, and any stale value echoed by the browser for an old
        # key refers to a widget that no longer exists, so it can't fire.
        st.session_state[ver_key] += 1

    def _on_all_regions(key):
        if st.session_state[key]:
            _store(set(REGIONS), set(ALL_FACILITIES))
        else:
            _store(set(), set())

    def _on_region(region, key):
        regions = set(st.session_state[sel_r_key])
        facilities = set(st.session_state[sel_f_key])
        if st.session_state[key]:
            regions.add(region)
            facilities |= set(REGIONS[region])
        else:
            regions.discard(region)
            facilities -= set(REGIONS[region])
        _store(regions, facilities)

    def _on_all_facilities(key):
        regions = set(st.session_state[sel_r_key])
        if st.session_state[key]:
            _store(regions, {f for r in regions for f in REGIONS[r]})
        else:
            _store(set(), set())   # no facilities left means no regions in scope

    def _on_facility(region, fac, key):
        regions = set(st.session_state[sel_r_key])
        facilities = set(st.session_state[sel_f_key])
        if st.session_state[key]:
            facilities.add(fac)
            regions.add(region)
        else:
            facilities.discard(fac)
            # A region whose every facility is excluded is no longer in scope,
            # so reporting never counts it.
            if not set(REGIONS[region]) & facilities:
                regions.discard(region)
        _store(regions, facilities)

    regions = list(st.session_state[sel_r_key])
    available = [f for r in regions for f in REGIONS[r]]
    facilities = [f for f in st.session_state[sel_f_key] if f in set(available)]
    ver = st.session_state[ver_key]

    col1, col2 = st.columns(2)
    with col1.popover(f"🌎 Regions ({len(regions)})", use_container_width=True):
        k = f"{kp}_{ver}_r_all"
        st.checkbox("**All Regions**", value=bool(regions) and set(regions) >= set(REGIONS),
                    key=k, on_change=_on_all_regions, args=(k,))
        for r in REGIONS:
            k = f"{kp}_{ver}_r_{r}"
            st.checkbox(r, value=r in set(regions), key=k, on_change=_on_region, args=(r, k))
    with col2.popover(f"🏥 Facilities ({len(facilities)})", use_container_width=True,
                      disabled=not regions):
        k = f"{kp}_{ver}_f_all"
        st.checkbox("**All Facilities**", value=bool(available) and set(facilities) >= set(available),
                    key=k, on_change=_on_all_facilities, args=(k,))
        for r in regions:
            st.caption(r)
            for fac in REGIONS[r]:
                k = f"{kp}_{ver}_f_{fac}"
                st.checkbox(fac, value=fac in set(facilities), key=k,
                            on_change=_on_facility, args=(r, fac, k))

    summary = region_chips(regions)
    available = [f for r in regions for f in REGIONS[r]]
    if facilities and len(facilities) < len(available):
        summary += chip(f"{len(facilities)} of {len(available)} facilities")
    st.markdown(summary or "<span class='issue-meta'>No regions selected — facilities unlock "
                           "once a region is checked</span>", unsafe_allow_html=True)
    return regions, facilities


def region_chips(regions):
    """Display-only: collapse to a single 'All Regions' chip when every region is
    selected. The stored data always keeps the full region list for reporting."""
    if regions and set(regions) >= set(REGIONS):
        return chip("All Regions", "#455a64")
    return "".join(chip(r, "#455a64") for r in regions)


def scope_chips(record, detailed=False):
    """Region/facility badges. The facility count only appears when a partial
    subset of the selected regions' facilities was chosen."""
    regions = json.loads(record["Regions"] or "[]")
    facilities = json.loads(record["Facilities"] or "[]")
    out = region_chips(regions)
    if facilities:
        if detailed:
            out += "".join(chip(f) for f in facilities)
        else:
            available = [f for r in regions for f in REGIONS.get(r, [])]
            if len(facilities) < len(available):
                out += chip(f"{len(facilities)} of {len(available)} facilities")
    return out


def field_edits(record, new_assignee_id, new_assignee_label, new_solventum, new_servicedesk,
                new_regions=None, new_facilities=None, new_due="__skip__"):
    """Diff the editable fields of an issue/project against the form values."""
    edits = []
    if new_due != "__skip__" and new_due != record.get("DueDate"):
        old_due = record.get("DueDate")
        edits.append({"field": "Due date", "old": f"{old_due}" if old_due else "",
                      "new": f"{new_due}" if new_due else ""})
    if new_assignee_id != record["AssignedTo"]:
        edits.append({"field": "Assigned to", "old": record["AssignedToName"] or "",
                      "new": "" if new_assignee_label == "(Unassigned)" else new_assignee_label})
    if (new_solventum.strip() or None) != record["SolventumTicket"]:
        edits.append({"field": "Solventum Ticket", "old": record["SolventumTicket"] or "",
                      "new": new_solventum.strip()})
    if (new_servicedesk.strip() or None) != record["ServiceDeskTicket"]:
        edits.append({"field": "ServiceDesk Ticket", "old": record["ServiceDeskTicket"] or "",
                      "new": new_servicedesk.strip()})
    if new_regions is not None:
        old_regions = json.loads(record["Regions"] or "[]")
        if sorted(new_regions) != sorted(old_regions):
            edits.append({"field": "Regions", "old": old_regions, "new": list(new_regions)})
    if new_facilities is not None:
        old_facilities = json.loads(record["Facilities"] or "[]")
        if sorted(new_facilities) != sorted(old_facilities):
            edits.append({"field": "Facilities", "old": old_facilities, "new": list(new_facilities)})
    return edits


def _edit_value_chips(field, value, color, max_chips=6):
    """Render an audit value as chips. List values get one chip apiece, collapse
    to 'All ...' when they cover everything, and overflow into '+N more'."""
    if isinstance(value, str):
        values = [v for v in value.split(", ") if v] if value else []
    else:
        values = list(value or [])
    if not values:
        return "<span class='tl-none'>none</span>"
    if field == "Regions" and set(values) >= set(REGIONS):
        return chip("All Regions", color)
    if field == "Facilities" and set(values) >= set(ALL_FACILITIES):
        return chip(f"All facilities ({len(ALL_FACILITIES)})", color)
    out = "".join(chip(v, color) for v in values[:max_chips])
    if len(values) > max_chips:
        out += chip(f"+{len(values) - max_chips} more", color)
    return out


MAX_ATTACHMENT_MB = 25


@st.cache_data(ttl=600, max_entries=64, show_spinner=False)
def _attachment_bytes(attachment_id):
    return bytes(db.get_attachment(attachment_id)["Content"])


def _fmt_size(n):
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


def render_attachments(kind, parent_id, user, log_update, read_only=False):
    """Attachment list + uploader. kind is 'issue' or 'project'; log_update writes
    the upload/removal into that item's history."""
    atts = db.list_attachments(kind, parent_id)
    with st.container(border=True):
        st.markdown(f"**📎 Attachments** &nbsp;<span class='issue-meta'>{len(atts)}</span>",
                    unsafe_allow_html=True)
        for a in atts:
            c1, c2, c3 = st.columns([6, 1, 1], vertical_alignment="center")
            c1.markdown(
                f"{html.escape(a['FileName'])}<br><span class='issue-meta'>"
                f"{_fmt_size(a['SizeBytes'])} · {html.escape(a['UploadedByName'])} · "
                f"{_rel_time(a['CreatedAt'])}</span>", unsafe_allow_html=True)
            c2.download_button("⬇", data=_attachment_bytes(a["Id"]), file_name=a["FileName"],
                               mime=a["ContentType"] or "application/octet-stream",
                               key=f"dl_{kind}_{a['Id']}", use_container_width=True,
                               help="Download")
            if not read_only and (user["IsAdmin"] or a["UploadedBy"] == user["Id"]):
                if c3.button("🗑", key=f"datt_{kind}_{a['Id']}", use_container_width=True,
                             help="Delete attachment"):
                    db.delete_attachment(a["Id"])
                    db.audit(user["Id"], "delete_attachment", f"{kind} #{parent_id}: {a['FileName']}")
                    log_update(json.dumps([{"field": "Attachment", "old": a["FileName"], "new": ""}]))
                    st.rerun()

        if read_only:
            return
        vkey = f"upv_{kind}_{parent_id}"
        ver = st.session_state.get(vkey, 0)
        files = st.file_uploader(f"Add files (max {MAX_ATTACHMENT_MB} MB each)",
                                 accept_multiple_files=True, key=f"up_{kind}_{parent_id}_{ver}")
        if files and st.button("Upload", key=f"upbtn_{kind}_{parent_id}", type="primary"):
            for f in files:
                if f.size > MAX_ATTACHMENT_MB * 1024 * 1024:
                    st.error(f"{f.name} is larger than {MAX_ATTACHMENT_MB} MB - skipped.")
                    continue
                db.add_attachment(kind, parent_id, f.name, f.type, f.getvalue(), user["Id"])
                log_update(json.dumps([{"field": "Attachment", "old": "", "new": f.name}]))
            st.session_state[vkey] = ver + 1
            st.rerun()


def render_history(updates, on_delete=None, can_delete=None,
                   proposal_allowed=False, on_proposal=None):
    """Timeline of updates. on_delete adds a 🗑 button per entry; can_delete(u)
    limits which entries get one (e.g. admins, or the entry's own author).
    When proposal_allowed, pending fix proposals get Accept/Decline buttons
    that call on_proposal(update, accepted)."""
    count = f"{len(updates)} update{'s' if len(updates) != 1 else ''}"
    st.markdown(f"**History** &nbsp;<span class='issue-meta'>{count}</span>", unsafe_allow_html=True)
    if not updates:
        st.caption("No updates yet — add the first one above.")
        return

    def item_html(u):
        dot_color, change_html = NEUTRAL, ""
        badges = ""
        proposal_color = {"Accepted": "#388e3c", "Declined": "#d32f2f"}.get(
            u.get("ProposalStatus"), "#f57c00")
        if u.get("IsFixProposal"):
            label = {"Accepted": "💡 Fix accepted", "Declined": "💡 Fix declined"}.get(
                u.get("ProposalStatus"), "💡 Fix proposal")
            badges += "&nbsp;" + chip(label, proposal_color)
        elif u["Comment"].strip():
            badges += "&nbsp;" + chip("💬 Comment", "#00796b")
        if u.get("FieldChanges"):
            badges += "&nbsp;" + chip("✏️ Details", "#5d4037")
        if u["StatusChange"]:
            old, _, new = u["StatusChange"].partition(" -> ")
            dot_color = STATUS_COLORS.get(new, NEUTRAL)
            change_html = (f"&nbsp;{chip(old)}<span class='issue-meta'>→</span>&nbsp;"
                           f"{chip(new, dot_color)}")
        elif u.get("IsFixProposal"):
            dot_color = proposal_color
        elif u["Comment"].strip():
            dot_color = "#00796b"

        edits_html = ""
        if u.get("FieldChanges"):
            try:
                edits = json.loads(u["FieldChanges"])
            except (ValueError, TypeError):
                edits = []
            rows = ""
            for e in edits:
                old_v = _edit_value_chips(e["field"], e["old"], NEUTRAL)
                new_v = _edit_value_chips(e["field"], e["new"], "#1976d2")
                rows += (f"<div class='tl-change'><span class='tl-field'>{html.escape(e['field'])}</span>"
                         f"{old_v}<span class='issue-meta'>→</span>&nbsp;{new_v}</div>")
            if rows:
                edits_html = f"<div class='tl-changes'>{rows}</div>"

        comment_html = ""
        if u["Comment"].strip():
            comment_html = f"<div class='tl-comment'>{html.escape(u['Comment']).replace(chr(10), '<br>')}</div>"

        return (
            f"<div class='tl-item'>"
            f"<span class='tl-dot' style='background:{dot_color}'></span>"
            f"<div class='tl-card'>"
            f"<div class='tl-head'>{_avatar(u['AuthorName'])}"
            f"<b>{html.escape(u['AuthorName'])}</b> "
            f"<span class='issue-meta'>{fmt_dt(u['CreatedAt'])} "
            f"· {_rel_time(u['CreatedAt'])}</span>{badges}{change_html}</div>"
            f"{comment_html}{edits_html}"
            f"</div></div>"
        )

    if on_delete is None:
        st.markdown(f"<div class='timeline'>{''.join(item_html(u) for u in updates)}</div>",
                    unsafe_allow_html=True)
        return
    for u in updates:
        c1, c2 = st.columns([14, 1])
        c1.markdown(f"<div class='timeline'>{item_html(u)}</div>", unsafe_allow_html=True)
        if (proposal_allowed and on_proposal is not None
                and u.get("IsFixProposal") and u.get("ProposalStatus") == "Pending"):
            b1, b2, _ = c1.columns([2, 2, 6])
            if b1.button("✅ Accept", key=f"accprop_{u['Id']}", use_container_width=True):
                on_proposal(u, True)
            if b2.button("❌ Decline", key=f"decprop_{u['Id']}", use_container_width=True):
                on_proposal(u, False)
        if can_delete is not None and not can_delete(u):
            continue
        if c2.button("🗑", key=f"delupd_{u['Id']}", help="Delete this update"):
            on_delete(u["Id"])
            st.rerun()


# ---------------------------------------------------------------- login

SESSION_COOKIE = "tracker_session"


def _write_cookie(value, max_age):
    # Mark the session cookie Secure when the app is served over HTTPS (per the
    # configured app_url) so browsers never transmit it over cleartext.
    secure = "; Secure" if db.get_config()["app"].get("app_url", "").startswith("https") else ""
    components.html(
        f"<script>parent.document.cookie = "
        f"'{SESSION_COOKIE}={value}; path=/; max-age={max_age}; SameSite=Lax{secure}';</script>",
        height=0,
    )


def logout():
    st.session_state.clear()
    st.session_state.cookie_restore_tried = True  # header cookie is stale for this session
    st.session_state.clear_cookie = True
    st.rerun()


def try_cookie_restore():
    """Silently re-establish the session from a valid signed cookie (set at last login)."""
    token = st.context.cookies.get(SESSION_COOKIE) or ""
    data = auth.load_session_token(token)
    if not data:
        return
    user = db.get_user_by_id(data["uid"])
    if user and user["IsActive"] and data["v"] == auth.auth_version(user):
        st.session_state.user = user
        st.session_state.totp_ok = True
        st.session_state.session_cookie_set = True
        st.rerun()


def login_screen():
    st.title("3M Issues & Projects Tracker")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in", type="primary"):
            user = db.get_user_by_username(username.strip())
            if user and user["LockedUntil"] and user["LockedUntil"] > datetime.now():
                mins = max(1, int((user["LockedUntil"] - datetime.now()).total_seconds() // 60))
                st.error(f"Account temporarily locked after repeated failed attempts. "
                         f"Try again in about {mins} minute{'s' if mins != 1 else ''}.")
            elif user and user["IsActive"] and auth.verify_password(password, user["PasswordHash"]):
                db.clear_failed_logins(user["Id"])
                st.session_state.user = user
                st.rerun()
            else:
                if user:
                    db.record_failed_login(user["Id"])
                st.error("Invalid username or password.")


def change_password_screen(user):
    st.title("3M Issues & Projects Tracker")
    st.warning("You're signed in with a temporary password. Choose a new one to continue.")
    with st.form("change_password"):
        new_pw = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Change password", type="primary"):
            if len(new_pw) < 8:
                st.error("Password must be at least 8 characters.")
            elif new_pw != confirm:
                st.error("Passwords do not match.")
            elif auth.verify_password(new_pw, user["PasswordHash"]):
                st.error("Your new password must be different from the temporary one.")
            else:
                db.set_user_password(user["Id"], auth.hash_password(new_pw))
                st.session_state.user = db.get_user_by_username(user["Username"])
                st.rerun()
    if st.button("Log out"):
        logout()


def totp_screen(user):
    st.title("3M Issues & Projects Tracker")
    if not user["TotpSecret"]:
        st.subheader("Set up two-factor authentication")
        if "totp_enroll_secret" not in st.session_state:
            st.session_state.totp_enroll_secret = pyotp.random_base32()
        secret = st.session_state.totp_enroll_secret
        st.markdown("Scan this QR code with **Microsoft Authenticator** (or any authenticator app), "
                    "then enter the 6-digit code it shows to finish setup.")
        uri = pyotp.TOTP(secret).provisioning_uri(name=user["Username"], issuer_name="3M Tracker")
        buf = io.BytesIO()
        qrcode.make(uri).save(buf, format="PNG")
        st.image(buf.getvalue(), width=220)
        st.caption(f"Can't scan? Add the account manually with this key: `{secret}`")
        with st.form("totp_enroll"):
            code = st.text_input("6-digit code")
            if st.form_submit_button("Verify and enable", type="primary"):
                if pyotp.TOTP(secret).verify(code.strip(), valid_window=1):
                    db.set_user_totp_secret(user["Id"], secret)
                    st.session_state.user = db.get_user_by_username(user["Username"])
                    st.session_state.totp_ok = True
                    del st.session_state.totp_enroll_secret
                    st.rerun()
                else:
                    st.error("That code didn't match — check the app and try again.")
    else:
        st.subheader("Two-factor authentication")
        with st.form("totp_verify"):
            code = st.text_input("6-digit code from your authenticator app")
            if st.form_submit_button("Verify", type="primary"):
                if pyotp.TOTP(user["TotpSecret"]).verify(code.strip(), valid_window=1):
                    db.clear_failed_logins(user["Id"])
                    st.session_state.totp_ok = True
                    st.rerun()
                else:
                    db.record_failed_login(user["Id"])
                    fresh = db.get_user_by_id(user["Id"])
                    if fresh["LockedUntil"] and fresh["LockedUntil"] > datetime.now():
                        logout()
                    st.error("Invalid code.")
    if st.button("Log out"):
        logout()


# ---------------------------------------------------------------- new issue / project dialogs

@st.dialog("New Issue", width="large")
def new_issue_dialog(user):
    users = db.list_users(active_only=True)
    names = {u["DisplayName"]: u["Id"] for u in users}
    title = st.text_input("Title", max_chars=200)
    description = st.text_area("Description", height=150,
                               placeholder="What's happening in 3M? Include steps to reproduce if applicable.")
    regions, facilities = region_facility_picker("ni")
    col1, col2, col3 = st.columns(3)
    assignee = col1.selectbox("Assign to", ["(Unassigned)"] + list(names))
    solventum = col2.text_input("Solventum Ticket #")
    servicedesk = col3.text_input("ServiceDesk Ticket #")
    m1, m2 = st.columns(2)
    is_major = m1.checkbox("🚩 Major issue")
    due = m2.date_input("Due date (optional)", value=None)
    if st.button("Submit Issue", type="primary", use_container_width=True):
        if not title.strip() or not description.strip():
            st.error("Title and description are required.")
        else:
            issue_id = db.create_issue(
                title.strip(), description.strip(), user["Id"], names.get(assignee),
                solventum.strip() or None, servicedesk.strip() or None,
                json.dumps(regions) if regions else None,
                json.dumps(facilities) if facilities else None,
                is_major, due,
            )
            if names.get(assignee):
                notify.notify_assignment(db.get_config(), "issue", issue_id, title.strip(),
                                         db.get_user_by_id(names[assignee]),
                                         user["DisplayName"], user["Id"])
            st.toast(f"Issue #{issue_id} created.")
            st.rerun()


@st.dialog("New Project", width="large")
def new_project_dialog(user):
    users = db.list_users(active_only=True)
    names = {u["DisplayName"]: u["Id"] for u in users}
    title = st.text_input("Title", max_chars=200)
    summary = st.text_area("Summary", height=120,
                           placeholder="What is this project about? Goals, scope, context.")
    regions, facilities = region_facility_picker("np")
    col1, col2, col3 = st.columns(3)
    assignee = col1.selectbox("Assign to", ["(Unassigned)"] + list(names))
    solventum = col2.text_input("Solventum Ticket #")
    servicedesk = col3.text_input("ServiceDesk Ticket #")
    st.caption("You can add milestones after creating the project.")
    if st.button("Create Project", type="primary", use_container_width=True):
        if not title.strip() or not summary.strip():
            st.error("Title and summary are required.")
        else:
            pid = db.create_project(title.strip(), summary.strip(), user["Id"],
                                    names.get(assignee), solventum.strip() or None,
                                    servicedesk.strip() or None,
                                    json.dumps(regions) if regions else None,
                                    json.dumps(facilities) if facilities else None)
            if names.get(assignee):
                notify.notify_assignment(db.get_config(), "project", pid, title.strip(),
                                         db.get_user_by_id(names[assignee]),
                                         user["DisplayName"], user["Id"])
            st.toast(f"Project #{pid} created.")
            st.rerun()


@st.dialog("Major issue — region rollout check")
def major_close_dialog(user):
    p = st.session_state.get("pending_major_close")
    if not p:
        st.rerun()
    st.warning(f"Issue #{p['issue_id']} is flagged 🚩 **Major** and is being marked "
               f"**{p['new_status']}**.")
    applies = st.radio("Will this fix be applied to every region?",
                       ["Yes — all regions", "No — limited rollout"])
    reason = ""
    if applies.startswith("No"):
        reason = st.text_area("Why not? (required)",
                              placeholder="Which regions are excluded, and why?")
    c1, c2 = st.columns(2)
    if c1.button("Confirm", type="primary", use_container_width=True):
        if applies.startswith("No") and not reason.strip():
            st.error("An explanation is required when the fix doesn't cover every region.")
        else:
            all_regions = applies.startswith("Yes")
            comment = p["comment"]
            if not all_regions:
                note = f"Not applied to all regions: {reason.strip()}"
                comment = f"{comment}\n\n{note}" if comment else note
            edits = p["edits"] + [{"field": "Applied to all regions", "old": "",
                                   "new": "Yes" if all_regions else "No"}]
            db.set_issue_fields(p["issue_id"], status=p["new_status"],
                                assigned_to=p["assignee_id"],
                                solventum_ticket=p["solventum"],
                                servicedesk_ticket=p["servicedesk"],
                                regions=json.dumps(p["regions"]) if p["regions"] else None,
                                facilities=json.dumps(p["facilities"]) if p["facilities"] else None,
                                is_major=p["is_major"], due_date=p["due"])
            db.add_update(p["issue_id"], user["Id"], comment, p["status_change"],
                          json.dumps(edits) if edits else None)
            del st.session_state["pending_major_close"]
            st.toast("Update saved.")
            st.rerun()
    if c2.button("Cancel", use_container_width=True):
        del st.session_state["pending_major_close"]
        st.rerun()


@st.dialog("Propose a Fix", width="large")
def propose_fix_dialog(issue, user):
    st.markdown(f"**Issue #{issue['Id']} — {issue['Title']}**")
    fix = st.text_area("Describe your proposed fix", height=150,
                       placeholder="What should be done to fix this issue, and why will it work?")
    if st.button("Submit Proposal", type="primary", use_container_width=True):
        if not fix.strip():
            st.error("Describe the fix first.")
        else:
            db.add_update(issue["Id"], user["Id"], fix.strip(), is_fix_proposal=True)
            st.toast("Fix proposed.")
            st.rerun()


# ---------------------------------------------------------------- browse / detail

def page_issues(user, config):
    if st.session_state.get("selected_issue"):
        issue_detail(st.session_state.selected_issue, user)
        return

    h1, h2 = st.columns([4, 1], vertical_alignment="center")
    h1.header("Issues")
    if h2.button("➕ New Issue", type="primary", use_container_width=True):
        for k in [k for k in st.session_state if k.startswith("ni_")]:
            del st.session_state[k]
        new_issue_dialog(user)
    with st.container(border=True):
        col1, col2, col3, col4 = st.columns([3, 3, 1.6, 1.6], vertical_alignment="center")
        status_filter = col1.multiselect("Status", STATUSES,
                                         default=["Open", "In Progress", "Waiting on Solventum", "Hold"])
        search = col2.text_input("Search title/description")
        mine_only = col3.checkbox("Mine only",
                                  value=st.session_state.pop("filter_mine_default", False))
        needs_update = col4.checkbox("Needs update",
                                     value=st.session_state.pop("filter_needs_default", False),
                                     help="Open / In Progress issues with no update since the last deadline")
    deadline = reporting.last_deadline(config)

    with st.expander("Bulk actions"):
        open_issues_bulk = db.list_issues(
            statuses=["Open", "In Progress", "Waiting on Solventum", "Hold"])
        bmap = {f"#{i['Id']} — {i['Title']}": i for i in open_issues_bulk}
        picked = st.multiselect("Issues to act on", list(bmap), key="bulk_pick")
        bc1, bc2 = st.columns([2, 3])
        action = bc1.selectbox("Action", ["Close", "Change status", "Reassign"], key="bulk_action")
        bulk_users = {u["DisplayName"]: u["Id"] for u in db.list_users(active_only=True)}
        target = None
        if action == "Change status":
            # 'Waiting on Solventum' is excluded - it needs a per-issue ticket number.
            target = bc2.selectbox("New status", [s for s in STATUSES if s != "Waiting on Solventum"],
                                   key="bulk_status")
        elif action == "Reassign":
            target = bc2.selectbox("Assign to", ["(Unassigned)"] + list(bulk_users), key="bulk_assignee")
        if st.button("Apply", disabled=not picked, key="bulk_apply"):
            chosen = [bmap[p] for p in picked]
            for i in chosen:
                if action in ("Close", "Change status"):
                    new_s = "Closed" if action == "Close" else target
                    if new_s != i["Status"]:
                        db.set_issue_fields(i["Id"], status=new_s)
                        db.add_update(i["Id"], user["Id"], "", f"{i['Status']} -> {new_s}")
                else:
                    aid = None if target == "(Unassigned)" else bulk_users[target]
                    if aid != i["AssignedTo"]:
                        db.set_issue_fields(i["Id"], assigned_to=aid)
                        db.add_update(i["Id"], user["Id"], "", None,
                                      json.dumps([{"field": "Assigned to",
                                                   "old": i["AssignedToName"] or "",
                                                   "new": "" if target == "(Unassigned)" else target}]))
            db.audit(user["Id"], "bulk_action", f"{action} on {len(chosen)} issue(s)")
            st.success(f"Applied '{action}' to {len(chosen)} issue(s).")
            del st.session_state["bulk_pick"]
            st.rerun()

    @st.fragment(run_every="10s")
    def issue_cards():
        issues = db.list_issues(statuses=status_filter or None)
        if mine_only:
            issues = [i for i in issues if i["AssignedTo"] == user["Id"]]
        if needs_update:
            issues = [i for i in issues
                      if i["Status"] in ("Open", "In Progress")
                      and (i["LastUpdateAt"] is None or i["LastUpdateAt"] < deadline)]
        if search:
            s = search.lower()
            issues = [i for i in issues if s in i["Title"].lower() or s in i["Description"].lower()]

        if not issues:
            st.info("No issues match the current filters.")
            return

        for i in issues:
            with st.container(border=True):
                c1, c2 = st.columns([6, 1], vertical_alignment="center")
                last = _rel_time(i["LastUpdateAt"]) if i["LastUpdateAt"] else "never"
                tickets = ""
                if i["SolventumTicket"]:
                    tickets += solventum_chip(i["SolventumTicket"])
                if i["ServiceDeskTicket"]:
                    tickets += servicedesk_chip(i["ServiceDeskTicket"])
                c1.markdown(
                    f"<div style='font-weight:600; font-size:1.02rem; margin-bottom:0.25rem'>"
                    f"#{i['Id']} · {html.escape(i['Title'])}</div>"
                    + (chip("🚩 Major", "#d32f2f") if i["IsMajor"] else "")
                    + chip(i["Status"], STATUS_COLORS.get(i["Status"], NEUTRAL))
                    + due_chip(i)
                    + tickets
                    + scope_chips(i)
                    + f"<p class='issue-meta'>assigned to {html.escape(i['AssignedToName'] or 'no one')}"
                    f" · reported by {html.escape(i['ReportedByName'])} · last update {last}</p>",
                    unsafe_allow_html=True,
                )
                if c2.button("Open", key=f"open_{i['Id']}", use_container_width=True):
                    st.session_state.selected_issue = i["Id"]
                    st.rerun()

    issue_cards()


def issue_detail(issue_id, user):
    if st.button("← All issues"):
        st.session_state.selected_issue = None
        st.rerun()
    issue = db.get_issue(issue_id)
    if not issue:
        st.error("Issue not found.")
        return
    page_key = f"issue:{issue_id}"
    db.touch_presence(user["Id"], page_key, activity=True)
    lock = db.get_lock_owner(page_key)
    editable = lock is None or lock["UserId"] == user["Id"]

    h1, h2 = st.columns([6, 1], vertical_alignment="center")
    h1.subheader(f"#{issue['Id']} — {issue['Title']}")
    if not editable:
        st.warning(f"🔒 **{lock['DisplayName']}** is currently viewing this issue — "
                   "you're in read-only mode until they leave or go idle (10 min).")
        if user["IsAdmin"] and st.button("🔓 Take over editing (admin)",
                                         key=f"takeover_{page_key}"):
            db.take_lock(page_key, user["Id"])
            db.audit(user["Id"], "take_lock", page_key)
            st.rerun()
    if editable and (user["IsAdmin"] or issue["ReportedBy"] == user["Id"]):
        with h2.popover("🗑 Delete", use_container_width=True):
            st.warning("Move this issue to the recycle bin? An admin can restore it.")
            if st.button("Delete issue", type="primary", key=f"delissue_{issue_id}"):
                db.delete_issue(issue_id, user["Id"])
                db.audit(user["Id"], "delete_issue", f"#{issue_id} {issue['Title']}")
                st.session_state.selected_issue = None
                st.toast(f"Issue #{issue_id} moved to the recycle bin.")
                st.rerun()
    tickets = ""
    if issue["SolventumTicket"]:
        tickets += solventum_chip(issue["SolventumTicket"])
    if issue["ServiceDeskTicket"]:
        tickets += servicedesk_chip(issue["ServiceDeskTicket"])
    st.markdown(
        (chip("🚩 Major", "#d32f2f") if issue["IsMajor"] else "")
        + chip(issue["Status"], STATUS_COLORS.get(issue["Status"], NEUTRAL))
        + due_chip(issue) + tickets
        + f"<p class='issue-meta'>Reported by {html.escape(issue['ReportedByName'])} on "
        f"{fmt_dt(issue['CreatedAt'])} ({_rel_time(issue['CreatedAt'])}) · assigned to "
        f"{html.escape(issue['AssignedToName'] or 'no one')}</p>",
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown(issue["Description"])
    if editable and st.button("💡 Propose Fix"):
        propose_fix_dialog(issue, user)

    render_attachments("issue", issue_id, user,
                       lambda fc: db.add_update(issue_id, user["Id"], "", field_changes=fc),
                       read_only=not editable)

    if not editable:
        with st.container(border=True):
            st.markdown("**Regions & Facilities**")
            st.markdown(scope_chips(issue, detailed=True)
                        or "<span class='issue-meta'>none</span>", unsafe_allow_html=True)

        @st.fragment(run_every="5s")
        def live_history_ro():
            db.touch_presence(user["Id"], page_key)
            lock_now = db.get_lock_owner(page_key)
            if lock_now is None or lock_now["UserId"] == user["Id"]:
                st.rerun()   # lock freed - re-render with edit rights
            others = db.list_presence(page_key, user["Id"])
            if others:
                st.markdown("".join(chip(f"👀 {o['DisplayName']} is viewing", "#0288d1")
                                    for o in others), unsafe_allow_html=True)
            render_history(db.list_updates(issue_id))

        live_history_ro()
        return

    users = db.list_users(active_only=True)
    names = {u["DisplayName"]: u["Id"] for u in users}
    assignee_options = ["(Unassigned)"] + list(names)
    current_assignee = issue["AssignedToName"] or "(Unassigned)"

    with st.container(border=True):
        st.markdown("**Regions & Facilities**")
        new_regions, new_facilities = region_facility_picker(
            f"iss{issue_id}",
            json.loads(issue["Regions"] or "[]"),
            json.loads(issue["Facilities"] or "[]"),
        )

    with st.form(f"update_{issue_id}"):
        st.markdown("**Add an update**")
        comment = st.text_area("Update", height=100, label_visibility="collapsed",
                               placeholder="What's the latest on this issue?")
        col1, col2 = st.columns(2)
        new_status = col1.selectbox("Status", STATUSES, index=STATUSES.index(issue["Status"]))
        new_assignee = col2.selectbox("Assign to", assignee_options,
                                      index=assignee_options.index(current_assignee))
        col3, col4 = st.columns(2)
        new_solventum = col3.text_input("Solventum Ticket #", value=issue["SolventumTicket"] or "")
        new_servicedesk = col4.text_input("ServiceDesk Ticket #", value=issue["ServiceDeskTicket"] or "")
        mj, dd = st.columns(2)
        new_major = mj.checkbox("🚩 Major issue", value=bool(issue["IsMajor"]))
        new_due = dd.date_input("Due date", value=issue["DueDate"])
        if st.form_submit_button("Save Update", type="primary"):
            status_change = None
            if new_status != issue["Status"]:
                status_change = f"{issue['Status']} -> {new_status}"
            edits = field_edits(issue, names.get(new_assignee), new_assignee,
                                new_solventum, new_servicedesk, new_regions, new_facilities,
                                new_due=new_due)
            if new_major != bool(issue["IsMajor"]):
                edits.append({"field": "Major", "old": "Yes" if issue["IsMajor"] else "No",
                              "new": "Yes" if new_major else "No"})
            if new_status == "Waiting on Solventum" and not new_solventum.strip():
                st.error("A Solventum Ticket # is required for 'Waiting on Solventum' — "
                         "enter it in the field above and save again.")
            elif not comment.strip() and not status_change and not edits:
                st.error("Enter an update, or change the status/details.")
            elif ((new_major or issue["IsMajor"]) and status_change
                  and new_status == "Closed"):
                st.session_state.pending_major_close = {
                    "issue_id": issue_id, "new_status": new_status,
                    "status_change": status_change, "comment": comment.strip(),
                    "assignee_id": names.get(new_assignee),
                    "solventum": new_solventum.strip() or None,
                    "servicedesk": new_servicedesk.strip() or None,
                    "regions": new_regions, "facilities": new_facilities,
                    "is_major": new_major, "due": new_due, "edits": edits,
                }
                major_close_dialog(user)
            else:
                db.set_issue_fields(issue_id, status=new_status,
                                    assigned_to=names.get(new_assignee),
                                    solventum_ticket=new_solventum.strip() or None,
                                    servicedesk_ticket=new_servicedesk.strip() or None,
                                    regions=json.dumps(new_regions) if new_regions else None,
                                    facilities=json.dumps(new_facilities) if new_facilities else None,
                                    is_major=new_major, due_date=new_due)
                db.add_update(issue_id, user["Id"], comment.strip(), status_change,
                              json.dumps(edits) if edits else None)
                new_aid = names.get(new_assignee)
                if new_aid and new_aid != issue["AssignedTo"]:
                    notify.notify_assignment(db.get_config(), "issue", issue_id, issue["Title"],
                                             db.get_user_by_id(new_aid), user["DisplayName"], user["Id"])
                if comment.strip():
                    notify.notify_mentions(db.get_config(), "issue", issue_id, issue["Title"],
                                           comment.strip(), user["DisplayName"], user["Id"])
                st.success("Update saved.")
                st.rerun()

    def decide_proposal(u, accepted):
        db.set_proposal_status(u["Id"], "Accepted" if accepted else "Declined")
        edits = [{"field": "Fix proposal", "old": "Pending",
                  "new": "Accepted" if accepted else "Declined"}]
        status_change = None
        if accepted and issue["Status"] != "In Progress":
            status_change = f"{issue['Status']} -> In Progress"
            db.set_issue_fields(issue_id, status="In Progress")
        db.add_update(issue_id, user["Id"], "", status_change, json.dumps(edits))
        st.rerun()

    @st.fragment(run_every="5s")
    def live_history():
        db.touch_presence(user["Id"], page_key)
        lock_now = db.get_lock_owner(page_key)
        if lock_now is not None and lock_now["UserId"] != user["Id"]:
            st.rerun()   # lost the lock - drop to read-only view
        others = db.list_presence(f"issue:{issue_id}", user["Id"])
        if others:
            st.markdown("".join(chip(f"👀 {o['DisplayName']} is viewing", "#0288d1")
                                for o in others), unsafe_allow_html=True)
        def _del_update(uid):
            db.delete_update(uid)
            db.audit(user["Id"], "delete_update", f"issue #{issue_id} update {uid}")
        render_history(db.list_updates(issue_id), on_delete=_del_update,
                       can_delete=lambda u: user["IsAdmin"] or u["AuthorId"] == user["Id"],
                       proposal_allowed=user["IsAdmin"] or issue["AssignedTo"] == user["Id"],
                       on_proposal=decide_proposal)

    live_history()


# ---------------------------------------------------------------- projects

def page_projects(user, config):
    if st.session_state.get("selected_project"):
        project_detail(st.session_state.selected_project, user)
        return

    h1, h2 = st.columns([4, 1], vertical_alignment="center")
    h1.header("Projects")
    if h2.button("➕ New Project", type="primary", use_container_width=True):
        for k in [k for k in st.session_state if k.startswith("np_")]:
            del st.session_state[k]
        new_project_dialog(user)

    with st.container(border=True):
        col1, col2, col3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        status_filter = col1.multiselect("Status", PROJECT_STATUSES,
                                         default=["Planned", "In Progress", "On Hold"])
        search = col2.text_input("Search title/summary")
        mine_only = col3.checkbox("Mine only")

    @st.fragment(run_every="10s")
    def project_cards():
        projects = db.list_projects(statuses=status_filter or None)
        if mine_only:
            projects = [p for p in projects if p["AssignedTo"] == user["Id"]]
        if search:
            s = search.lower()
            projects = [p for p in projects if s in p["Title"].lower() or s in p["Summary"].lower()]

        if not projects:
            st.info("No projects match the current filters.")
            return

        next_ms = db.next_milestones_map()
        for p in projects:
            with st.container(border=True):
                c1, c2 = st.columns([6, 1], vertical_alignment="center")
                last = _rel_time(p["LastUpdateAt"]) if p["LastUpdateAt"] else "never"
                tickets = ""
                if p["SolventumTicket"]:
                    tickets += solventum_chip(p["SolventumTicket"])
                if p["ServiceDeskTicket"]:
                    tickets += servicedesk_chip(p["ServiceDeskTicket"])
                c1.markdown(
                    f"<div style='font-weight:600; font-size:1.02rem; margin-bottom:0.25rem'>"
                    f"#{p['Id']} · {html.escape(p['Title'])}</div>"
                    + chip(p["Status"], STATUS_COLORS.get(p["Status"], NEUTRAL))
                    + tickets
                    + next_milestone_chip(next_ms.get(p["Id"]))
                    + scope_chips(p)
                    + f"<p class='issue-meta'>assigned to {html.escape(p['AssignedToName'] or 'no one')}"
                    f" · created by {html.escape(p['CreatedByName'])} · last update {last}</p>",
                    unsafe_allow_html=True,
                )
                if c2.button("Open", key=f"proj_{p['Id']}", use_container_width=True):
                    st.session_state.selected_project = p["Id"]
                    st.rerun()

    project_cards()


def project_detail(project_id, user):
    if st.button("← All projects"):
        st.session_state.selected_project = None
        st.rerun()
    proj = db.get_project(project_id)
    if not proj:
        st.error("Project not found.")
        return
    page_key = f"project:{project_id}"
    db.touch_presence(user["Id"], page_key, activity=True)
    lock = db.get_lock_owner(page_key)
    editable = lock is None or lock["UserId"] == user["Id"]

    h1, h2 = st.columns([6, 1], vertical_alignment="center")
    h1.subheader(f"#{proj['Id']} — {proj['Title']}")
    if not editable:
        st.warning(f"🔒 **{lock['DisplayName']}** is currently viewing this project — "
                   "you're in read-only mode until they leave or go idle (10 min).")
        if user["IsAdmin"] and st.button("🔓 Take over editing (admin)",
                                         key=f"takeover_{page_key}"):
            db.take_lock(page_key, user["Id"])
            db.audit(user["Id"], "take_lock", page_key)
            st.rerun()
    if editable and (user["IsAdmin"] or proj["CreatedBy"] == user["Id"]):
        with h2.popover("🗑 Delete", use_container_width=True):
            st.warning("Move this project to the recycle bin? An admin can restore it.")
            if st.button("Delete project", type="primary", key=f"delproj_{project_id}"):
                db.delete_project(project_id, user["Id"])
                db.audit(user["Id"], "delete_project", f"#{project_id} {proj['Title']}")
                st.session_state.selected_project = None
                st.toast(f"Project #{project_id} moved to the recycle bin.")
                st.rerun()
    tickets = ""
    if proj["SolventumTicket"]:
        tickets += solventum_chip(proj["SolventumTicket"])
    if proj["ServiceDeskTicket"]:
        tickets += servicedesk_chip(proj["ServiceDeskTicket"])
    st.markdown(
        chip(proj["Status"], STATUS_COLORS.get(proj["Status"], NEUTRAL)) + tickets
        + f"<p class='issue-meta'>Created by {html.escape(proj['CreatedByName'])} on "
        f"{fmt_dt(proj['CreatedAt'])} ({_rel_time(proj['CreatedAt'])}) · assigned to "
        f"{html.escape(proj['AssignedToName'] or 'no one')}</p>",
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown(proj["Summary"])

    with st.container(border=True):
        st.markdown("**🎯 Milestones**")
        milestones = db.list_milestones(project_id)
        if not milestones:
            st.caption("No milestones yet.")
        for m in milestones:
            if editable:
                mc1, mc2, mc3 = st.columns([6, 1, 1], vertical_alignment="center")
                mc1.markdown(milestone_chip(m), unsafe_allow_html=True)
                if mc2.button("Reopen" if m["Done"] else "Done", key=f"msdone_{m['Id']}",
                              use_container_width=True):
                    db.update_milestone(m["Id"], done=not m["Done"])
                    verb = "Reopened" if m["Done"] else "Completed"
                    emoji = "↩️" if m["Done"] else "✅"
                    db.add_project_update(project_id, user["Id"],
                                          f"{emoji} {verb} milestone: {m['Name']}")
                    db.audit(user["Id"], "milestone_toggle",
                             f"project #{project_id} '{m['Name']}' -> "
                             f"{'open' if m['Done'] else 'done'}")
                    st.rerun()
                if mc3.button("🗑", key=f"msdel_{m['Id']}", use_container_width=True):
                    db.delete_milestone(m["Id"])
                    db.add_project_update(project_id, user["Id"],
                                          f"🗑 Removed milestone: {m['Name']}")
                    db.audit(user["Id"], "milestone_delete", f"project #{project_id} '{m['Name']}'")
                    st.rerun()
            else:
                st.markdown(milestone_chip(m), unsafe_allow_html=True)
        if editable:
            with st.form(f"add_ms_{project_id}", clear_on_submit=True):
                a1, a2, a3 = st.columns([4, 2, 1], vertical_alignment="bottom")
                ms_name = a1.text_input("Milestone", placeholder="e.g. UAT complete")
                ms_date = a2.date_input("Target date (optional)", value=None)
                if a3.form_submit_button("Add", use_container_width=True):
                    if ms_name.strip():
                        db.add_milestone(project_id, ms_name.strip(), ms_date)
                        due = f" (due {ms_date:%b %d, %Y})" if ms_date else ""
                        db.add_project_update(project_id, user["Id"],
                                              f"🎯 Added milestone: {ms_name.strip()}{due}")
                        db.audit(user["Id"], "milestone_add",
                                 f"project #{project_id} '{ms_name.strip()}'")
                        st.rerun()
                    else:
                        st.warning("Enter a milestone name.")

    with st.container(border=True):
        cc1, cc2 = st.columns([6, 1], vertical_alignment="center")
        cc1.markdown("**📅 Calendar**")
        if editable and cc2.button("➕ Add", key=f"addcal_{project_id}", use_container_width=True):
            for k in [k for k in st.session_state if k.startswith("ne_")]:
                del st.session_state[k]
            st.session_state.ne_seed_project = project_id
            new_event_dialog(user)
        events = db.list_events_for_project(project_id)
        if not events:
            st.caption("No calendar events linked to this project yet.")
        for e in events:
            color = EVENT_COLORS.get(e["Category"], NEUTRAL)
            when = f"{e['EventDate']:%b %d, %Y}"
            if e["EventTime"]:
                when += f" · {e['EventTime']:%#I:%M %p}"
            if e["EndDate"] and e["EndDate"] != e["EventDate"]:
                when += f" → {e['EndDate']:%b %d}"
            ec1, ec2 = st.columns([6, 1], vertical_alignment="center")
            ec1.markdown(f"{chip(e['Category'], color)} {html.escape(e['Title'])}"
                         f"<p class='issue-meta'>{when}</p>", unsafe_allow_html=True)
            if ec2.button("Open", key=f"pcalev_{e['Id']}", use_container_width=True):
                st.session_state.open_event_id = e["Id"]
                st.session_state.page = "Calendar"
                st.rerun()

    render_attachments("project", project_id, user,
                       lambda fc: db.add_project_update(project_id, user["Id"], "", field_changes=fc),
                       read_only=not editable)

    if not editable:
        with st.container(border=True):
            st.markdown("**Regions & Facilities**")
            st.markdown(scope_chips(proj, detailed=True)
                        or "<span class='issue-meta'>none</span>", unsafe_allow_html=True)

        @st.fragment(run_every="5s")
        def live_history_ro():
            db.touch_presence(user["Id"], page_key)
            lock_now = db.get_lock_owner(page_key)
            if lock_now is None or lock_now["UserId"] == user["Id"]:
                st.rerun()   # lock freed - re-render with edit rights
            others = db.list_presence(page_key, user["Id"])
            if others:
                st.markdown("".join(chip(f"👀 {o['DisplayName']} is viewing", "#0288d1")
                                    for o in others), unsafe_allow_html=True)
            render_history(db.list_project_updates(project_id))

        live_history_ro()
        return

    users = db.list_users(active_only=True)
    names = {u["DisplayName"]: u["Id"] for u in users}
    assignee_options = ["(Unassigned)"] + list(names)
    current_assignee = proj["AssignedToName"] or "(Unassigned)"

    with st.container(border=True):
        st.markdown("**Regions & Facilities**")
        new_regions, new_facilities = region_facility_picker(
            f"prj{project_id}",
            json.loads(proj["Regions"] or "[]"),
            json.loads(proj["Facilities"] or "[]"),
        )

    with st.form(f"proj_update_{project_id}"):
        st.markdown("**Add an update**")
        comment = st.text_area("Update", height=100, label_visibility="collapsed",
                               placeholder="What's the latest on this project?")
        col1, col2 = st.columns(2)
        new_status = col1.selectbox("Status", PROJECT_STATUSES,
                                    index=PROJECT_STATUSES.index(proj["Status"]))
        new_assignee = col2.selectbox("Assign to", assignee_options,
                                      index=assignee_options.index(current_assignee))
        col3, col4 = st.columns(2)
        new_solventum = col3.text_input("Solventum Ticket #", value=proj["SolventumTicket"] or "")
        new_servicedesk = col4.text_input("ServiceDesk Ticket #", value=proj["ServiceDeskTicket"] or "")
        if st.form_submit_button("Save Update", type="primary"):
            status_change = None
            if new_status != proj["Status"]:
                status_change = f"{proj['Status']} -> {new_status}"
            edits = field_edits(proj, names.get(new_assignee), new_assignee,
                                new_solventum, new_servicedesk, new_regions, new_facilities)
            if not comment.strip() and not status_change and not edits:
                st.error("Enter an update, or change the status/details.")
            else:
                db.set_project_fields(project_id, status=new_status,
                                      assigned_to=names.get(new_assignee),
                                      solventum_ticket=new_solventum.strip() or None,
                                      servicedesk_ticket=new_servicedesk.strip() or None,
                                      regions=json.dumps(new_regions) if new_regions else None,
                                      facilities=json.dumps(new_facilities) if new_facilities else None)
                db.add_project_update(project_id, user["Id"], comment.strip(), status_change,
                                      json.dumps(edits) if edits else None)
                new_aid = names.get(new_assignee)
                if new_aid and new_aid != proj["AssignedTo"]:
                    notify.notify_assignment(db.get_config(), "project", project_id, proj["Title"],
                                             db.get_user_by_id(new_aid), user["DisplayName"], user["Id"])
                if comment.strip():
                    notify.notify_mentions(db.get_config(), "project", project_id, proj["Title"],
                                           comment.strip(), user["DisplayName"], user["Id"])
                st.success("Update saved.")
                st.rerun()

    @st.fragment(run_every="5s")
    def live_history():
        db.touch_presence(user["Id"], page_key)
        lock_now = db.get_lock_owner(page_key)
        if lock_now is not None and lock_now["UserId"] != user["Id"]:
            st.rerun()   # lost the lock - drop to read-only view
        others = db.list_presence(f"project:{project_id}", user["Id"])
        if others:
            st.markdown("".join(chip(f"👀 {o['DisplayName']} is viewing", "#0288d1")
                                for o in others), unsafe_allow_html=True)
        def _del_pupdate(uid):
            db.delete_project_update(uid)
            db.audit(user["Id"], "delete_update", f"project #{project_id} update {uid}")
        render_history(db.list_project_updates(project_id), on_delete=_del_pupdate,
                       can_delete=lambda u: user["IsAdmin"] or u["AuthorId"] == user["Id"])

    live_history()


# ---------------------------------------------------------------- calendar

_CAL_CSS = """
<style>
.cal { width:100%; border-collapse:collapse; table-layout:fixed; margin-top:0.4rem; }
.cal-th { padding:6px 6px; font-size:0.72rem; text-transform:uppercase; letter-spacing:0.04em;
          color:rgba(128,128,128,0.9); border-bottom:2px solid rgba(128,128,128,0.25); text-align:left; }
.cal-cell { height:6.4rem; width:14.28%; vertical-align:top; border:1px solid rgba(128,128,128,0.18);
            padding:3px 4px; overflow:hidden; }
.cal-dim { background:rgba(128,128,128,0.06); }
.cal-dim .cal-daynum { opacity:0.4; }
.cal-today { outline:2px solid #ff4b4b; outline-offset:-2px; }
.cal-daynum { font-size:0.78rem; font-weight:600; margin-bottom:2px; color:rgba(128,128,128,0.95); }
.cal-ev { font-size:0.7rem; line-height:1.25; padding:1px 5px; margin-bottom:2px; border-radius:3px;
          background:rgba(128,128,128,0.10); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cal-more { font-size:0.66rem; color:rgba(128,128,128,0.8); padding-left:2px; }
.cal-legend { margin:0.6rem 0 0.2rem; font-size:0.78rem; color:rgba(128,128,128,0.9); }
.cal-leg { margin-right:1rem; white-space:nowrap; }
.cal-dot { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px;
           vertical-align:middle; }
</style>
"""


def _cal_chip(color, text):
    return (f"<div class='cal-ev' style='border-left:3px solid {color};'>"
            f"{html.escape(text)}</div>")


def _calendar_grid(year, month, items_by_day, today):
    cal = calendar.Calendar(firstweekday=6)  # Sunday first (US)
    head = "".join(f"<th class='cal-th'>{d}</th>"
                   for d in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
    body = ""
    for week in cal.monthdatescalendar(year, month):
        cells = ""
        for day in week:
            cls = "cal-cell"
            if day.month != month:
                cls += " cal-dim"
            if day == today:
                cls += " cal-today"
            items = sorted(items_by_day.get(day, []), key=lambda x: x["sort"])
            chips = "".join(it["chip"] for it in items[:4])
            if len(items) > 4:
                chips += f"<div class='cal-more'>+{len(items) - 4} more</div>"
            cells += f"<td class='{cls}'><div class='cal-daynum'>{day.day}</div>{chips}</td>"
        body += f"<tr>{cells}</tr>"
    return f"<table class='cal'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _cal_legend():
    parts = [f"<span class='cal-leg'><span class='cal-dot' style='background:{c}'></span>{k}</span>"
             for k, c in EVENT_COLORS.items()]
    return "<div class='cal-legend'>" + " ".join(parts) + "</div>"


def _event_form(user, event):
    """Shared create/edit form. `event` is None for a new event. Keyed widgets so
    picks survive Streamlit reruns; state clears on save."""
    is_edit = event is not None
    projects = db.list_projects()
    proj_labels = {f"#{p['Id']} · {p['Title']}": p["Id"] for p in projects}
    id_to_label = {v: k for k, v in proj_labels.items()}
    pfx = f"ee{event['Id']}_" if is_edit else "ne_"

    if pfx + "init" not in st.session_state:
        st.session_state[pfx + "init"] = True
        st.session_state[pfx + "title"] = event["Title"] if is_edit else ""
        st.session_state[pfx + "date"] = event["EventDate"] if is_edit else datetime.now().date()
        st.session_state[pfx + "cat"] = (event["Category"] if is_edit and event["Category"]
                                         in EVENT_CATEGORIES else "Go-Live")
        st.session_state[pfx + "settime"] = bool(is_edit and event["EventTime"])
        st.session_state[pfx + "time"] = (event["EventTime"] if (is_edit and event["EventTime"])
                                          else datetime.now().time().replace(second=0, microsecond=0))
        st.session_state[pfx + "multi"] = bool(is_edit and event["EndDate"])
        st.session_state[pfx + "end"] = (event["EndDate"] if (is_edit and event["EndDate"])
                                         else st.session_state[pfx + "date"])
        st.session_state[pfx + "desc"] = (event["Description"] if is_edit and event["Description"] else "")
        if is_edit:
            sel = [id_to_label[e["Id"]] for e in db.list_event_projects(event["Id"])
                   if e["Id"] in id_to_label]
        else:
            seed = st.session_state.pop("ne_seed_project", None)
            sel = [id_to_label[seed]] if seed in id_to_label else []
        st.session_state[pfx + "projects"] = sel

    title = st.text_input("Title", key=pfx + "title", max_chars=200)
    c1, c2 = st.columns(2)
    edate = c1.date_input("Date", key=pfx + "date")
    c2.selectbox("Category", EVENT_CATEGORIES, key=pfx + "cat")
    category = st.session_state[pfx + "cat"]
    t1, t2 = st.columns(2)
    set_time = t1.checkbox("Set a start time", key=pfx + "settime")
    etime = (t1.time_input("Start time", key=pfx + "time", label_visibility="collapsed")
             if set_time else None)
    multi = t2.checkbox("Multi-day (end date)", key=pfx + "multi")
    end_date = (t2.date_input("End date", key=pfx + "end", label_visibility="collapsed")
                if multi else None)
    picked = st.multiselect("Linked projects", list(proj_labels), key=pfx + "projects")
    description = st.text_area("Description", key=pfx + "desc", height=100)

    if st.button("Save changes" if is_edit else "Create event", type="primary",
                 use_container_width=True):
        if not title.strip():
            st.error("Title is required.")
            return
        if multi and end_date and end_date < edate:
            st.error("End date can't be before the start date.")
            return
        pids = [proj_labels[lbl] for lbl in picked]
        if is_edit:
            db.update_event(event["Id"], title.strip(), edate, etime, end_date if multi else None,
                            category, description.strip() or None, pids)
            db.audit(user["Id"], "update_event", f"#{event['Id']} {title.strip()}")
            st.toast("Event updated.")
        else:
            eid = db.create_event(title.strip(), edate, user["Id"], etime,
                                  end_date if multi else None, category,
                                  description.strip() or None, pids)
            db.audit(user["Id"], "create_event", f"#{eid} {title.strip()}")
            st.toast("Event created.")
        for k in [k for k in st.session_state if k.startswith(pfx)]:
            del st.session_state[k]
        st.rerun()


@st.dialog("New Event", width="large")
def new_event_dialog(user):
    _event_form(user, None)


def _render_event_readonly(event):
    color = EVENT_COLORS.get(event["Category"], NEUTRAL)
    when = f"{event['EventDate']:%A, %B %d, %Y}"
    if event["EventTime"]:
        when += f" at {event['EventTime']:%#I:%M %p}"
    if event["EndDate"] and event["EndDate"] != event["EventDate"]:
        when += f" → {event['EndDate']:%B %d, %Y}"
    st.markdown(f"{chip(event['Category'], color)} **{html.escape(event['Title'])}**",
                unsafe_allow_html=True)
    st.caption(f"{when} · added by {event['CreatedByName']}")
    if event["Description"]:
        st.markdown(event["Description"])
    links = db.list_event_projects(event["Id"])
    if links:
        st.markdown("**Linked projects**")
        for l in links:
            if st.button(f"#{l['Id']} · {l['Title']}", key=f"evproj_{event['Id']}_{l['Id']}"):
                st.session_state.selected_project = l["Id"]
                st.session_state.page = "Projects"
                st.rerun()


@st.dialog("Event", width="large")
def event_detail_dialog(event, user):
    if user["IsAdmin"] or event["CreatedBy"] == user["Id"]:
        _event_form(user, event)
        st.divider()
        with st.popover("🗑 Delete event"):
            st.warning("Delete this event permanently? This can't be undone.")
            if st.button("Delete event", type="primary", key=f"delev_{event['Id']}"):
                db.delete_event(event["Id"])
                db.audit(user["Id"], "delete_event", f"#{event['Id']} {event['Title']}")
                for k in [k for k in st.session_state if k.startswith(f"ee{event['Id']}_")]:
                    del st.session_state[k]
                st.toast("Event deleted.")
                st.rerun()
    else:
        _render_event_readonly(event)


def page_calendar(user, config):
    pending = st.session_state.pop("open_event_id", None)
    if pending:
        for k in [k for k in st.session_state if k.startswith(f"ee{pending}_")]:
            del st.session_state[k]
        ev = db.get_event(pending)
        if ev:
            event_detail_dialog(ev, user)

    today = datetime.now().date()
    if "cal_year" not in st.session_state:
        st.session_state.cal_year, st.session_state.cal_month = today.year, today.month
    year, month = st.session_state.cal_year, st.session_state.cal_month

    h1, h2 = st.columns([6, 1], vertical_alignment="center")
    h1.header("Calendar")
    if h2.button("➕ New Event", type="primary", use_container_width=True):
        for k in [k for k in st.session_state if k.startswith("ne_")]:
            del st.session_state[k]
        new_event_dialog(user)

    nav1, nav2, nav3, nav4 = st.columns([1, 1, 4, 1], vertical_alignment="center")
    if nav1.button("◀ Prev", use_container_width=True):
        st.session_state.cal_year, st.session_state.cal_month = (
            (year, month - 1) if month > 1 else (year - 1, 12))
        st.rerun()
    if nav2.button("Today", use_container_width=True):
        st.session_state.cal_year, st.session_state.cal_month = today.year, today.month
        st.rerun()
    if nav4.button("Next ▶", use_container_width=True):
        st.session_state.cal_year, st.session_state.cal_month = (
            (year, month + 1) if month < 12 else (year + 1, 1))
        st.rerun()
    nav3.markdown(f"<div style='text-align:center; font-size:1.15rem; font-weight:600;'>"
                  f"{calendar.month_name[month]} {year}</div>", unsafe_allow_html=True)

    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdatescalendar(year, month)
    grid_start, grid_end = weeks[0][0], weeks[-1][-1]
    midnight = datetime.min.time()

    items_by_day = {}
    for e in db.list_events(grid_start, grid_end):
        color = EVENT_COLORS.get(e["Category"], NEUTRAL)
        label = (f"{e['EventTime']:%#I:%M %p} " if e["EventTime"] else "") + e["Title"]
        end = e["EndDate"] or e["EventDate"]
        d = max(e["EventDate"], grid_start)
        while d <= min(end, grid_end):
            items_by_day.setdefault(d, []).append(
                {"sort": (d, e["EventTime"] or midnight), "chip": _cal_chip(color, label)})
            d += timedelta(days=1)

    st.markdown(_CAL_CSS + _calendar_grid(year, month, items_by_day, today), unsafe_allow_html=True)
    st.markdown(_cal_legend(), unsafe_allow_html=True)

    st.subheader(f"Agenda — {calendar.month_name[month]} {year}")
    m_start = datetime(year, month, 1).date()
    m_end = datetime(year, month, calendar.monthrange(year, month)[1]).date()
    agenda = [("event", e["EventDate"], e["EventTime"] or midnight, e)
              for e in db.list_events(m_start, m_end)]
    agenda.sort(key=lambda x: (x[1], x[2]))

    if not agenda:
        st.info("Nothing scheduled this month. Use **New Event** to add one.")
        return

    for _kind, d, _t, obj in agenda:
        with st.container(border=True):
            c1, c2 = st.columns([6, 1], vertical_alignment="center")
            color = EVENT_COLORS.get(obj["Category"], NEUTRAL)
            when = f"{d:%a %b %d}"
            if obj["EventTime"]:
                when += f" · {obj['EventTime']:%#I:%M %p}"
            if obj["EndDate"] and obj["EndDate"] != d:
                when += f" → {obj['EndDate']:%b %d}"
            links = "".join(chip(l["Title"], PROJECT_TARGET_COLOR)
                            for l in db.list_event_projects(obj["Id"]))
            c1.markdown(
                f"{chip(obj['Category'], color)} <b>{html.escape(obj['Title'])}</b>"
                f"<p class='issue-meta'>{when} · added by {html.escape(obj['CreatedByName'])}</p>"
                f"{links}", unsafe_allow_html=True)
            if c2.button("Open", key=f"calev_{obj['Id']}", use_container_width=True):
                for k in [k for k in st.session_state if k.startswith(f"ee{obj['Id']}_")]:
                    del st.session_state[k]
                event_detail_dialog(obj, user)


# ---------------------------------------------------------------- dashboard

def _bar(counts, x_label):
    """A small bar chart from a {category: count} dict, largest first."""
    if not counts:
        st.caption("Nothing to show yet.")
        return
    items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    df = pd.DataFrame({x_label: [k for k, _ in items], "Count": [v for _, v in items]})
    st.bar_chart(df, x=x_label, y="Count", color="#1976d2", height=260)


def _csv_dt(dt):
    """Clean, spreadsheet-friendly timestamp (blank if none)."""
    return f"{dt:%Y-%m-%d %H:%M}" if dt else ""


def _issues_csv(issues):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Title", "Status", "Major", "Solventum", "ServiceDesk", "Regions",
                "Facilities", "Reported By", "Assigned To", "Created", "Updated", "Closed",
                "Last Update"])
    for i in issues:
        w.writerow([i["Id"], i["Title"], i["Status"], "Yes" if i["IsMajor"] else "No",
                    i["SolventumTicket"] or "", i["ServiceDeskTicket"] or "",
                    "; ".join(json.loads(i["Regions"] or "[]")),
                    "; ".join(json.loads(i["Facilities"] or "[]")),
                    i["ReportedByName"], i["AssignedToName"] or "", _csv_dt(i["CreatedAt"]),
                    _csv_dt(i["UpdatedAt"]), _csv_dt(i["ResolvedAt"]), _csv_dt(i["LastUpdateAt"])])
    return buf.getvalue()


def _projects_csv(projects):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Title", "Status", "Solventum", "ServiceDesk", "Regions", "Facilities",
                "Created By", "Assigned To", "Created", "Updated", "Last Update"])
    for p in projects:
        w.writerow([p["Id"], p["Title"], p["Status"], p["SolventumTicket"] or "",
                    p["ServiceDeskTicket"] or "", "; ".join(json.loads(p["Regions"] or "[]")),
                    "; ".join(json.loads(p["Facilities"] or "[]")), p["CreatedByName"],
                    p["AssignedToName"] or "", _csv_dt(p["CreatedAt"]), _csv_dt(p["UpdatedAt"]),
                    _csv_dt(p["LastUpdateAt"])])
    return buf.getvalue()


def page_dashboard(user, config):
    st.header("Dashboard")
    issues = db.list_issues()
    projects = db.list_projects()
    deadline = reporting.last_deadline(config)
    open_states = ("Open", "In Progress", "Waiting on Solventum", "Hold")

    open_issues = [i for i in issues if i["Status"] in open_states]
    closed_week = [i for i in issues if i["Status"] == "Closed"
                   and i["ResolvedAt"] and i["ResolvedAt"] >= deadline]
    needs = [i for i in open_issues if i["Status"] in ("Open", "In Progress")
             and (i["LastUpdateAt"] is None or i["LastUpdateAt"] < deadline)]
    active_projects = [p for p in projects if p["Status"] in ("Planned", "In Progress", "On Hold")]

    overdue = [i for i in open_issues if is_overdue(i)]
    overdue_ms = db.list_overdue_milestones()
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Open issues", len(open_issues))
    c2.metric("Overdue", len(overdue))
    c3.metric("Closed this week", len(closed_week))
    c4.metric("Needs update", len(needs))
    c5.metric("Active projects", len(active_projects))
    c6.metric("Overdue milestones", len(overdue_ms))

    now = datetime.now()
    if open_issues:
        ages = [(now - i["CreatedAt"]).days for i in open_issues]
        a1, a2 = st.columns(2)
        a1.metric("Avg age of open issues", f"{round(sum(ages) / len(ages))} days")
        a2.metric("Oldest open issue", f"{max(ages)} days")

    if overdue_ms:
        st.subheader("⚠️ Overdue milestones")
        for m in overdue_ms:
            days = (now.date() - m["DueDate"]).days
            name_chip = chip(f"🎯 {m['Name']}", "#d32f2f")
            plural = "s" if days != 1 else ""
            with st.container(border=True):
                o1, o2 = st.columns([6, 1], vertical_alignment="center")
                o1.markdown(
                    f"{name_chip} <b>{html.escape(m['ProjectTitle'])}</b>"
                    f"<p class='issue-meta'>Due {m['DueDate']:%b %d, %Y} · {days} day{plural} "
                    f"overdue · assigned to {html.escape(m['AssignedToName'] or 'no one')}</p>",
                    unsafe_allow_html=True)
                if o2.button("Open project", key=f"omst_{m['Id']}", use_container_width=True):
                    st.session_state.selected_project = m["ProjectId"]
                    st.session_state.page = "Projects"
                    st.rerun()

    st.subheader("Upcoming — next 30 days")
    up_start = now.date()
    up_end = up_start + timedelta(days=30)
    midnight = datetime.min.time()
    upcoming = sorted(db.list_events(up_start, up_end),
                      key=lambda e: (e["EventDate"], e["EventTime"] or midnight))
    if not upcoming:
        st.caption("No calendar events in the next 30 days.")
    else:
        for e in upcoming[:12]:
            with st.container(border=True):
                u1, u2 = st.columns([6, 1], vertical_alignment="center")
                color = EVENT_COLORS.get(e["Category"], NEUTRAL)
                when = f"{e['EventDate']:%a %b %d}"
                if e["EventTime"]:
                    when += f" · {e['EventTime']:%#I:%M %p}"
                links = "".join(chip(l["Title"], PROJECT_TARGET_COLOR)
                                for l in db.list_event_projects(e["Id"]))
                u1.markdown(f"{chip(e['Category'], color)} <b>{html.escape(e['Title'])}</b>"
                            f"<p class='issue-meta'>{when}</p>{links}", unsafe_allow_html=True)
                if u2.button("Open", key=f"dashev_{e['Id']}", use_container_width=True):
                    st.session_state.open_event_id = e["Id"]
                    st.session_state.page = "Calendar"
                    st.rerun()
        if len(upcoming) > 12:
            st.caption(f"+{len(upcoming) - 12} more — see the Calendar.")

    st.subheader("Issues by status")
    by_status = {}
    for i in issues:
        by_status[i["Status"]] = by_status.get(i["Status"], 0) + 1
    _bar(by_status, "Status")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Open issues by region")
        by_region = {}
        for i in open_issues:
            for r in json.loads(i["Regions"] or "[]"):
                by_region[r] = by_region.get(r, 0) + 1
        _bar(by_region, "Region")
    with col2:
        st.subheader("Open issues by assignee")
        by_assignee = {}
        for i in open_issues:
            name = i["AssignedToName"] or "Unassigned"
            by_assignee[name] = by_assignee.get(name, 0) + 1
        _bar(by_assignee, "Assignee")

    st.subheader("Projects by status")
    proj_status = {}
    for p in projects:
        proj_status[p["Status"]] = proj_status.get(p["Status"], 0) + 1
    _bar(proj_status, "Status")

    st.subheader("Export")
    st.caption("Download the current data as a spreadsheet (opens in Excel).")
    today = f"{now:%Y-%m-%d}"
    e1, e2 = st.columns(2)
    e1.download_button("⬇ Issues (CSV)", _issues_csv(issues), f"issues_{today}.csv",
                       "text/csv", use_container_width=True)
    e2.download_button("⬇ Projects (CSV)", _projects_csv(projects), f"projects_{today}.csv",
                       "text/csv", use_container_width=True)


# ---------------------------------------------------------------- admin

def _last_backup_info():
    """(newest_datetime, age_hours, file_count, total_mb) for the DB backups,
    or None if the folder is missing/empty. Best-effort."""
    try:
        files = glob.glob(os.path.join(BACKUP_DIR, "IssueTracker_*.bak"))
        if not files:
            return None
        newest_path = max(files, key=os.path.getmtime)
        newest = datetime.fromtimestamp(os.path.getmtime(newest_path))
        age_h = (datetime.now() - newest).total_seconds() / 3600
        total_mb = sum(os.path.getsize(f) for f in files) / (1024 * 1024)
        return (newest, age_h, len(files), total_mb)
    except Exception:  # noqa: BLE001
        return None


def _task_status():
    """Status line for each scheduled task via schtasks. Best-effort; slow enough
    to gate behind a button."""
    tasks = ["IssueTracker App", "IssueTracker Reminders", "IssueTracker Weekly Digest",
             "IssueTracker Project Digest", "IssueTracker DB Backup"]
    out = []
    for t in tasks:
        try:
            r = subprocess.run(["schtasks", "/Query", "/TN", t, "/FO", "LIST"],
                               capture_output=True, text=True, timeout=10)
            status = "not found"
            for line in r.stdout.splitlines():
                if line.strip().startswith("Status:"):
                    status = line.split(":", 1)[1].strip()
                    break
            out.append(f"**{t}** — {status}")
        except Exception as exc:  # noqa: BLE001
            out.append(f"**{t}** — error: {exc}")
    return out


def render_diagnostics():
    diag = db.env_diagnostics()

    st.markdown("**Application**")
    st.markdown(
        f"- Version **v{APP_VERSION}** · build `{BUILD_STR or 'unknown'}`\n"
        f"- Python `{PY_VERSION}` · Streamlit `{ST_VERSION}` · pyodbc `{diag['pyodbc']}`\n"
        f"- Server time {datetime.now():%Y-%m-%d %I:%M %p} ({SERVER_TZ.key})"
    )

    st.markdown("**Database**")
    drivers = ", ".join(diag["installed_drivers"]) or "none detected"
    st.markdown(
        f"- Configured driver: `{diag['configured_driver']}`\n"
        f"- Installed ODBC (SQL Server): {drivers}\n"
        f"- SQL Server: {diag['sql_server']}"
    )

    st.markdown("**Backups**")
    info = _last_backup_info()
    if info:
        newest, age_h, count, total_mb = info
        flag = " ⚠️ stale (>26h)" if age_h > 26 else " ✅"
        st.markdown(
            f"- Latest {newest:%Y-%m-%d %I:%M %p} ({age_h:.0f}h ago){flag}\n"
            f"- {count} file(s), {total_mb:.0f} MB in `{BACKUP_DIR}`"
        )
    else:
        st.markdown(f"- No backups found in `{BACKUP_DIR}`.")

    st.markdown("**Scheduled tasks**")
    if st.button("Check task status", key="diag_tasks_btn"):
        st.session_state.diag_task_status = _task_status()
    for line in st.session_state.get("diag_task_status", []):
        st.markdown(f"- {line}")


def page_admin(user, config):
    st.header("Admin — User Management")

    with st.expander("🩺 System diagnostics", expanded=False):
        render_diagnostics()

    with st.expander("Create a new user", expanded=False):
        with st.form("create_user", clear_on_submit=True):
            col1, col2 = st.columns(2)
            username = col1.text_input("Username")
            display_name = col2.text_input("Display name")
            email = col1.text_input("Email")
            temp_password = col2.text_input("Temporary password", type="password")
            is_admin = st.checkbox("Administrator")
            if st.form_submit_button("Create User", type="primary"):
                if not all([username.strip(), display_name.strip(), email.strip(), temp_password]):
                    st.error("All fields are required.")
                elif db.get_user_by_username(username.strip()):
                    st.error("That username already exists.")
                else:
                    db.create_user(username.strip(), display_name.strip(), email.strip(),
                                   auth.hash_password(temp_password), is_admin, must_change=True)
                    db.audit(user["Id"], "create_user",
                             f"{username.strip()}" + (" (admin)" if is_admin else ""))
                    st.success(f"User '{username.strip()}' created. They'll be asked to "
                               "choose their own password on first login.")

    st.subheader("Existing users")
    for u in db.list_users():
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
            role_chip = chip("Admin", "#7b1fa2") if u["IsAdmin"] else chip("User")
            state_chip = chip("Active", "#388e3c") if u["IsActive"] else chip("Inactive", "#d32f2f")
            col1.markdown(f"**{u['DisplayName']}** (`{u['Username']}`)")
            col2.markdown(f"{html.escape(u['Email'])}<br>{role_chip}{state_chip}",
                          unsafe_allow_html=True)
            new_pw = col3.text_input("New password", type="password", key=f"pw_{u['Id']}",
                                     label_visibility="collapsed", placeholder="New password")
            if col3.button("Reset password", key=f"reset_{u['Id']}"):
                if new_pw:
                    db.set_user_password(u["Id"], auth.hash_password(new_pw), must_change=True)
                    db.audit(user["Id"], "reset_password", u["Username"])
                    st.success(f"Password reset for {u['Username']}. They'll be asked to "
                               "choose a new one at next login.")
                else:
                    st.error("Enter a new password first.")
            toggle_label = "Deactivate" if u["IsActive"] else "Reactivate"
            if col4.button(toggle_label, key=f"toggle_{u['Id']}"):
                db.set_user_active(u["Id"], not u["IsActive"])
                db.audit(user["Id"], "deactivate_user" if u["IsActive"] else "reactivate_user",
                         u["Username"])
                st.rerun()
            if u["Id"] != user["Id"]:
                admin_label = "Remove admin" if u["IsAdmin"] else "Make admin"
                if col4.button(admin_label, key=f"adm_{u['Id']}"):
                    db.set_user_admin(u["Id"], not u["IsAdmin"])
                    db.audit(user["Id"], "remove_admin" if u["IsAdmin"] else "make_admin",
                             u["Username"])
                    st.rerun()
            if u["TotpSecret"] and col4.button("Reset 2FA", key=f"totp_{u['Id']}"):
                db.set_user_totp_secret(u["Id"], None)
                db.audit(user["Id"], "reset_2fa", u["Username"])
                st.success(f"2FA reset for {u['Username']}. They'll re-enroll at next login.")

    st.subheader("Reassign work")
    st.caption("Move all open issues and projects from one person to another — handy when "
               "someone leaves or changes roles.")
    all_users = db.list_users()
    umap = {f"{u['DisplayName']} ({u['Username']})": u["Id"] for u in all_users}
    rc1, rc2 = st.columns(2)
    from_label = rc1.selectbox("From", list(umap), key="reassign_from")
    to_label = rc2.selectbox("To", list(umap), key="reassign_to")
    from_id, to_id = umap[from_label], umap[to_label]
    n_issues = len([i for i in db.list_issues(
        statuses=["Open", "In Progress", "Waiting on Solventum", "Hold"]) if i["AssignedTo"] == from_id])
    n_projects = len([p for p in db.list_projects(
        statuses=["Planned", "In Progress", "On Hold"]) if p["AssignedTo"] == from_id])
    st.caption(f"**{from_label}** has **{n_issues}** open issue(s) and **{n_projects}** "
               f"open project(s) assigned.")
    if st.button("Reassign", type="primary", disabled=(from_id == to_id or n_issues + n_projects == 0)):
        moved_i = db.reassign_issues(from_id, to_id)
        moved_p = db.reassign_projects(from_id, to_id)
        db.audit(user["Id"], "reassign",
                 f"{from_label} -> {to_label}: {moved_i} issues, {moved_p} projects")
        st.success(f"Reassigned {moved_i} issue(s) and {moved_p} project(s) to {to_label}.")
        st.rerun()

    st.subheader("Email recipients")
    st.caption("Who receives the weekly digests and the Thursday update reminders. "
               "Digests go to the opted-in users below plus any additional recipients.")

    def _save_prefs(uid, dkey, rkey):
        db.set_user_email_prefs(uid, st.session_state[dkey], st.session_state[rkey])

    hdr = st.columns([3, 1, 1], vertical_alignment="bottom")
    hdr[1].markdown("**Digests**")
    hdr[2].markdown("**Reminders**")
    for u in db.list_users(active_only=True):
        c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="center")
        c1.markdown(f"**{u['DisplayName']}**  \n<span class='issue-meta'>{html.escape(u['Email'])}</span>",
                    unsafe_allow_html=True)
        dkey, rkey = f"dig_{u['Id']}", f"rem_{u['Id']}"
        c2.checkbox("Digests", value=bool(u["ReceivesDigest"]), key=dkey,
                    label_visibility="collapsed", on_change=_save_prefs, args=(u["Id"], dkey, rkey))
        c3.checkbox("Reminders", value=bool(u["ReceivesReminders"]), key=rkey,
                    label_visibility="collapsed", on_change=_save_prefs, args=(u["Id"], dkey, rkey))

    with st.expander("Additional digest recipients (managers or lists that aren't app users)"):
        with st.form("add_extra_recipient", clear_on_submit=True):
            c1, c2, c3 = st.columns([3, 2, 1], vertical_alignment="bottom")
            xemail = c1.text_input("Email")
            xlabel = c2.text_input("Label (optional)")
            if c3.form_submit_button("Add", use_container_width=True):
                if xemail.strip():
                    db.add_extra_recipient(xemail.strip(), xlabel.strip() or None)
                    db.audit(user["Id"], "add_recipient", xemail.strip())
                    st.rerun()
                else:
                    st.error("Enter an email address.")
        extras = db.list_extra_recipients()
        if not extras:
            st.caption("None yet. Digests currently go only to opted-in users above.")
        for r in extras:
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.markdown(f"{html.escape(r['Email'])}"
                        + (f" — {html.escape(r['Label'])}" if r["Label"] else ""))
            if c2.button("Remove", key=f"xr_{r['Id']}", use_container_width=True):
                db.delete_extra_recipient(r["Id"])
                db.audit(user["Id"], "remove_recipient", r["Email"])
                st.rerun()

    st.subheader("Regions & Facilities")
    st.caption("Changes apply to new tagging immediately. Items already tagged with a "
               "renamed or deleted entry keep their original tag text.")
    with st.form("add_region", clear_on_submit=True):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        region_name = c1.text_input("New region name")
        if c2.form_submit_button("Add Region", type="primary", use_container_width=True):
            if region_name.strip():
                try:
                    db.create_region(region_name.strip())
                    st.rerun()
                except Exception:
                    st.error("Couldn't add region - does that name already exist?")

    for r in db.list_regions():
        facs = db.list_facilities(r["Id"])
        with st.expander(f"{r['Name']} — {len(facs)} facilit{'ies' if len(facs) != 1 else 'y'}"):
            c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="bottom")
            new_name = c1.text_input("Region name", value=r["Name"], key=f"rn_{r['Id']}")
            if c2.button("Rename", key=f"rrn_{r['Id']}", use_container_width=True):
                if new_name.strip():
                    try:
                        db.rename_region(r["Id"], new_name.strip())
                        st.rerun()
                    except Exception:
                        st.error("Couldn't rename - does that name already exist?")
            if c3.button("Delete", key=f"rdel_{r['Id']}", use_container_width=True):
                db.delete_region(r["Id"])
                db.audit(user["Id"], "delete_region", r["Name"])
                st.rerun()

            st.markdown("**Facilities** (name · code)")
            for f in facs:
                c1, c2, c3, c4 = st.columns([3, 2, 1, 1], vertical_alignment="bottom")
                f_name = c1.text_input("Name", value=f["Name"], key=f"fn_{f['Id']}",
                                       label_visibility="collapsed")
                f_code = c2.text_input("Code", value=f["Code"] or "", key=f"fc_{f['Id']}",
                                       label_visibility="collapsed", placeholder="Code")
                if c3.button("Save", key=f"fs_{f['Id']}", use_container_width=True):
                    if f_name.strip():
                        db.update_facility(f["Id"], f_name.strip(), f_code.strip() or None)
                        st.rerun()
                if c4.button("Delete", key=f"fd_{f['Id']}", use_container_width=True):
                    db.delete_facility(f["Id"])
                    db.audit(user["Id"], "delete_facility", f"{r['Name']}: {f['Name']}")
                    st.rerun()

            with st.form(f"add_fac_{r['Id']}", clear_on_submit=True):
                c1, c2, c3 = st.columns([3, 2, 1], vertical_alignment="bottom")
                af_name = c1.text_input("New facility name")
                af_code = c2.text_input("Code")
                if c3.form_submit_button("Add", use_container_width=True):
                    if af_name.strip():
                        db.create_facility(r["Id"], af_name.strip(), af_code.strip() or None)
                        st.rerun()

    st.subheader("Email tools")
    st.caption("Preview the emails or trigger a real send. Test buttons go only to you; "
               "'Send now to everyone' respects the once-per-week guard.")
    me = user["Email"]
    t1, t2, t3 = st.columns(3)
    if t1.button("Test issue digest to me", use_container_width=True):
        subj, body = send_digest.render(config)
        mailer.send_email(config, [me], subj + " (test)", body)
        st.success(f"Sent to {me}")
    if t2.button("Test project digest to me", use_container_width=True):
        subj, body = send_project_digest.render(config)
        mailer.send_email(config, [me], subj + " (test)", body)
        st.success(f"Sent to {me}")
    if t3.button("Test reminder to me", use_container_width=True):
        mine = [i for i in db.list_issues(statuses=["Open", "In Progress"])
                if user["Id"] in (i["AssignedTo"], i["ReportedBy"])]
        body = send_reminders.build_body(user["DisplayName"], mine[:10],
                                         reporting.upcoming_deadline(config),
                                         config["app"].get("app_url", ""))
        mailer.send_email(config, [me], "3M Update Reminder (test)", body)
        st.success(f"Sent to {me}")
    with st.popover("Send now to everyone…"):
        st.warning("These send to all recipients immediately (skips if already sent this week).")
        if st.button("Send issue digest now"):
            send_digest.main()
            db.audit(user["Id"], "send_issue_digest", "manual")
            st.success("Issue digest sent (or already sent this week).")
        if st.button("Send project digest now"):
            send_project_digest.main()
            db.audit(user["Id"], "send_project_digest", "manual")
            st.success("Project digest sent (or already sent this week).")

    st.subheader("Recycle bin")
    st.caption("Deleted issues and projects. Restore brings them back; permanent delete "
               "removes them and their history for good.")
    del_issues = db.list_deleted_issues()
    del_projects = db.list_deleted_projects()
    if not del_issues and not del_projects:
        st.caption("Empty.")
    for kind, items, restore_fn, purge_fn in [
        ("issue", del_issues, db.restore_issue, db.purge_issue),
        ("project", del_projects, db.restore_project, db.purge_project),
    ]:
        for it in items:
            c1, c2, c3 = st.columns([5, 1, 1], vertical_alignment="center")
            c1.markdown(
                f"{chip(kind.title(), '#546e7a')} #{it['Id']} · {html.escape(it['Title'])}"
                f"<br><span class='issue-meta'>deleted by "
                f"{html.escape(it['DeletedByName'] or 'unknown')} · {fmt_dt(it['DeletedAt'])}</span>",
                unsafe_allow_html=True)
            if c2.button("Restore", key=f"restore_{kind}_{it['Id']}", use_container_width=True):
                restore_fn(it["Id"])
                db.audit(user["Id"], f"restore_{kind}", f"#{it['Id']} {it['Title']}")
                st.rerun()
            with c3.popover("Delete", use_container_width=True):
                st.warning("Permanently delete? This cannot be undone.")
                if st.button("Delete forever", key=f"purge_{kind}_{it['Id']}"):
                    purge_fn(it["Id"])
                    db.audit(user["Id"], f"purge_{kind}", f"#{it['Id']} {it['Title']}")
                    st.rerun()

    st.subheader("Audit log")
    st.caption("Deletions and administrative actions, most recent first.")
    entries = db.list_audit(200)
    if not entries:
        st.caption("No activity recorded yet.")
    else:
        for e in entries:
            who = html.escape(e["ActorName"] or "unknown")
            detail = f" — {html.escape(e['Detail'])}" if e["Detail"] else ""
            st.markdown(
                f"<div style='padding:2px 0'>{chip(e['Action'], '#5d4037')} "
                f"<b>{who}</b><span class='issue-meta'>{detail} · {fmt_dt(e['CreatedAt'])}</span></div>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------- main

def main():
    config = db.get_config()
    if "user" not in st.session_state:
        if st.session_state.pop("clear_cookie", False):
            _write_cookie("", 0)
        elif "cookie_restore_tried" not in st.session_state:
            st.session_state.cookie_restore_tried = True
            try_cookie_restore()
        login_screen()
        return

    user = st.session_state.user
    if user["MustChangePassword"]:
        change_password_screen(user)
        return
    if not st.session_state.get("totp_ok"):
        totp_screen(user)
        return
    if not st.session_state.get("session_cookie_set"):
        _write_cookie(auth.make_session_token(user), auth.SESSION_MAX_AGE)
        st.session_state.session_cookie_set = True

    deadline = reporting.upcoming_deadline(config)

    st.markdown("""
        <style>
        /* Sidebar nav cards */
        section[data-testid="stSidebar"] [class*="st-key-nav_"] button {
            width: 100%;
            justify-content: flex-start;
            text-align: left;
            padding: 0.85rem 1rem;
            border-radius: 0.75rem;
            border: 1px solid rgba(128, 128, 128, 0.35);
            font-weight: 500;
        }
        section[data-testid="stSidebar"] [class*="st-key-nav_"] button:hover {
            border-color: #ff4b4b;
        }
        /* Card containers: softer corners to match the nav */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 0.75rem;
        }
        /* Colored pill badges for priority / status / category */
        .chip {
            display: inline-block;
            padding: 0.12rem 0.6rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            margin-right: 0.3rem;
            white-space: nowrap;
        }
        .issue-meta {
            color: rgba(128, 128, 128, 0.95);
            font-size: 0.82rem;
            margin: 0.15rem 0 0 0;
        }
        /* Region/facility picker popovers: cap height so the panel scrolls
           instead of growing taller than the space below and flipping upward */
        div[data-testid="stPopoverBody"] {
            max-height: min(14rem, 30vh);
            overflow-y: auto;
        }
        /* Update-history timeline */
        .timeline {
            border-left: 2px solid rgba(128, 128, 128, 0.3);
            margin: 0.6rem 0 0 0.55rem;
            padding-left: 1.4rem;
        }
        .tl-item { position: relative; padding-bottom: 1rem; }
        .tl-item:last-child { padding-bottom: 0.2rem; }
        .tl-dot {
            position: absolute;
            left: calc(-1.4rem - 8px);
            top: 0.55rem;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            border: 2px solid rgba(128, 128, 128, 0.15);
        }
        .tl-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 0.6rem;
            padding: 0.6rem 0.85rem;
            background: rgba(128, 128, 128, 0.05);
        }
        .tl-head { margin-bottom: 0.3rem; }
        .tl-avatar {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.55rem;
            height: 1.55rem;
            border-radius: 50%;
            color: #fff;
            font-size: 0.68rem;
            font-weight: 700;
            margin-right: 0.45rem;
            vertical-align: middle;
        }
        .tl-comment { line-height: 1.5; }
        .tl-changes {
            margin-top: 0.4rem;
            padding-top: 0.4rem;
            border-top: 1px dashed rgba(128, 128, 128, 0.25);
        }
        .tl-change { font-size: 0.84rem; margin-bottom: 0.2rem; }
        .tl-field {
            display: inline-block;
            min-width: 8.5rem;
            color: rgba(128, 128, 128, 0.95);
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .tl-none {
            color: rgba(128, 128, 128, 0.8);
            font-style: italic;
            font-size: 0.8rem;
            margin-right: 0.3rem;
        }
        /* Keep filter checkbox labels on one line so they align */
        div[data-testid="stCheckbox"] label p { white-space: nowrap; }
        </style>
    """, unsafe_allow_html=True)

    pages = ["Issues", "Projects", "Calendar", "Dashboard"]
    if user["IsAdmin"]:
        pages.append("Admin")
    icons = {"Issues": "📋", "Projects": "🗂️", "Calendar": "📅", "Dashboard": "📊", "Admin": "⚙️"}

    # Deep links from the emails: ?page=Issues|Projects, and ?mine=1 to open the
    # Issues list already filtered to the current user's items. Apply once.
    if not st.session_state.get("deeplink_applied"):
        st.session_state.deeplink_applied = True
        qp = st.query_params
        target = qp.get("page")
        if target in pages:
            st.session_state.page = target
        if qp.get("mine") == "1":
            st.session_state.filter_mine_default = True
        if qp.get("needsupdate") == "1":
            st.session_state.filter_needs_default = True
        if (qp.get("issue") or "").isdigit():
            st.session_state.selected_issue = int(qp["issue"])
            st.session_state.page = "Issues"
        if (qp.get("project") or "").isdigit():
            st.session_state.selected_project = int(qp["project"])
            st.session_state.page = "Projects"
        if (qp.get("event") or "").isdigit():
            st.session_state.open_event_id = int(qp["event"])
            st.session_state.page = "Calendar"

    if st.session_state.get("page") not in pages:
        st.session_state.page = pages[0]

    with st.sidebar:
        st.title("3M Issues & Projects Tracker")
        st.markdown(f"Signed in as **{user['DisplayName']}**")
        due = to_viewer(deadline)
        st.info(f"Updates due **{due:%a %b %d} at {due:%#I:%M %p %Z}**")
        for p in pages:
            active = st.session_state.page == p
            if st.button(f"{icons[p]}  {p}", key=f"nav_{p}",
                         type="primary" if active else "secondary",
                         use_container_width=True):
                st.session_state.page = p
                st.session_state.selected_issue = None
                st.session_state.selected_project = None
                st.rerun()
        st.divider()
        if st.button("Log out"):
            logout()
    page = st.session_state.page

    if page == "Issues":
        page_issues(user, config)
    elif page == "Projects":
        page_projects(user, config)
    elif page == "Calendar":
        page_calendar(user, config)
    elif page == "Dashboard":
        page_dashboard(user, config)
    elif page == "Admin":
        page_admin(user, config)


FAQ_ITEMS = [
    ("How do I sign in for the first time?",
     "Use the temporary password an administrator gave you. You'll be asked to set your own "
     "password right away, then to set up two-factor authentication (2FA) by scanning a QR "
     "code with an authenticator app (it shows up as **3M Tracker**). After that, each login "
     "asks for a 6-digit code from that app."),
    ("I'm locked out or forgot my password.",
     "Five failed attempts locks the account for 15 minutes. For a password or 2FA reset, ask "
     "an administrator — they can reset your password and clear 2FA from the Admin page."),
    ("What's the difference between an Issue and a Project?",
     "**Issues** track problems and requests in 3M that need resolution. **Projects** track "
     "longer, planned bodies of work. They have separate pages and separate weekly digests."),
    ("What are the Solventum and ServiceDesk ticket fields for?",
     "They link a record to the matching ticket number in those systems so everyone can "
     "cross-reference. The **Waiting on Solventum** status requires a Solventum ticket number."),
    ("What does the 🚩 Major flag mean?",
     "It marks an issue as high-impact. When you close a Major issue or accept a proposed fix "
     "for it, you'll be asked to confirm whether the resolution applies to every region."),
    ("How do regions and facilities work?",
     "Use the picker to tag which areas an item affects. Selecting every region collapses to a "
     "single **All Regions** tag. Administrators manage the region and facility lists on the "
     "Admin page."),
    ("What are the statuses, and what is 'Propose a Fix'?",
     "Issues move Open → In Progress → (Waiting on Solventum / Hold) → Closed. Anyone can "
     "**Propose a Fix**; the assigned analyst can accept it — which moves the issue to In "
     "Progress — or decline it."),
    ("How do due dates and the 'Needs update' filter work?",
     "Set an optional due date on an issue; overdue items get a red badge and appear on the "
     "dashboard. The **Needs update** filter shows items that haven't been touched recently, "
     "and the Thursday reminder email links straight to them."),
    ("When do emails go out?",
     "You get an email the moment an item is assigned to you or you're @mentioned in a comment. "
     "Weekly, there's an Issue digest and a Project digest on Friday morning and an update "
     "reminder on Thursday. Administrators manage who receives digests on the Admin page."),
    ("Can two people edit the same record at once?",
     "The tracker shows who else is viewing a record in real time. The first person to open it "
     "for editing holds the lock and everyone else is read-only until it's released — it frees "
     "after a period of inactivity, and an administrator can take over."),
    ("How do I attach a file?",
     "Open an issue or project and use the attachments section to upload supporting files."),
    ("Something is wrong, or I have a request.",
     "Use the **Report a Bug** button next to Help — it goes straight to the administrators. "
     "For access, password, or 2FA resets, contact an administrator directly."),
]


@st.dialog("Help & FAQ", width="large")
def help_dialog():
    st.caption(f"3M Issues & Projects Tracker · v{APP_VERSION}")
    st.markdown("Common questions about using the tracker. Still stuck? Use **Report a Bug** "
                "to reach an administrator.")
    for question, answer in FAQ_ITEMS:
        with st.expander(question):
            st.markdown(answer)


def _env_block():
    """A best-effort environment summary appended to bug-report emails, so admins
    can see the stack (Python/Streamlit/pyodbc/ODBC driver/SQL Server) at a glance."""
    build = f" &middot; build {BUILD_STR}" if BUILD_STR else ""
    lines = [f"App v{APP_VERSION}{build} &middot; Python {PY_VERSION} &middot; Streamlit {ST_VERSION}"]
    try:
        diag = db.env_diagnostics()
        drivers = ", ".join(diag["installed_drivers"]) or "none detected"
        lines.append(f"pyodbc {html.escape(str(diag['pyodbc']))} &middot; "
                     f"configured driver: {html.escape(str(diag['configured_driver']))}")
        lines.append(f"installed ODBC (SQL Server): {html.escape(drivers)}")
        lines.append(f"SQL Server: {html.escape(str(diag['sql_server']))}")
    except Exception as exc:  # noqa: BLE001 - diagnostics must never break the report
        lines.append(f"(environment details unavailable: {html.escape(str(exc))})")
    return ('<span style="color:#6b7280;font-size:12px;line-height:1.5;">'
            f'<b>Environment</b><br>{"<br>".join(lines)}</span>')


def _submit_bug_report(user, where, severity, what, steps, attachment=None):
    """Email active administrators (and the reporter, as a receipt) the bug report
    and record it in the audit log. Best-effort: returns (report_id, sent) where
    sent is True if the email went out, False if it was only logged.
    `attachment` is an optional (filename, content_type, bytes) tuple."""
    config = db.get_config()
    detail = f"[{severity} | {where}] {what}" + (f" | Steps: {steps}" if steps else "")
    report_id = None
    try:
        report_id = db.audit(user["Id"], "Bug report", detail)
    except Exception as exc:  # noqa: BLE001 - logging is best-effort
        print(f"bug report: audit failed: {exc}")

    admins = [u for u in db.list_users(active_only=True) if u["IsAdmin"] and u["Email"]]
    if not admins:
        return (report_id, False)

    reporter = f"{user['DisplayName']} ({user.get('Email') or 'no email on file'})"
    what_html = html.escape(what).replace("\n", "<br>")
    ref_line = f"<b>Report #:</b> {report_id}<br>" if report_id else ""
    body = (f"{ref_line}"
            f"<b>Reporter:</b> {html.escape(reporter)}<br>"
            f"<b>Severity:</b> {html.escape(severity)}<br>"
            f"<b>Where:</b> {html.escape(where)}<br><br>"
            f"<b>What happened</b><br>{what_html}")
    if steps:
        body += f"<br><br><b>Steps to reproduce</b><br>{html.escape(steps).replace(chr(10), '<br>')}"
    if attachment:
        body += "<br><br><i>Screenshot attached.</i>"
    body += "<br><br>" + _env_block()
    inner = es.intro_row(body)
    app_url = config["app"].get("app_url", "")
    ref = f"#{report_id} " if report_id else ""
    subject = f"3M Tracker bug report {ref}— {severity.split(' ')[0]} — {where}"
    body_html = es.shell("Bug report", inner, app_url,
                         "This is an automated bug report from the 3M Issues &amp; Projects Tracker.",
                         button_text="Open the Tracker")
    # The reporter gets a copy as a receipt.
    recipients = [a["Email"] for a in admins]
    if user.get("Email") and user["Email"] not in recipients:
        recipients.append(user["Email"])
    try:
        mailer.send_email(config, recipients, subject, body_html,
                          attachments=[attachment] if attachment else None)
        return (report_id, True)
    except Exception as exc:  # noqa: BLE001 - never break the reporting flow
        print(f"bug report: email failed: {exc}")
        return (report_id, False)


@st.dialog("Report a Bug", width="large")
def bug_report_dialog(user):
    st.markdown("Tell us what went wrong. This goes straight to the administrators, "
                "and you'll get a copy for your records.")
    places = ["Issues", "Projects", "Dashboard", "Admin", "Login / sign-in", "Emails", "Other"]
    current = st.session_state.get("page")
    c1, c2 = st.columns(2)
    where = c1.selectbox("Where did it happen?", places,
                         index=places.index(current) if current in places else 0)
    severity = c2.selectbox("How bad is it?",
                            ["Blocking — can't work", "Annoying — has a workaround",
                             "Cosmetic — minor"])
    what = st.text_area("What happened?", height=140,
                        placeholder="Describe the problem. What did you expect, and what "
                                    "happened instead?")
    steps = st.text_area("Steps to reproduce (optional)", height=100,
                         placeholder="1. ...\n2. ...")
    shot = st.file_uploader("Screenshot (optional)", type=["png", "jpg", "jpeg", "gif"])
    if st.button("Send Report", type="primary", use_container_width=True):
        if not what.strip():
            st.error("Please describe what happened.")
        else:
            attachment = None
            if shot is not None:
                attachment = (shot.name, shot.type or "application/octet-stream", shot.getvalue())
            report_id, sent = _submit_bug_report(user, where, severity, what.strip(),
                                                 steps.strip(), attachment)
            ref = f" (report #{report_id})" if report_id else ""
            st.toast(f"Report sent to the administrators{ref}." if sent
                     else f"Report recorded for the administrators{ref}.")
            st.rerun()


def render_footer():
    """A small, muted footer with Help/Report actions, shown at the bottom of
    every screen. Rendered after main() so it lands below whichever page (or the
    login/2FA screen) was just drawn, since Streamlit paints in call order."""
    user = st.session_state.get("user")
    year = datetime.now().year
    build_meta = f" <span class='sep'>•</span> build {BUILD_STR}" if BUILD_STR else ""
    st.markdown(
        """
        <style>
        .footer-rule {
            border: none;
            border-top: 1px solid rgba(128, 128, 128, 0.2);
            margin: 2.5rem 0 0.4rem 0;
        }
        .app-footer {
            text-align: center;
            color: rgba(128, 128, 128, 0.85);
            font-size: 0.78rem;
            letter-spacing: 0.02em;
            padding: 0.2rem 0 0.6rem 0;
        }
        .app-footer strong { color: rgba(128, 128, 128, 0.95); font-weight: 600; }
        .app-footer .sep { margin: 0 0.5rem; opacity: 0.5; }
        .app-footer a { color: inherit; text-decoration: underline; text-underline-offset: 2px; }
        .app-footer a:hover { color: #ff4b4b; }
        .app-footer-meta { margin-top: 0.25rem; font-size: 0.72rem; opacity: 0.8; }
        /* Make the footer action buttons read like quiet text links */
        [class*="st-key-footer_"] button {
            border: none;
            background: transparent;
            color: rgba(128, 128, 128, 0.9);
            font-size: 0.82rem;
            font-weight: 500;
            padding: 0.2rem 0.4rem;
            min-height: 0;
        }
        [class*="st-key-footer_"] button:hover { color: #ff4b4b; background: transparent; }
        [class*="st-key-footer_"] button:focus { box-shadow: none; }
        </style>
        <hr class='footer-rule'>
        """,
        unsafe_allow_html=True,
    )
    if user:
        _, c1, c2, _ = st.columns([3, 2, 2, 3])
        if c1.button("❓ Help & FAQ", key="footer_help", use_container_width=True):
            help_dialog()
        if c2.button("🐛 Report a Bug", key="footer_bug", use_container_width=True):
            bug_report_dialog(user)
    else:
        _, c1, _ = st.columns([3, 2, 3])
        if c1.button("❓ Help & FAQ", key="footer_help", use_container_width=True):
            help_dialog()
    st.markdown(
        f"""
        <div class='app-footer'>
            <strong>3M Issues &amp; Projects Tracker</strong>
            <span class='sep'>•</span> v{APP_VERSION}
            <span class='sep'>•</span> Developed by
            <a href="{REPO_URL}" target="_blank" rel="noopener">Michael Sauer</a>
            <span class='sep'>•</span> &copy; {year}
            <div class='app-footer-meta'>Python {PY_VERSION}
                <span class='sep'>•</span> Streamlit {ST_VERSION}{build_meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


main()
render_footer()
