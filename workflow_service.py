"""workflow_service.py - connects the rule engine to SQLite.

ADAPT THE THREE COLUMN NAMES BELOW to match your Week 4 `documents` table.
Everything else is self-contained.
"""
import json
import time

import audit
import validator
import workflow
from workflow import (NEW, PROCESSING, NEEDS_REVIEW, APPROVED, REJECTED, COMPLETED,
                      InvalidTransition)

TABLE = "documents"
COL_ID = "id"
COL_NAME = "filename"
COL_TYPE = "doc_type"            # predicted/stored document type
COL_FIELDS = "extracted_fields"  # JSON text of extracted fields

NEW_COLUMNS = {
    "workflow_status": "TEXT DEFAULT 'New'",
    "review_reason": "TEXT",
    "validation_json": "TEXT",
    "predicted_type": "TEXT",
    "confidence": "REAL",           # stays NULL when the classifier gives none
    "failed": "INTEGER DEFAULT 0",
    "last_error": "TEXT",
    "processing_ms": "REAL",
}


def migrate(conn):
    """Add Week 5 columns + audit table. Safe to run on every app start."""
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})")}
    for col, ddl in NEW_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {col} {ddl}")
    conn.execute(f"UPDATE {TABLE} SET workflow_status = 'New' WHERE workflow_status IS NULL")
    conn.commit()
    audit.init_audit_table(conn)


def _row(conn, doc_id):
    cur = conn.execute(f"SELECT * FROM {TABLE} WHERE {COL_ID} = ?", (doc_id,))
    r = cur.fetchone()
    if r is None:
        raise LookupError(f"Document {doc_id} not found")
    return dict(zip([d[0] for d in cur.description], r))


def get_status(conn, doc_id):
    return _row(conn, doc_id)["workflow_status"] or NEW


