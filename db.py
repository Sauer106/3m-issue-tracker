"""Shared database access for the 3M Issues & Projects Tracker.

Used by the Streamlit app (app.py) and the scheduled email scripts.
Reads connection settings from config.ini next to this file.
"""
import configparser
from pathlib import Path

import pyodbc

CONFIG_PATH = Path(__file__).resolve().parent / "config.ini"
_config = None


def get_config():
    global _config
    if _config is None:
        if not CONFIG_PATH.exists():
            raise FileNotFoundError(
                f"Missing {CONFIG_PATH}. Copy config.example.ini to config.ini and edit it."
            )
        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_PATH)
        _config = cfg
    return _config


def get_conn():
    dbcfg = get_config()["database"]
    parts = [
        f"DRIVER={{{dbcfg.get('driver', 'ODBC Driver 18 for SQL Server')}}}",
        f"SERVER={dbcfg['server']}",
        f"DATABASE={dbcfg['database']}",
        "TrustServerCertificate=yes",
    ]
    if dbcfg.getboolean("trusted_connection", fallback=True):
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={dbcfg['username']}")
        parts.append(f"PWD={dbcfg['password']}")
    return pyodbc.connect(";".join(parts))


def env_diagnostics():
    """Best-effort environment info for bug reports: the configured and installed
    ODBC drivers, the pyodbc version, and the SQL Server banner. Never raises —
    any piece that can't be read comes back as 'unknown'/'unavailable'."""
    info = {"configured_driver": "unknown", "pyodbc": "unknown",
            "installed_drivers": [], "sql_server": "unknown"}
    try:
        info["configured_driver"] = get_config()["database"].get(
            "driver", "ODBC Driver 18 for SQL Server")
    except Exception:  # noqa: BLE001
        pass
    try:
        info["pyodbc"] = pyodbc.version
    except Exception:  # noqa: BLE001
        pass
    try:
        info["installed_drivers"] = [d for d in pyodbc.drivers() if "SQL Server" in d]
    except Exception:  # noqa: BLE001
        pass
    try:
        row = query("SELECT @@VERSION AS v")
        banner = (row[0]["v"] or "") if row else ""
        info["sql_server"] = banner.splitlines()[0].strip() if banner else "unknown"
    except Exception as exc:  # noqa: BLE001
        info["sql_server"] = f"unavailable ({exc})"
    return info


def query(sql, params=()):
    """Run a SELECT and return a list of dicts."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def execute(sql, params=()):
    """Run an INSERT/UPDATE/DELETE and commit."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()


