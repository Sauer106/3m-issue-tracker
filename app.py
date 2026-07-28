"""3M Issue Tracker — Streamlit app.

Run with:  streamlit run app.py --server.address 0.0.0.0 --server.port 8501
"""
import pandas as pd
import streamlit as st

import auth
import db
import reporting

STATUSES = ["Open", "In Progress", "Resolved", "Closed"]
PRIORITIES = ["Critical", "High", "Medium", "Low"]

st.set_page_config(page_title="3M Issue Tracker", page_icon="🎯", layout="wide")


def get_categories(config):
    return [c.strip() for c in config["app"].get("categories", "Other").split(",")]


# ---------------------------------------------------------------- login

def login_screen():
    st.title("3M Issue Tracker")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in", type="primary"):
            user = db.get_user_by_username(username.strip())
            if user and user["IsActive"] and auth.verify_password(password, user["PasswordHash"]):
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid username or password.")


# ---------------------------------------------------------------- report issue

def page_report(user, config):
    st.header("Report a New Issue")
    users = db.list_users(active_only=True)
    names = {u["DisplayName"]: u["Id"] for u in users}
    with st.form("report_issue", clear_on_submit=True):
        title = st.text_input("Title", max_chars=200)
        description = st.text_area("Description", height=150,
                                   placeholder="What's happening in 3M? Include steps to reproduce if applicable.")
        col1, col2, col3 = st.columns(3)
        category = col1.selectbox("Category", get_categories(config))
        priority = col2.selectbox("Priority", PRIORITIES, index=2)
        assignee = col3.selectbox("Assign to", ["(Unassigned)"] + list(names))
        if st.form_submit_button("Submit Issue", type="primary"):
            if not title.strip() or not description.strip():
                st.error("Title and description are required.")
            else:
                issue_id = db.create_issue(
                    title.strip(), description.strip(), category, priority,
                    user["Id"], names.get(assignee),
                )
                st.success(f"Issue #{issue_id} created.")


# ---------------------------------------------------------------- browse / detail

