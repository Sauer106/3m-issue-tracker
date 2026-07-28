"""Shared database access for the 3M Issue Tracker.

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


def list_users(active_only=False):
    sql = "SELECT * FROM Users"
    if active_only:
        sql += " WHERE IsActive = 1"
    return query(sql + " ORDER BY DisplayName")


def create_user(username, display_name, email, password_hash, is_admin=False):
    return insert_returning_id(
        """INSERT INTO Users (Username, DisplayName, Email, PasswordHash, IsAdmin)
           OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?)""",
        (username, display_name, email, password_hash, 1 if is_admin else 0),
    )


def set_user_password(user_id, password_hash):
    execute("UPDATE Users SET PasswordHash = ? WHERE Id = ?", (password_hash, user_id))


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


def list_issues(statuses=None):
    sql = ISSUE_SELECT
    params = ()
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        sql += f" WHERE i.Status IN ({placeholders})"
        params = tuple(statuses)
    return query(sql + " ORDER BY i.Id DESC", params)


def get_issue(issue_id):
    rows = query(ISSUE_SELECT + " WHERE i.Id = ?", (issue_id,))
    return rows[0] if rows else None


def create_issue(title, description, category, priority, reported_by, assigned_to=None):
    return insert_returning_id(
        """INSERT INTO Issues (Title, Description, Category, Priority, ReportedBy, AssignedTo)
           OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?)""",
        (title, description, category, priority, reported_by, assigned_to),
    )


def add_update(issue_id, author_id, comment, status_change=None):
    execute(
        """INSERT INTO IssueUpdates (IssueId, AuthorId, Comment, StatusChange)
           VALUES (?, ?, ?, ?)""",
        (issue_id, author_id, comment, status_change),
    )
    execute("UPDATE Issues SET UpdatedAt = SYSDATETIME() WHERE Id = ?", (issue_id,))


def set_issue_fields(issue_id, status=None, priority=None, assigned_to="__unchanged__"):
    sets, params = ["UpdatedAt = SYSDATETIME()"], []
    if status is not None:
        sets.append("Status = ?")
        params.append(status)
        if status in ("Resolved", "Closed"):
            sets.append("ResolvedAt = COALESCE(ResolvedAt, SYSDATETIME())")
        else:
            sets.append("ResolvedAt = NULL")
    if priority is not None:
        sets.append("Priority = ?")
        params.append(priority)
    if assigned_to != "__unchanged__":
        sets.append("AssignedTo = ?")
        params.append(assigned_to)
    params.append(issue_id)
    execute(f"UPDATE Issues SET {', '.join(sets)} WHERE Id = ?", tuple(params))


def list_updates(issue_id):
    return query(
        """SELECT u.*, usr.DisplayName AS AuthorName
           FROM IssueUpdates u JOIN Users usr ON usr.Id = u.AuthorId
           WHERE u.IssueId = ? ORDER BY u.CreatedAt DESC""",
        (issue_id,),
    )


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