def insert_returning_id(sql, params=()):
    """Run an INSERT that includes an OUTPUT INSERTED.Id clause; return the new id."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        new_id = cur.fetchone()[0]
        conn.commit()
        return int(new_id)


# ---------------------------------------------------------------- users

def get_user_by_username(username):
    rows = query("SELECT * FROM Users WHERE Username = ?", (username,))
    return rows[0] if rows else None


def get_user_by_id(user_id):
    rows = query("SELECT * FROM Users WHERE Id = ?", (user_id,))
    return rows[0] if rows else None


def list_users(active_only=False):
    sql = "SELECT * FROM Users"
    if active_only:
        sql += " WHERE IsActive = 1"
    return query(sql + " ORDER BY DisplayName")


def create_user(username, display_name, email, password_hash, is_admin=False, must_change=False):
    return insert_returning_id(
        """INSERT INTO Users (Username, DisplayName, Email, PasswordHash, IsAdmin, MustChangePassword)
           OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?)""",
        (username, display_name, email, password_hash, 1 if is_admin else 0, 1 if must_change else 0),
    )


LOCKOUT_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def record_failed_login(user_id):
    """Count a failed password/2FA attempt; the 5th locks the account for 15 min."""
    execute(
        """UPDATE Users SET
             LockedUntil = CASE WHEN FailedLogins + 1 >= ?
                                THEN DATEADD(MINUTE, ?, SYSDATETIME()) ELSE LockedUntil END,
             FailedLogins = CASE WHEN FailedLogins + 1 >= ? THEN 0 ELSE FailedLogins + 1 END
           WHERE Id = ?""",
        (LOCKOUT_ATTEMPTS, LOCKOUT_MINUTES, LOCKOUT_ATTEMPTS, user_id),
    )


def clear_failed_logins(user_id):
    execute("UPDATE Users SET FailedLogins = 0, LockedUntil = NULL WHERE Id = ?", (user_id,))


def set_user_password(user_id, password_hash, must_change=False):
    execute("UPDATE Users SET PasswordHash = ?, MustChangePassword = ? WHERE Id = ?",
            (password_hash, 1 if must_change else 0, user_id))


def set_user_totp_secret(user_id, secret):
    """Set the TOTP seed after enrollment, or None to force re-enrollment."""
    execute("UPDATE Users SET TotpSecret = ? WHERE Id = ?", (secret, user_id))


def set_user_admin(user_id, is_admin):
    execute("UPDATE Users SET IsAdmin = ? WHERE Id = ?", (1 if is_admin else 0, user_id))


def set_user_email_prefs(user_id, receives_digest, receives_reminders):
    execute("UPDATE Users SET ReceivesDigest = ?, ReceivesReminders = ? WHERE Id = ?",
            (1 if receives_digest else 0, 1 if receives_reminders else 0, user_id))


def _execute_count(sql, params):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        n = cur.rowcount
        conn.commit()
        return n


def reassign_issues(from_user_id, to_user_id, open_only=True):
    sql = "UPDATE Issues SET AssignedTo = ?, UpdatedAt = SYSDATETIME() WHERE AssignedTo = ?"
    if open_only:
        sql += " AND Status IN ('Open', 'In Progress', 'Waiting on Solventum', 'Hold')"
    return _execute_count(sql, (to_user_id, from_user_id))


def reassign_projects(from_user_id, to_user_id, open_only=True):
    sql = "UPDATE Projects SET AssignedTo = ?, UpdatedAt = SYSDATETIME() WHERE AssignedTo = ?"
    if open_only:
        sql += " AND Status IN ('Planned', 'In Progress', 'On Hold')"
    return _execute_count(sql, (to_user_id, from_user_id))


def set_user_active(user_id, is_active):
    execute("UPDATE Users SET IsActive = ? WHERE Id = ?", (1 if is_active else 0, user_id))


# ---------------------------------------------------------------- issues

ISSUE_SELECT = """
SELECT i.*, r.DisplayName AS ReportedByName, a.DisplayName AS AssignedToName,
       (SELECT MAX(u.CreatedAt) FROM IssueUpdates u WHERE u.IssueId = i.Id) AS LastUpdateAt
FROM Issues i
JOIN Users r ON r.Id = i.ReportedBy
LEFT JOIN Users a ON a.Id = i.AssignedTo
"""


def list_issues(statuses=None, include_deleted=False):
    clauses, params = [], []
    if not include_deleted:
        clauses.append("i.DeletedAt IS NULL")
    if statuses:
        clauses.append("i.Status IN (" + ",".join("?" for _ in statuses) + ")")
        params += list(statuses)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return query(ISSUE_SELECT + where + " ORDER BY i.Id DESC", tuple(params))


def list_deleted_issues():
    return query(
        """SELECT i.Id, i.Title, i.Status, i.DeletedAt, d.DisplayName AS DeletedByName
           FROM Issues i LEFT JOIN Users d ON d.Id = i.DeletedBy
           WHERE i.DeletedAt IS NOT NULL ORDER BY i.DeletedAt DESC""")


def get_issue(issue_id):
    rows = query(ISSUE_SELECT + " WHERE i.Id = ?", (issue_id,))
    return rows[0] if rows else None


def create_issue(title, description, reported_by, assigned_to=None,
                 solventum_ticket=None, servicedesk_ticket=None, regions=None, facilities=None,
                 is_major=False, due_date=None, regions_checked=None, regions_checked_reason=None,
                 impact=None, current_action=None):
    return insert_returning_id(
        """INSERT INTO Issues (Title, Description, ReportedBy, AssignedTo, SolventumTicket,
                               ServiceDeskTicket, Regions, Facilities, IsMajor, DueDate,
                               RegionsChecked, RegionsCheckedReason, Impact, CurrentAction)
           OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, description, reported_by, assigned_to, solventum_ticket, servicedesk_ticket,
         regions, facilities, 1 if is_major else 0, due_date, regions_checked,
         regions_checked_reason, impact, current_action),
    )


