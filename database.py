"""
database.py
Week 4 - Task 2 (SQLite repository), Task 4 (search), Task 5 (filters/sort).

Pure database code: no Streamlit imports. Every public function takes an
optional db_path so tests can use a throw-away database.

Any sqlite3 error is logged in full and re-raised as DatabaseError with a
short message that is safe to show to normal users (Task 8).
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import config

logger = logging.getLogger(__name__)

USER_MESSAGE = (
    "The document database is not available right now. "
    "Please try again in a moment."
)


class DatabaseError(Exception):
    """Something went wrong in the database. The message is safe to show."""


class DuplicateDocumentError(DatabaseError):
    """A document with the same SHA-256 hash is already stored."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT    NOT NULL,
    stored_filename   TEXT    NOT NULL,
    document_type     TEXT    NOT NULL,
    upload_date       TEXT    NOT NULL,
    company           TEXT,
    invoice_number    TEXT,
    total_amount      TEXT,
    file_path         TEXT    NOT NULL,
    text_preview      TEXT,
    file_hash         TEXT    NOT NULL UNIQUE,
    status            TEXT    NOT NULL,
    status_reason     TEXT,
    extracted_fields  TEXT,
    confidence        REAL,
    used_ocr          INTEGER NOT NULL DEFAULT 0,
    file_size         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_documents_type   ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_date   ON documents(upload_date);
"""

# Columns a caller may change with update_document().
UPDATABLE = {
    "company", "invoice_number", "total_amount", "status", "status_reason",
    "extracted_fields", "text_preview",
}

# Columns the search box looks at (Task 4).
SEARCH_COLUMNS = (
    "original_filename", "stored_filename", "company",
    "invoice_number", "document_type", "text_preview",
)

_initialised: set[str] = set()


@contextmanager
def _connect(db_path=config.DB_PATH):
    path = Path(db_path)
    needs_init = str(path) not in _initialised or not path.exists()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
    except (sqlite3.Error, OSError) as exc:
        logger.exception("Could not open database %s", path)
        raise DatabaseError(USER_MESSAGE) from exc
    try:
        if needs_init:
            conn.executescript(SCHEMA)
            _initialised.add(str(path))
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        logger.exception("Database operation failed")
        raise DatabaseError(USER_MESSAGE) from exc
    finally:
        conn.close()


def _to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    doc = dict(row)
    try:
        doc["fields"] = json.loads(doc.get("extracted_fields") or "{}")
    except (TypeError, ValueError):
        doc["fields"] = {}
    return doc


def init_db(db_path=config.DB_PATH) -> None:
    """Create the database file and table if they do not exist yet."""
    with _connect(db_path):
        pass


# ------------------------------------------------------------------ create
def create_document(record: dict, db_path=config.DB_PATH) -> int:
    """Insert one document. Returns the new id."""
    values = {
        "original_filename": record["original_filename"],
        "stored_filename": record["stored_filename"],
        "document_type": record["document_type"],
        "upload_date": record.get("upload_date")
        or datetime.now().isoformat(sep=" ", timespec="seconds"),
        "company": record.get("company"),
        "invoice_number": record.get("invoice_number"),
        "total_amount": record.get("total_amount"),
        "file_path": record["file_path"],
        "text_preview": record.get("text_preview"),
        "file_hash": record["file_hash"],
        "status": record["status"],
        "status_reason": record.get("status_reason"),
        "extracted_fields": json.dumps(record.get("fields") or {}),
        "confidence": record.get("confidence"),
        "used_ocr": 1 if record.get("used_ocr") else 0,
        "file_size": record.get("file_size"),
    }
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    with _connect(db_path) as conn:
        try:
            cur = conn.execute(
                f"INSERT INTO documents ({columns}) VALUES ({marks})",
                tuple(values.values()),
            )
        except sqlite3.IntegrityError as exc:
            if "file_hash" in str(exc):
                raise DuplicateDocumentError(
                    "This file is already in the library."
                ) from exc
            raise
        return cur.lastrowid


# -------------------------------------------------------------------- read
def get_document(doc_id: int, db_path=config.DB_PATH) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return _to_dict(row)


def get_by_hash(file_hash: str, db_path=config.DB_PATH) -> dict | None:
    """Task 3: is this exact file already stored?"""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE file_hash = ?", (file_hash,)
        ).fetchone()
    return _to_dict(row)


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _build_where(query="", document_type=None, status=None,
                 date_from=None, date_to=None) -> tuple[str, list]:
    clauses, params = [], []

    # Every word must appear somewhere; a word may match any search column.
    for word in (query or "").split():
        pattern = _like(word)
        any_column = " OR ".join(f"{col} LIKE ? ESCAPE '\\'" for col in SEARCH_COLUMNS)
        clauses.append(f"({any_column})")
        params.extend([pattern] * len(SEARCH_COLUMNS))

    if document_type:
        clauses.append("document_type = ?")
        params.append(document_type)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if date_from:
        clauses.append("date(upload_date) >= ?")
        params.append(_iso(date_from))
    if date_to:
        clauses.append("date(upload_date) <= ?")
        params.append(_iso(date_to))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


def search_documents(query="", document_type=None, status=None,
                     date_from=None, date_to=None, sort="newest",
                     limit=None, offset=0, db_path=config.DB_PATH) -> list[dict]:
    """Search + filter + sort in SQL (Tasks 4 and 5)."""
    where, params = _build_where(query, document_type, status, date_from, date_to)
    direction = "ASC" if sort == "oldest" else "DESC"
    sql = (
        f"SELECT * FROM documents {where} "
        f"ORDER BY upload_date {direction}, id {direction}"
    )
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = params + [int(limit), int(offset)]
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_to_dict(r) for r in rows]


def count_documents(query="", document_type=None, status=None,
                    date_from=None, date_to=None, db_path=config.DB_PATH) -> int:
    where, params = _build_where(query, document_type, status, date_from, date_to)
    with _connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM documents {where}", params).fetchone()[0]


def get_stats(db_path=config.DB_PATH) -> dict:
    """Small summary for the dashboard tiles."""
    with _connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        by_status = dict(conn.execute(
            "SELECT status, COUNT(*) FROM documents GROUP BY status").fetchall())
        by_type = dict(conn.execute(
            "SELECT document_type, COUNT(*) FROM documents GROUP BY document_type").fetchall())
    return {"total": total, "by_status": by_status, "by_type": by_type}


# ------------------------------------------------------------------ update
def update_document(doc_id: int, db_path=config.DB_PATH, **changes) -> bool:
    """Change allowed columns on one document. Returns True if a row changed."""
    unknown = set(changes) - UPDATABLE
    if unknown:
        raise ValueError(f"Cannot update column(s): {', '.join(sorted(unknown))}")
    if not changes:
        return False
    if isinstance(changes.get("extracted_fields"), dict):
        changes["extracted_fields"] = json.dumps(changes["extracted_fields"])
    assignments = ", ".join(f"{col} = ?" for col in changes)
    with _connect(db_path) as conn:
        cur = conn.execute(
            f"UPDATE documents SET {assignments} WHERE id = ?",
            (*changes.values(), doc_id),
        )
        return cur.rowcount > 0


# ------------------------------------------------------------------ delete
def delete_document(doc_id: int, db_path=config.DB_PATH) -> str | None:
    """Delete the record. Returns its file_path so the caller can remove the
    file too, or None when no such record existed."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return row["file_path"]
