"""Run with:  pytest test_week5.py -v
Uses an in-memory SQLite DB, so it never touches your real data."""
import json
import sqlite3

import pytest

import audit
import validator
import workflow
import workflow_service as ws
from workflow import (NEW, NEEDS_REVIEW, REJECTED, APPROVED, COMPLETED, InvalidTransition)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, "
              "doc_type TEXT, extracted_fields TEXT)")
    ws.migrate(c)
    return c


def add(conn, name, doc_type, fields):
    cur = conn.execute("INSERT INTO documents (filename, doc_type, extracted_fields) VALUES (?,?,?)",
                       (name, doc_type, json.dumps(fields) if fields is not None else None))
    conn.commit()
    return cur.lastrowid


GOOD_INVOICE = {"invoice_number": "INV-001", "date": "2026-03-01",
                "company_name": "Acme Ltd", "total_amount": "$1,250.50"}
GOOD_RESUME = {"name": "Ayesha Khan", "email": "ayesha@example.com",
               "skills": ["Python", "SQL"], "phone": "+92 300 1234567"}


def test_normal_invoice_completes(conn):
    r = ws.process_document(conn, add(conn, "inv.pdf", "invoice", GOOD_INVOICE))
    assert r["ok"] and r["state"] == COMPLETED


def test_normal_resume_completes(conn):
    r = ws.process_document(conn, add(conn, "cv.pdf", "resume", GOOD_RESUME))
    assert r["state"] == COMPLETED


def test_missing_required_fields_go_to_review(conn):
    bad = {k: v for k, v in GOOD_INVOICE.items() if k != "company_name"}
    r = ws.process_document(conn, add(conn, "inv2.pdf", "invoice", bad))
    assert r["state"] == NEEDS_REVIEW and "company_name" in r["reason"]


def test_unreadable_document_goes_to_review(conn):
    r = ws.process_document(conn, add(conn, "scan.png", "invoice", {}))
    assert r["state"] == NEEDS_REVIEW and "unreadable" in r["reason"].lower()


@pytest.mark.parametrize("field,value", [("email", "not-an-email"),
                                         ("date", "31st Feb maybe"),
                                         ("total_amount", "abc")])
def test_invalid_formats_recorded(field, value):
    fields = dict(GOOD_RESUME if field == "email" else GOOD_INVOICE)
    fields[field] = value
    v = validator.validate_document("resume" if field == "email" else "invoice", fields)
    assert not v["is_valid"] and field in v["invalid_fields"]


def test_low_confidence_goes_to_review(conn):
    doc = add(conn, "inv3.pdf", "invoice", GOOD_INVOICE)
    r = ws.process_document(conn, doc, confidence=0.35)
    assert r["state"] == NEEDS_REVIEW and "confidence" in r["reason"].lower()


def test_no_confidence_is_never_invented(conn):
    doc = add(conn, "inv4.pdf", "invoice", GOOD_INVOICE)
    ws.process_document(conn, doc)
    assert ws._row(conn, doc)["confidence"] is None


def test_invalid_transition_blocked(conn):
    doc = add(conn, "inv5.pdf", "invoice", GOOD_INVOICE)
    with pytest.raises(InvalidTransition):
        ws.change_status(conn, doc, APPROVED, "bad", "New cannot jump to Approved")
    assert ws.get_status(conn, doc) == NEW


def test_reject_requires_reason(conn):
    doc = add(conn, "inv6.pdf", "invoice", {})
    ws.process_document(conn, doc)
    with pytest.raises(ValueError):
        ws.reject(conn, doc, "  ")
    ws.reject(conn, doc, "Illegible scan")
    assert ws.get_status(conn, doc) == REJECTED


def test_review_actions_write_audit(conn):
    doc = add(conn, "inv7.pdf", "invoice", {})
    ws.process_document(conn, doc)
    ws.approve(conn, doc, "Checked manually")
    ws.complete(conn, doc)
    actions = [h["action"] for h in audit.get_history(conn, doc)]
    assert actions[-2:] == ["reviewer_approved", "workflow_completed"]


def test_batch_mixed_success_does_not_stop(conn):
    ok = add(conn, "a.pdf", "invoice", GOOD_INVOICE)
    review = add(conn, "b.pdf", "invoice", {})
    results, counts = ws.process_batch(conn, [ok, 99999, review])  # 99999 doesn't exist
    assert counts == {"processed": 1, "review": 1, "failed": 1}
    assert len(results) == 3


def test_database_failure_is_reported_not_raised():
    c = sqlite3.connect(":memory:")  # no tables at all -> every query fails
    results, counts = ws.process_batch(c, [1, 2])
    assert counts["failed"] == 2


def test_search_and_metrics(conn):
    ws.process_document(conn, add(conn, "acme.pdf", "invoice", GOOD_INVOICE))
    ws.process_document(conn, add(conn, "empty.png", "resume", {}))
    assert len(ws.search_documents(conn, query="INV-001")) == 1
    assert len(ws.search_documents(conn, status=NEEDS_REVIEW)) == 1
    m = ws.metrics(conn)
    assert m["total"] == 2 and m["completed"] == 1 and m["needs_review"] == 1