def add_update(issue_id, author_id, comment, status_change=None, field_changes=None,
               is_fix_proposal=False):
    execute(
        """INSERT INTO IssueUpdates (IssueId, AuthorId, Comment, StatusChange, FieldChanges,
                                     IsFixProposal, ProposalStatus)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (issue_id, author_id, comment, status_change, field_changes,
         1 if is_fix_proposal else 0, "Pending" if is_fix_proposal else None),
    )
    execute("UPDATE Issues SET UpdatedAt = SYSDATETIME() WHERE Id = ?", (issue_id,))


def set_proposal_status(update_id, status):
    execute("UPDATE IssueUpdates SET ProposalStatus = ? WHERE Id = ?", (status, update_id))


def set_issue_fields(issue_id, status=None, assigned_to="__unchanged__",
                     solventum_ticket="__unchanged__", servicedesk_ticket="__unchanged__",
                     regions="__unchanged__", facilities="__unchanged__", is_major="__unchanged__",
                     due_date="__unchanged__", regions_checked="__unchanged__",
                     regions_checked_reason="__unchanged__",
                     fix_applied_all_regions="__unchanged__", fix_not_applied_reason="__unchanged__",
                     fix_all_regions_by="__unchanged__",
                     impact="__unchanged__", other_regions_affected="__unchanged__",
                     current_action="__unchanged__"):
    sets, params = ["UpdatedAt = SYSDATETIME()"], []
    if due_date != "__unchanged__":
        sets.append("DueDate = ?")
        params.append(due_date)
    if status is not None:
        sets.append("Status = ?")
        params.append(status)
        if status == "Closed":
            sets.append("ResolvedAt = COALESCE(ResolvedAt, SYSDATETIME())")
        else:
            sets.append("ResolvedAt = NULL")
    if assigned_to != "__unchanged__":
        sets.append("AssignedTo = ?")
        params.append(assigned_to)
    if solventum_ticket != "__unchanged__":
        sets.append("SolventumTicket = ?")
        params.append(solventum_ticket)
    if servicedesk_ticket != "__unchanged__":
        sets.append("ServiceDeskTicket = ?")
        params.append(servicedesk_ticket)
    if regions != "__unchanged__":
        sets.append("Regions = ?")
        params.append(regions)
    if facilities != "__unchanged__":
        sets.append("Facilities = ?")
        params.append(facilities)
    if is_major != "__unchanged__":
        sets.append("IsMajor = ?")
        params.append(1 if is_major else 0)
    if regions_checked != "__unchanged__":
        sets.append("RegionsChecked = ?")
        params.append(regions_checked)
    if regions_checked_reason != "__unchanged__":
        sets.append("RegionsCheckedReason = ?")
        params.append(regions_checked_reason)
    if fix_applied_all_regions != "__unchanged__":
        sets.append("FixAppliedAllRegions = ?")
        params.append(fix_applied_all_regions)
    if fix_not_applied_reason != "__unchanged__":
        sets.append("FixNotAppliedReason = ?")
        params.append(fix_not_applied_reason)
    if fix_all_regions_by != "__unchanged__":
        sets.append("FixAllRegionsBy = ?")
        params.append(fix_all_regions_by)
    if impact != "__unchanged__":
        sets.append("Impact = ?")
        params.append(impact)
    if other_regions_affected != "__unchanged__":
        sets.append("OtherRegionsAffected = ?")
        params.append(other_regions_affected)
    if current_action != "__unchanged__":
        sets.append("CurrentAction = ?")
        params.append(current_action)
    params.append(issue_id)
    execute(f"UPDATE Issues SET {', '.join(sets)} WHERE Id = ?", tuple(params))


def delete_update(update_id):
    execute("DELETE FROM IssueUpdates WHERE Id = ?", (update_id,))


def delete_issue(issue_id, deleted_by):
    """Soft delete: hide the issue (and its history) but keep it for restore."""
    execute("UPDATE Issues SET DeletedAt = SYSDATETIME(), DeletedBy = ? WHERE Id = ?",
            (deleted_by, issue_id))


def restore_issue(issue_id):
    execute("UPDATE Issues SET DeletedAt = NULL, DeletedBy = NULL WHERE Id = ?", (issue_id,))


def purge_issue(issue_id):
    """Permanent hard delete from the recycle bin, including updates and attachments."""
    execute("DELETE FROM Attachments WHERE ParentType = 'issue' AND ParentId = ?", (issue_id,))
    execute("DELETE FROM IssueUpdates WHERE IssueId = ?", (issue_id,))
    execute("DELETE FROM Issues WHERE Id = ?", (issue_id,))


def list_updates(issue_id):
    return query(
        """SELECT u.*, usr.DisplayName AS AuthorName
           FROM IssueUpdates u JOIN Users usr ON usr.Id = u.AuthorId
           WHERE u.IssueId = ? ORDER BY u.CreatedAt DESC""",
        (issue_id,),
    )


# ---------------------------------------------------------------- projects

PROJECT_SELECT = """
SELECT p.*, c.DisplayName AS CreatedByName, a.DisplayName AS AssignedToName,
       (SELECT MAX(u.CreatedAt) FROM ProjectUpdates u WHERE u.ProjectId = p.Id) AS LastUpdateAt
FROM Projects p
JOIN Users c ON c.Id = p.CreatedBy
LEFT JOIN Users a ON a.Id = p.AssignedTo
"""


def list_projects(statuses=None, include_deleted=False):
    clauses, params = [], []
    if not include_deleted:
        clauses.append("p.DeletedAt IS NULL")
    if statuses:
        clauses.append("p.Status IN (" + ",".join("?" for _ in statuses) + ")")
        params += list(statuses)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return query(PROJECT_SELECT + where + " ORDER BY p.Id DESC", tuple(params))


def list_deleted_projects():
    return query(
        """SELECT p.Id, p.Title, p.Status, p.DeletedAt, d.DisplayName AS DeletedByName
           FROM Projects p LEFT JOIN Users d ON d.Id = p.DeletedBy
           WHERE p.DeletedAt IS NOT NULL ORDER BY p.DeletedAt DESC""")


def get_project(project_id):
    rows = query(PROJECT_SELECT + " WHERE p.Id = ?", (project_id,))
    return rows[0] if rows else None


def create_project(title, summary, created_by, assigned_to=None,
                   solventum_ticket=None, servicedesk_ticket=None, regions=None, facilities=None):
    return insert_returning_id(
        """INSERT INTO Projects (Title, Summary, CreatedBy, AssignedTo, SolventumTicket,
                                 ServiceDeskTicket, Regions, Facilities)
           OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, summary, created_by, assigned_to, solventum_ticket, servicedesk_ticket,
         regions, facilities),
    )


