"""3M Issues & Projects Tracker — Streamlit app.

Run with:  streamlit run app.py --server.address 0.0.0.0 --server.port 8501
"""
import html
import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pyotp
import qrcode
import streamlit as st
import streamlit.components.v1 as components

import auth
import db
import reporting

STATUSES = ["Open", "In Progress", "Waiting on Solventum", "Hold", "Closed"]
PROJECT_STATUSES = ["Planned", "In Progress", "On Hold", "Completed", "Cancelled"]

# Managed from the Admin page (Regions/Facilities tables); reloaded every rerun.
REGIONS = db.get_region_map()

st.set_page_config(page_title="3M Issues & Projects Tracker", page_icon="🎯", layout="wide")


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
                new_regions=None, new_facilities=None):
    """Diff the editable fields of an issue/project against the form values."""
    edits = []
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
    is_major = st.checkbox("🚩 Major issue")
    if st.button("Submit Issue", type="primary", use_container_width=True):
        if not title.strip() or not description.strip():
            st.error("Title and description are required.")
        else:
            issue_id = db.create_issue(
                title.strip(), description.strip(), user["Id"], names.get(assignee),
                solventum.strip() or None, servicedesk.strip() or None,
                json.dumps(regions) if regions else None,
                json.dumps(facilities) if facilities else None,
                is_major,
            )
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
    if st.button("Create Project", type="primary", use_container_width=True):
        if not title.strip() or not summary.strip():
            st.error("Title and summary are required.")
        else:
            pid = db.create_project(title.strip(), summary.strip(), user["Id"],
                                    names.get(assignee), solventum.strip() or None,
                                    servicedesk.strip() or None,
                                    json.dumps(regions) if regions else None,
                                    json.dumps(facilities) if facilities else None)
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
                                is_major=p["is_major"])
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
        col1, col2, col3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        status_filter = col1.multiselect("Status", STATUSES,
                                         default=["Open", "In Progress", "Waiting on Solventum", "Hold"])
        search = col2.text_input("Search title/description")
        mine_only = col3.checkbox("Mine only")

    @st.fragment(run_every="10s")
    def issue_cards():
        issues = db.list_issues(statuses=status_filter or None)
        if mine_only:
            issues = [i for i in issues if user["Id"] in (i["AssignedTo"], i["ReportedBy"])]
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
            st.rerun()
    if editable and (user["IsAdmin"] or issue["ReportedBy"] == user["Id"]):
        with h2.popover("🗑 Delete", use_container_width=True):
            st.warning("Permanently delete this issue and its entire history?")
            if st.button("Yes, delete permanently", type="primary", key=f"delissue_{issue_id}"):
                db.delete_issue(issue_id)
                st.session_state.selected_issue = None
                st.toast(f"Issue #{issue_id} deleted.")
                st.rerun()
    tickets = ""
    if issue["SolventumTicket"]:
        tickets += solventum_chip(issue["SolventumTicket"])
    if issue["ServiceDeskTicket"]:
        tickets += servicedesk_chip(issue["ServiceDeskTicket"])
    st.markdown(
        (chip("🚩 Major", "#d32f2f") if issue["IsMajor"] else "")
        + chip(issue["Status"], STATUS_COLORS.get(issue["Status"], NEUTRAL)) + tickets
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
        new_major = st.checkbox("🚩 Major issue", value=bool(issue["IsMajor"]))
        if st.form_submit_button("Save Update", type="primary"):
            status_change = None
            if new_status != issue["Status"]:
                status_change = f"{issue['Status']} -> {new_status}"
            edits = field_edits(issue, names.get(new_assignee), new_assignee,
                                new_solventum, new_servicedesk, new_regions, new_facilities)
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
                    "is_major": new_major, "edits": edits,
                }
                major_close_dialog(user)
            else:
                db.set_issue_fields(issue_id, status=new_status,
                                    assigned_to=names.get(new_assignee),
                                    solventum_ticket=new_solventum.strip() or None,
                                    servicedesk_ticket=new_servicedesk.strip() or None,
                                    regions=json.dumps(new_regions) if new_regions else None,
                                    facilities=json.dumps(new_facilities) if new_facilities else None,
                                    is_major=new_major)
                db.add_update(issue_id, user["Id"], comment.strip(), status_change,
                              json.dumps(edits) if edits else None)
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
        render_history(db.list_updates(issue_id), on_delete=db.delete_update,
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
            projects = [p for p in projects if user["Id"] in (p["AssignedTo"], p["CreatedBy"])]
        if search:
            s = search.lower()
            projects = [p for p in projects if s in p["Title"].lower() or s in p["Summary"].lower()]

        if not projects:
            st.info("No projects match the current filters.")
            return

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
            st.rerun()
    if editable and (user["IsAdmin"] or proj["CreatedBy"] == user["Id"]):
        with h2.popover("🗑 Delete", use_container_width=True):
            st.warning("Permanently delete this project and its entire history?")
            if st.button("Yes, delete permanently", type="primary", key=f"delproj_{project_id}"):
                db.delete_project(project_id)
                st.session_state.selected_project = None
                st.toast(f"Project #{project_id} deleted.")
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
        render_history(db.list_project_updates(project_id), on_delete=db.delete_project_update,
                       can_delete=lambda u: user["IsAdmin"] or u["AuthorId"] == user["Id"])

    live_history()


# ---------------------------------------------------------------- admin

def page_admin(user, config):
    st.header("Admin — User Management")

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
                    st.success(f"Password reset for {u['Username']}. They'll be asked to "
                               "choose a new one at next login.")
                else:
                    st.error("Enter a new password first.")
            toggle_label = "Deactivate" if u["IsActive"] else "Reactivate"
            if col4.button(toggle_label, key=f"toggle_{u['Id']}"):
                db.set_user_active(u["Id"], not u["IsActive"])
                st.rerun()
            if u["Id"] != user["Id"]:
                admin_label = "Remove admin" if u["IsAdmin"] else "Make admin"
                if col4.button(admin_label, key=f"adm_{u['Id']}"):
                    db.set_user_admin(u["Id"], not u["IsAdmin"])
                    st.rerun()
            if u["TotpSecret"] and col4.button("Reset 2FA", key=f"totp_{u['Id']}"):
                db.set_user_totp_secret(u["Id"], None)
                st.success(f"2FA reset for {u['Username']}. They'll re-enroll at next login.")

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
                    st.rerun()

            with st.form(f"add_fac_{r['Id']}", clear_on_submit=True):
                c1, c2, c3 = st.columns([3, 2, 1], vertical_alignment="bottom")
                af_name = c1.text_input("New facility name")
                af_code = c2.text_input("Code")
                if c3.form_submit_button("Add", use_container_width=True):
                    if af_name.strip():
                        db.create_facility(r["Id"], af_name.strip(), af_code.strip() or None)
                        st.rerun()


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
        </style>
    """, unsafe_allow_html=True)

    pages = ["Issues", "Projects"]
    if user["IsAdmin"]:
        pages.append("Admin")
    icons = {"Issues": "📋", "Projects": "🗂️", "Admin": "⚙️"}
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
    elif page == "Admin":
        page_admin(user, config)


main()