def page_issues(user, config):
    st.header("Issues")
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    status_filter = col1.multiselect("Status", STATUSES, default=["Open", "In Progress"])
    priority_filter = col2.multiselect("Priority", PRIORITIES)
    search = col3.text_input("Search title/description")
    mine_only = col4.checkbox("Mine only")

    issues = db.list_issues(statuses=status_filter or None)
    if priority_filter:
        issues = [i for i in issues if i["Priority"] in priority_filter]
    if mine_only:
        issues = [i for i in issues if user["Id"] in (i["AssignedTo"], i["ReportedBy"])]
    if search:
        s = search.lower()
        issues = [i for i in issues if s in i["Title"].lower() or s in i["Description"].lower()]

    if not issues:
        st.info("No issues match the current filters.")
        return

    df = pd.DataFrame([
        {
            "ID": i["Id"], "Title": i["Title"], "Priority": i["Priority"],
            "Status": i["Status"], "Category": i["Category"],
            "Assigned To": i["AssignedToName"] or "—",
            "Reported By": i["ReportedByName"],
            "Last Update": i["LastUpdateAt"].strftime("%Y-%m-%d %H:%M") if i["LastUpdateAt"] else "never",
            "Opened": i["CreatedAt"].strftime("%Y-%m-%d"),
        }
        for i in issues
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    labels = {f"#{i['Id']} — {i['Title']}": i["Id"] for i in issues}
    choice = st.selectbox("View / update an issue", list(labels))
    issue_detail(labels[choice], user)


def issue_detail(issue_id, user):
    issue = db.get_issue(issue_id)
    if not issue:
        st.error("Issue not found.")
        return
    st.divider()
    st.subheader(f"#{issue['Id']} — {issue['Title']}")
    meta1, meta2, meta3, meta4 = st.columns(4)
    meta1.metric("Status", issue["Status"])
    meta2.metric("Priority", issue["Priority"])
    meta3.metric("Assigned To", issue["AssignedToName"] or "Unassigned")
    meta4.metric("Category", issue["Category"])
    st.markdown(f"**Reported by** {issue['ReportedByName']} on {issue['CreatedAt']:%Y-%m-%d %H:%M}")
    st.markdown(issue["Description"])

    users = db.list_users(active_only=True)
    names = {u["DisplayName"]: u["Id"] for u in users}
    assignee_options = ["(Unassigned)"] + list(names)
    current_assignee = issue["AssignedToName"] or "(Unassigned)"

    with st.form(f"update_{issue_id}"):
        st.markdown("**Add an update**")
        comment = st.text_area("Update", height=100, label_visibility="collapsed",
                               placeholder="What's the latest on this issue?")
        col1, col2, col3 = st.columns(3)
        new_status = col1.selectbox("Status", STATUSES, index=STATUSES.index(issue["Status"]))
        new_priority = col2.selectbox("Priority", PRIORITIES, index=PRIORITIES.index(issue["Priority"]))
        new_assignee = col3.selectbox("Assign to", assignee_options,
                                      index=assignee_options.index(current_assignee))
        if st.form_submit_button("Save Update", type="primary"):
            status_change = None
            if new_status != issue["Status"]:
                status_change = f"{issue['Status']} -> {new_status}"
            if not comment.strip() and not status_change:
                st.error("Enter an update, or change the status.")
            else:
                db.set_issue_fields(issue_id, status=new_status, priority=new_priority,
                                    assigned_to=names.get(new_assignee))
                db.add_update(issue_id, user["Id"],
                              comment.strip() or f"Status changed: {status_change}", status_change)
                st.success("Update saved.")
                st.rerun()

    updates = db.list_updates(issue_id)
    if updates:
        st.markdown("**History**")
        for u in updates:
            suffix = f" · _{u['StatusChange']}_" if u["StatusChange"] else ""
            with st.container(border=True):
                st.markdown(f"**{u['AuthorName']}** · {u['CreatedAt']:%Y-%m-%d %H:%M}{suffix}")
                st.markdown(u["Comment"])


# ---------------------------------------------------------------- admin

def page_admin(config):
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
                                   auth.hash_password(temp_password), is_admin)
                    st.success(f"User '{username.strip()}' created.")

    st.subheader("Existing users")
    for u in db.list_users():
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
            role = "Admin" if u["IsAdmin"] else "User"
            state = "Active" if u["IsActive"] else "Inactive"
            col1.markdown(f"**{u['DisplayName']}** (`{u['Username']}`)")
            col2.markdown(f"{u['Email']}  \n{role} · {state}")
            new_pw = col3.text_input("New password", type="password", key=f"pw_{u['Id']}",
                                     label_visibility="collapsed", placeholder="New password")
            if col3.button("Reset password", key=f"reset_{u['Id']}"):
                if new_pw:
                    db.set_user_password(u["Id"], auth.hash_password(new_pw))
                    st.success(f"Password reset for {u['Username']}.")
                else:
                    st.error("Enter a new password first.")
            toggle_label = "Deactivate" if u["IsActive"] else "Reactivate"
            if col4.button(toggle_label, key=f"toggle_{u['Id']}"):
                db.set_user_active(u["Id"], not u["IsActive"])
                st.rerun()


# ---------------------------------------------------------------- main

def main():
    config = db.get_config()
    if "user" not in st.session_state:
        login_screen()
        return

    user = st.session_state.user
    deadline = reporting.upcoming_deadline(config)

    with st.sidebar:
        st.title("3M Issue Tracker")
        st.markdown(f"Signed in as **{user['DisplayName']}**")
        st.info(f"Updates due **{deadline:%a %b %d} at 2:00 PM EST**")
        pages = ["Issues", "Report Issue"]
        if user["IsAdmin"]:
            pages.append("Admin")
        page = st.radio("Navigate", pages, label_visibility="collapsed")
        if st.button("Log out"):
            del st.session_state.user
            st.rerun()

    if page == "Issues":
        page_issues(user, config)
    elif page == "Report Issue":
        page_report(user, config)
    elif page == "Admin":
        page_admin(config)


main()