def set_project_fields(project_id, status=None, assigned_to="__unchanged__",
                       solventum_ticket="__unchanged__", servicedesk_ticket="__unchanged__",
                       regions="__unchanged__", facilities="__unchanged__"):
    sets, params = ["UpdatedAt = SYSDATETIME()"], []
    if status is not None:
        sets.append("Status = ?")
        params.append(status)
    if assigned_to != "__unchanged__":
        sets.append("AssignedTo = ?")
        params.append(assigned_to)
    if solventum_ticket != "__unchanged__":
        sets.append("SolventumTicket = ?")
        params.append(solventum_ticket)
    if servicedesk_ticket != "__unchanged__":
        sets.append("ServiceDeskTicket = ?")
        params.append(servicedesk_ticket)
    if regions != "__unchanged__":
        sets.append("Regions = ?")
        params.append(regions)
    if facilities != "__unchanged__":
        sets.append("Facilities = ?")
        params.append(facilities)
    params.append(project_id)
    execute(f"UPDATE Projects SET {', '.join(sets)} WHERE Id = ?", tuple(params))


def add_project_update(project_id, author_id, comment, status_change=None, field_changes=None):
    execute(
        """INSERT INTO ProjectUpdates (ProjectId, AuthorId, Comment, StatusChange, FieldChanges)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, author_id, comment, status_change, field_changes),
    )
    execute("UPDATE Projects SET UpdatedAt = SYSDATETIME() WHERE Id = ?", (project_id,))


def delete_project_update(update_id):
    execute("DELETE FROM ProjectUpdates WHERE Id = ?", (update_id,))


def delete_project(project_id, deleted_by):
    """Soft delete: hide the project (and its history) but keep it for restore."""
    execute("UPDATE Projects SET DeletedAt = SYSDATETIME(), DeletedBy = ? WHERE Id = ?",
            (deleted_by, project_id))


def restore_project(project_id):
    execute("UPDATE Projects SET DeletedAt = NULL, DeletedBy = NULL WHERE Id = ?", (project_id,))


def purge_project(project_id):
    """Permanent hard delete from the recycle bin, including updates and attachments."""
    execute("DELETE FROM Attachments WHERE ParentType = 'project' AND ParentId = ?", (project_id,))
    execute("DELETE FROM ProjectUpdates WHERE ProjectId = ?", (project_id,))
    execute("DELETE FROM CalendarEventProjects WHERE ProjectId = ?", (project_id,))
    execute("DELETE FROM ProjectMilestones WHERE ProjectId = ?", (project_id,))
    execute("DELETE FROM Projects WHERE Id = ?", (project_id,))


# ---------------------------------------------------------------- project milestones

def list_milestones(project_id):
    """Milestones for a project: open ones first (soonest date first), then done."""
    return query(
        """SELECT * FROM ProjectMilestones WHERE ProjectId = ?
           ORDER BY Done,
                    CASE WHEN DueDate IS NULL THEN 1 ELSE 0 END, DueDate, Id""",
        (project_id,),
    )


def add_milestone(project_id, name, due_date=None):
    return insert_returning_id(
        "INSERT INTO ProjectMilestones (ProjectId, Name, DueDate) OUTPUT INSERTED.Id VALUES (?, ?, ?)",
        (project_id, name, due_date),
    )


def update_milestone(milestone_id, name=None, due_date="__unchanged__", done=None):
    sets, params = [], []
    if name is not None:
        sets.append("Name = ?")
        params.append(name)
    if due_date != "__unchanged__":
        sets.append("DueDate = ?")
        params.append(due_date)
    if done is not None:
        sets.append("Done = ?")
        params.append(1 if done else 0)
    if not sets:
        return
    params.append(milestone_id)
    execute(f"UPDATE ProjectMilestones SET {', '.join(sets)} WHERE Id = ?", tuple(params))


def delete_milestone(milestone_id):
    execute("DELETE FROM ProjectMilestones WHERE Id = ?", (milestone_id,))


def list_overdue_milestones():
    """Open, past-due milestones on live projects (not deleted/Completed/Cancelled)."""
    return query(
        """SELECT m.Id, m.Name, m.DueDate, m.ProjectId, p.Title AS ProjectTitle,
                  p.Status AS ProjectStatus, p.AssignedTo AS AssignedTo,
                  a.DisplayName AS AssignedToName
           FROM ProjectMilestones m
           JOIN Projects p ON p.Id = m.ProjectId
           LEFT JOIN Users a ON a.Id = p.AssignedTo
           WHERE m.Done = 0 AND m.DueDate IS NOT NULL
                 AND m.DueDate < CAST(SYSDATETIME() AS DATE)
                 AND p.DeletedAt IS NULL
                 AND p.Status NOT IN ('Completed', 'Cancelled')
           ORDER BY m.DueDate""")


def next_milestones_map():
    """The next open (incomplete) milestone per project, for the project cards."""
    rows = query(
        """SELECT ProjectId, Name, DueDate FROM (
               SELECT ProjectId, Name, DueDate,
                      ROW_NUMBER() OVER (PARTITION BY ProjectId
                        ORDER BY CASE WHEN DueDate IS NULL THEN 1 ELSE 0 END, DueDate, Id) rn
               FROM ProjectMilestones WHERE Done = 0
           ) t WHERE rn = 1""")
    return {r["ProjectId"]: r for r in rows}


def list_project_updates(project_id):
    return query(
        """SELECT u.*, usr.DisplayName AS AuthorName
           FROM ProjectUpdates u JOIN Users usr ON usr.Id = u.AuthorId
           WHERE u.ProjectId = ? ORDER BY u.CreatedAt DESC""",
        (project_id,),
    )


# ---------------------------------------------------------------- calendar

def create_event(title, event_date, created_by, event_time=None, end_date=None,
                 category="Other", description=None, project_ids=None):
    event_id = insert_returning_id(
        """INSERT INTO CalendarEvents (Title, EventDate, EventTime, EndDate, Category,
                                       Description, CreatedBy)
           OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, event_date, event_time, end_date, category, description, created_by),
    )
    set_event_projects(event_id, project_ids or [])
    return event_id