def change_status(conn, doc_id, new_state, action, reason="", extra=None):
    """Validate the transition, update the row and write the audit entry atomically."""
    current = get_status(conn, doc_id)
    workflow.assert_transition(current, new_state)   # raises InvalidTransition
    sets = {"workflow_status": new_state}
    sets.update(extra or {})
    assignments = ", ".join(f"{k} = ?" for k in sets)
    try:
        conn.execute(f"UPDATE {TABLE} SET {assignments} WHERE {COL_ID} = ?",
                     [*sets.values(), doc_id])
        audit.log_event(conn, doc_id, action, current, new_state, reason, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _load_fields(row):
    raw = row.get(COL_FIELDS)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def process_document(conn, doc_id, confidence=None):
    """Run one document through the workflow. Returns a result dict.

    `confidence` should come from your classifier ONLY if it truly provides one
    (e.g. predict_proba). Pass None otherwise - it is never estimated.
    """
    start = time.perf_counter()
    try:
        row = _row(conn, doc_id)
        if confidence is None:
            confidence = row.get("confidence")  # keep a stored value if there is one
        change_status(conn, doc_id, PROCESSING, "processing_started", "Workflow started")

        doc_type = (row.get(COL_TYPE) or "").lower()
        fields = _load_fields(row)
        validation = validator.validate_document(doc_type, fields)
        decision = workflow.decide(doc_type, fields, validation, confidence)

        ms = round((time.perf_counter() - start) * 1000, 2)
        change_status(conn, doc_id, decision.next_state, decision.action, decision.reason, {
            "review_reason": decision.reason if decision.next_state == NEEDS_REVIEW else None,
            "validation_json": json.dumps(validation),
            "predicted_type": doc_type or None,
            "confidence": confidence,
            "failed": 0, "last_error": None, "processing_ms": ms,
        })
        return {"id": doc_id, "ok": True, "state": decision.next_state, "reason": decision.reason}
    except Exception as exc:  # one failure must never stop a batch
        return _record_failure(conn, doc_id, exc)


def _record_failure(conn, doc_id, exc):
    try:
        conn.rollback()
        if get_status(conn, doc_id) == PROCESSING:
            change_status(conn, doc_id, NEW, "processing_failed", str(exc),
                          {"failed": 1, "last_error": str(exc)})
        elif isinstance(exc, InvalidTransition):
            # Blocked by the state machine: log it, but don't mark the document as failed.
            current = get_status(conn, doc_id)
            audit.log_event(conn, doc_id, "transition_blocked", current, current, str(exc))
        else:
            conn.execute(f"UPDATE {TABLE} SET failed = 1, last_error = ? WHERE {COL_ID} = ?",
                         (str(exc), doc_id))
            audit.log_event(conn, doc_id, "processing_failed", None, None, str(exc))
    except Exception:
        pass  # database itself is down; still report the failure to the caller
    return {"id": doc_id, "ok": False, "state": None, "reason": str(exc)}


def process_batch(conn, doc_ids):
    """Run the same rules for every selected document; return results + counts."""
    results = [process_document(conn, d) for d in doc_ids]
    counts = {
        "processed": sum(1 for r in results if r["ok"] and r["state"] == COMPLETED),
        "review": sum(1 for r in results if r["ok"] and r["state"] == NEEDS_REVIEW),
        "failed": sum(1 for r in results if not r["ok"]),
    }
    return results, counts


def approve(conn, doc_id, note=""):
    change_status(conn, doc_id, APPROVED, "reviewer_approved", note or "Approved by reviewer")


def reject(conn, doc_id, reason):
    if not (reason or "").strip():
        raise ValueError("A reason is required when rejecting a document")
    change_status(conn, doc_id, REJECTED, "reviewer_rejected", reason.strip())


def complete(conn, doc_id):
    change_status(conn, doc_id, COMPLETED, "workflow_completed", "Approved document completed")


def reprocess_rejected(conn, doc_id):
    change_status(conn, doc_id, NEW, "resubmitted", "Rejected document resubmitted")


def search_documents(conn, status=None, query=""):
    """Filter by status and search filename / type / company / invoice number."""
    sql = f"""
        SELECT d.{COL_ID} AS id, d.{COL_NAME} AS filename, d.{COL_TYPE} AS doc_type,
               d.workflow_status, d.review_reason, d.confidence, d.failed,
               (SELECT action FROM audit_log a WHERE a.document_id = d.{COL_ID}
                ORDER BY a.id DESC LIMIT 1) AS latest_action,
               (SELECT timestamp FROM audit_log a WHERE a.document_id = d.{COL_ID}
                ORDER BY a.id DESC LIMIT 1) AS latest_timestamp
        FROM {TABLE} d WHERE 1=1"""
    params = []
    if status and status != "All":
        sql += " AND d.workflow_status = ?"
        params.append(status)
    if query:
        like = f"%{query}%"
        # company and invoice number live inside the extracted-fields JSON text
        sql += (f" AND (d.{COL_NAME} LIKE ? OR d.{COL_TYPE} LIKE ? OR d.{COL_FIELDS} LIKE ?)")
        params += [like, like, like]
    sql += " ORDER BY d.id DESC"
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def metrics(conn):
    def one(sql, p=()):
        return conn.execute(sql, p).fetchone()[0]
    by_status = dict(conn.execute(
        f"SELECT workflow_status, COUNT(*) FROM {TABLE} GROUP BY workflow_status").fetchall())
    by_type = dict(conn.execute(
        f"SELECT COALESCE({COL_TYPE}, 'unknown'), COUNT(*) FROM {TABLE} GROUP BY 1").fetchall())
    return {
        "total": one(f"SELECT COUNT(*) FROM {TABLE}"),
        "processed": one(f"SELECT COUNT(*) FROM {TABLE} WHERE workflow_status NOT IN ('New','Processing')"),
        "needs_review": by_status.get(NEEDS_REVIEW, 0),
        "approved": by_status.get(APPROVED, 0),
        "rejected": by_status.get(REJECTED, 0),
        "completed": by_status.get(COMPLETED, 0),
        "failed": one(f"SELECT COUNT(*) FROM {TABLE} WHERE failed = 1"),
        "by_type": by_type,
        "by_status": by_status,
        "avg_processing_ms": conn.execute(
            f"SELECT AVG(processing_ms) FROM {TABLE} WHERE processing_ms IS NOT NULL").fetchone()[0],
    }
