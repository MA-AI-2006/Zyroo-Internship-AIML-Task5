"""audit.py - workflow history and audit logging (SQLite)."""
from datetime import datetime, timezone

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   INTEGER NOT NULL,
    action        TEXT NOT NULL,
    previous_status TEXT,
    new_status    TEXT,
    timestamp     TEXT NOT NULL,
    reason        TEXT
)
"""


def init_audit_table(conn):
    conn.execute(CREATE_SQL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_doc ON audit_log(document_id)")
    conn.commit()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def log_event(conn, document_id, action, previous_status, new_status, reason="", commit=True):
    conn.execute(
        "INSERT INTO audit_log (document_id, action, previous_status, new_status, timestamp, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (document_id, action, previous_status, new_status, now_iso(), reason or ""),
    )
    if commit:
        conn.commit()


def get_history(conn, document_id):
    cur = conn.execute(
        "SELECT action, previous_status, new_status, timestamp, reason "
        "FROM audit_log WHERE document_id = ? ORDER BY id ASC",
        (document_id,),
    )
    cols = ["action", "previous_status", "new_status", "timestamp", "reason"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