def update_event(event_id, title, event_date, event_time=None, end_date=None,
                 category="Other", description=None, project_ids=None):
    execute(
        """UPDATE CalendarEvents SET Title = ?, EventDate = ?, EventTime = ?, EndDate = ?,
                  Category = ?, Description = ?, UpdatedAt = SYSDATETIME() WHERE Id = ?""",
        (title, event_date, event_time, end_date, category, description, event_id),
    )
    if project_ids is not None:
        set_event_projects(event_id, project_ids)


def delete_event(event_id):
    """Hard delete; the link rows go via ON DELETE CASCADE."""
    execute("DELETE FROM CalendarEvents WHERE Id = ?", (event_id,))


def set_event_projects(event_id, project_ids):
    """Replace the set of Projects linked to an event."""
    execute("DELETE FROM CalendarEventProjects WHERE EventId = ?", (event_id,))
    for pid in dict.fromkeys(project_ids):  # de-dup, keep order
        execute("INSERT INTO CalendarEventProjects (EventId, ProjectId) VALUES (?, ?)",
                (event_id, pid))


EVENT_SELECT = """
SELECT e.*, u.DisplayName AS CreatedByName
FROM CalendarEvents e JOIN Users u ON u.Id = e.CreatedBy
"""


def get_event(event_id):
    rows = query(EVENT_SELECT + " WHERE e.Id = ?", (event_id,))
    return rows[0] if rows else None


def list_events(start_date, end_date):
    """Events that touch the [start_date, end_date] window (inclusive), accounting
    for optional multi-day spans (EndDate)."""
    return query(
        EVENT_SELECT + """ WHERE e.EventDate <= ?
              AND COALESCE(e.EndDate, e.EventDate) >= ?
           ORDER BY e.EventDate, e.EventTime""",
        (end_date, start_date),
    )


def list_event_projects(event_id):
    return query(
        """SELECT p.Id, p.Title, p.Status FROM CalendarEventProjects ep
           JOIN Projects p ON p.Id = ep.ProjectId
           WHERE ep.EventId = ? AND p.DeletedAt IS NULL
           ORDER BY p.Title""",
        (event_id,),
    )


def list_events_for_project(project_id):
    return query(
        EVENT_SELECT + """ JOIN CalendarEventProjects ep ON ep.EventId = e.Id
           WHERE ep.ProjectId = ? ORDER BY e.EventDate, e.EventTime""",
        (project_id,),
    )


# ---------------------------------------------------------------- presence

LOCK_IDLE_SECONDS = 600   # a lock holder idle this long loses the lock to a waiting viewer


def touch_presence(user_id, page_key, activity=False):
    """Heartbeat (activity=False) or real user interaction (activity=True)."""
    execute(
        """MERGE Presence AS t
           USING (SELECT ? AS UserId, ? AS PageKey) AS s
           ON t.UserId = s.UserId AND t.PageKey = s.PageKey
           WHEN MATCHED THEN UPDATE SET
               FirstSeen = CASE WHEN t.LastSeen < DATEADD(SECOND, -20, SYSDATETIME())
                                THEN SYSDATETIME() ELSE t.FirstSeen END,
               LastActivity = CASE WHEN ? = 1 THEN SYSDATETIME() ELSE t.LastActivity END,
               LastSeen = SYSDATETIME()
           WHEN NOT MATCHED THEN INSERT (UserId, PageKey) VALUES (s.UserId, s.PageKey);""",
        (user_id, page_key, 1 if activity else 0),
    )
    execute("DELETE FROM Presence WHERE LastSeen < DATEADD(HOUR, -1, SYSDATETIME())")


def get_lock_owner(page_key):
    """The active, non-idle viewer who arrived first holds the edit lock.
    An idle holder is requeued when someone active is waiting."""
    execute(
        """UPDATE p SET FirstSeen = SYSDATETIME()
           FROM Presence p
           WHERE p.PageKey = ?
             AND p.LastSeen >= DATEADD(SECOND, -20, SYSDATETIME())
             AND p.LastActivity < DATEADD(SECOND, -?, SYSDATETIME())
             AND EXISTS (SELECT 1 FROM Presence p2
                         WHERE p2.PageKey = p.PageKey
                           AND p2.LastSeen >= DATEADD(SECOND, -20, SYSDATETIME())
                           AND p2.LastActivity >= DATEADD(SECOND, -?, SYSDATETIME()))""",
        (page_key, LOCK_IDLE_SECONDS, LOCK_IDLE_SECONDS),
    )
    rows = query(
        """SELECT TOP 1 p.UserId, u.DisplayName
           FROM Presence p JOIN Users u ON u.Id = p.UserId
           WHERE p.PageKey = ? AND p.LastSeen >= DATEADD(SECOND, -20, SYSDATETIME())
           ORDER BY CASE WHEN p.LastActivity >= DATEADD(SECOND, -?, SYSDATETIME())
                         THEN 0 ELSE 1 END,
                    p.FirstSeen, p.UserId""",
        (page_key, LOCK_IDLE_SECONDS),
    )
    return rows[0] if rows else None


def take_lock(page_key, user_id):
    """Admin takeover: requeue every other active viewer so user_id holds the lock."""
    execute("UPDATE Presence SET FirstSeen = SYSDATETIME() WHERE PageKey = ? AND UserId <> ?",
            (page_key, user_id))


def list_presence(page_key, exclude_user_id, seconds=20):
    """Other users seen on this page within the last N seconds."""
    return query(
        """SELECT u.DisplayName FROM Presence p JOIN Users u ON u.Id = p.UserId
           WHERE p.PageKey = ? AND p.UserId <> ?
             AND p.LastSeen >= DATEADD(SECOND, -?, SYSDATETIME())
           ORDER BY u.DisplayName""",
        (page_key, exclude_user_id, seconds),
    )


# ---------------------------------------------------------------- attachments

def add_attachment(parent_type, parent_id, filename, content_type, content, uploaded_by):
    return insert_returning_id(
        """INSERT INTO Attachments (ParentType, ParentId, FileName, ContentType, Content, UploadedBy)
           OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?)""",
        (parent_type, parent_id, filename, content_type, pyodbc.Binary(content), uploaded_by),
    )


def list_attachments(parent_type, parent_id):
    """Attachment metadata only - content is fetched per-file via get_attachment."""
    return query(
        """SELECT a.Id, a.FileName, a.ContentType, a.UploadedBy, a.CreatedAt,
                  DATALENGTH(a.Content) AS SizeBytes, u.DisplayName AS UploadedByName
           FROM Attachments a JOIN Users u ON u.Id = a.UploadedBy
           WHERE a.ParentType = ? AND a.ParentId = ? ORDER BY a.CreatedAt""",
        (parent_type, parent_id),
    )


def get_attachment(attachment_id):
    rows = query("SELECT * FROM Attachments WHERE Id = ?", (attachment_id,))
    return rows[0] if rows else None


def delete_attachment(attachment_id):
    execute("DELETE FROM Attachments WHERE Id = ?", (attachment_id,))


# ---------------------------------------------------------------- regions & facilities

def facility_label(name, code):
    return f"{name} ({code})" if code else name


def get_region_map():
    """{region name: [facility display names]}, ordered - drives pickers and chips."""
    regions = query("SELECT * FROM Regions ORDER BY SortOrder, Name")
    facilities = query("SELECT * FROM Facilities ORDER BY SortOrder, Name")
    by_region = {r["Id"]: [] for r in regions}
    for f in facilities:
        by_region.setdefault(f["RegionId"], []).append(facility_label(f["Name"], f["Code"]))
    return {r["Name"]: by_region[r["Id"]] for r in regions}


def list_regions():
    return query("SELECT * FROM Regions ORDER BY SortOrder, Name")


def list_facilities(region_id):
    return query("SELECT * FROM Facilities WHERE RegionId = ? ORDER BY SortOrder, Name", (region_id,))


def create_region(name):
    return insert_returning_id(
        """INSERT INTO Regions (Name, SortOrder) OUTPUT INSERTED.Id
           SELECT ?, ISNULL(MAX(SortOrder), 0) + 1 FROM Regions""", (name,))


def rename_region(region_id, name):
    execute("UPDATE Regions SET Name = ? WHERE Id = ?", (name, region_id))


def delete_region(region_id):
    execute("DELETE FROM Regions WHERE Id = ?", (region_id,))   # facilities cascade


def create_facility(region_id, name, code):
    return insert_returning_id(
        """INSERT INTO Facilities (RegionId, Name, Code, SortOrder) OUTPUT INSERTED.Id
           SELECT ?, ?, ?, ISNULL(MAX(SortOrder), 0) + 1 FROM Facilities WHERE RegionId = ?""",
        (region_id, name, code, region_id))


def update_facility(facility_id, name, code):
    execute("UPDATE Facilities SET Name = ?, Code = ? WHERE Id = ?", (name, code, facility_id))


def delete_facility(facility_id):
    execute("DELETE FROM Facilities WHERE Id = ?", (facility_id,))


# ---------------------------------------------------------------- audit log

def audit(actor_id, action, detail=None):
    """Record an accountability-relevant action (deletions, admin actions).
    Returns the new AuditLog Id (callers that don't need it can ignore it)."""
    return insert_returning_id(
        "INSERT INTO AuditLog (ActorId, Action, Detail) OUTPUT INSERTED.Id VALUES (?, ?, ?)",
        (actor_id, action, (detail or "")[:400]))


def list_audit(limit=200):
    return query(
        """SELECT TOP (?) a.Id, a.Action, a.Detail, a.CreatedAt,
                  u.DisplayName AS ActorName
           FROM AuditLog a LEFT JOIN Users u ON u.Id = a.ActorId
           ORDER BY a.Id DESC""",
        (limit,),
    )


# ---------------------------------------------------------------- email recipients

def list_extra_recipients():
    return query("SELECT * FROM ExtraRecipients ORDER BY Email")


def add_extra_recipient(email, label=None):
    execute("INSERT INTO ExtraRecipients (Email, Label) VALUES (?, ?)", (email, label))


def delete_extra_recipient(recipient_id):
    execute("DELETE FROM ExtraRecipients WHERE Id = ?", (recipient_id,))


def digest_recipients():
    """Everyone who should receive the weekly digests: opted-in active users plus
    the managed extra-recipient list. De-duplicated, case-insensitive."""
    emails = [u["Email"] for u in list_users(active_only=True)
              if u["Email"] and u["ReceivesDigest"]]
    emails += [r["Email"] for r in list_extra_recipients() if r["Email"]]
    seen, out = set(), []
    for e in emails:
        if e.lower() not in seen:
            seen.add(e.lower())
            out.append(e)
    return sorted(out)


# ---------------------------------------------------------------- email log

def log_email(email_type, recipient, issue_id=None):
    execute(
        "INSERT INTO EmailLog (EmailType, IssueId, Recipient) VALUES (?, ?, ?)",
        (email_type, issue_id, recipient),
    )


def email_already_sent(email_type, recipient, since, issue_id=None):
    sql = "SELECT COUNT(*) AS N FROM EmailLog WHERE EmailType = ? AND Recipient = ? AND SentAt >= ?"
    params = [email_type, recipient, since]
    if issue_id is not None:
        sql += " AND IssueId = ?"
        params.append(issue_id)
    return query(sql, tuple(params))[0]["N"] > 0
