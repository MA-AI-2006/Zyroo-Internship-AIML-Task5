"""workflow_pages.py - Week 5 Streamlit pages (UI only; no workflow rules here).

In app.py:
    import workflow_pages as wp, workflow_service as ws
    ws.migrate(conn)
    page = st.sidebar.radio("Page", [..., "Review Queue", "Batch Processing",
                                     "Workflow Search", "Metrics"])
    if page == "Review Queue":      wp.review_queue_page(conn)
    elif page == "Batch Processing": wp.batch_page(conn)
    elif page == "Workflow Search":  wp.search_page(conn)
    elif page == "Metrics":          wp.metrics_page(conn)
"""
import json

import pandas as pd
import streamlit as st

import audit
import workflow_service as ws
from workflow import (ALL_STATES, NEEDS_REVIEW, APPROVED, REJECTED, COMPLETED,
                      NEW, InvalidTransition)

COLORS = {NEW: "#64748b", "Processing": "#0ea5e9", NEEDS_REVIEW: "#f59e0b",
          APPROVED: "#10b981", REJECTED: "#ef4444", COMPLETED: "#6366f1"}


def _css():
    st.markdown("""
    <style>
    .badge{display:inline-block;padding:2px 12px;border-radius:999px;color:#fff;
           font-size:.8rem;font-weight:600}
    .card{border:1px solid #e2e8f0;border-radius:14px;padding:14px 18px;margin-bottom:10px;
          background:linear-gradient(135deg,#f8fafc,#eef2ff)}
    .reason{color:#92400e;background:#fef3c7;border-radius:8px;padding:6px 10px;font-size:.9rem}
    </style>""", unsafe_allow_html=True)


def badge(status):
    return f"<span class='badge' style='background:{COLORS.get(status, '#64748b')}'>{status}</span>"


def _doc_label(d):
    return f"#{d['id']} - {d['filename']} ({d['doc_type'] or 'unknown'}) [{d['workflow_status']}]"


# ---------------------------------------------------------------- review ---
def review_queue_page(conn):
    _css()
    st.title("Human Review Queue")
    queue = ws.search_documents(conn, status=NEEDS_REVIEW)
    approved = ws.search_documents(conn, status=APPROVED)

    if not queue:
        st.success("Nothing waiting for review.")
    for d in queue:
        row = ws._row(conn, d["id"])
        with st.container():
            st.markdown(
                f"<div class='card'><b>{d['filename']}</b> &nbsp; {badge(d['workflow_status'])}"
                f"<br>Type: <b>{d['doc_type'] or 'unknown'}</b>"
                f"<br><span class='reason'>Reason: {row.get('review_reason') or 'n/a'}</span></div>",
                unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                st.caption("Extracted fields")
                st.json(ws._load_fields(row))
            with c2:
                st.caption("Validation results")
                v = json.loads(row["validation_json"]) if row.get("validation_json") else {}
                st.json(v)
            reason = st.text_input("Reason (required to reject)", key=f"reason_{d['id']}")
            b1, b2, _ = st.columns([1, 1, 4])
            if b1.button("Approve", key=f"ap_{d['id']}", type="primary"):
                _safe(lambda: ws.approve(conn, d["id"], reason))
            if b2.button("Reject", key=f"rj_{d['id']}"):
                if not reason.strip():
                    st.error("Please enter a short reason before rejecting.")
                else:
                    _safe(lambda: ws.reject(conn, d["id"], reason))
            with st.expander("Audit history"):
                st.dataframe(pd.DataFrame(audit.get_history(conn, d["id"])), use_container_width=True)

    if approved:
        st.subheader("Approved - ready to complete")
        for d in approved:
            if st.button(f"Complete #{d['id']} {d['filename']}", key=f"co_{d['id']}"):
                _safe(lambda: ws.complete(conn, d["id"]))


def _safe(fn):
    try:
        fn()
        st.rerun()
    except InvalidTransition as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Action failed: {e}")


# ----------------------------------------------------------------- batch ---
def batch_page(conn):
    _css()
    st.title("Batch Workflow Processing")
    docs = ws.search_documents(conn, status=NEW)
    if not docs:
        st.info("No New documents to process.")
        return
    labels = {_doc_label(d): d["id"] for d in docs}
    chosen = st.multiselect("Select documents", list(labels))
    if st.button("Run workflow", type="primary", disabled=not chosen):
        results, counts = ws.process_batch(conn, [labels[c] for c in chosen])
        c1, c2, c3 = st.columns(3)
        c1.metric("Processed (completed)", counts["processed"])
        c2.metric("Sent to review", counts["review"])
        c3.metric("Failed", counts["failed"])
        st.dataframe(pd.DataFrame(results), use_container_width=True)


# ---------------------------------------------------------------- search ---
def search_page(conn):
    _css()
    st.title("Workflow Search & Filters")
    c1, c2 = st.columns([1, 2])
    status = c1.selectbox("Status", ["All"] + ALL_STATES)
    query = c2.text_input("Search filename, type, company or invoice number")
    rows = ws.search_documents(conn, status=status, query=query)
    st.caption(f"{len(rows)} document(s)")
    if rows:
        df = pd.DataFrame(rows)[["id", "filename", "doc_type", "workflow_status",
                                 "latest_action", "latest_timestamp"]]
        st.dataframe(df, use_container_width=True)
        pick = st.selectbox("View history for", [_doc_label(r) for r in rows])
        doc_id = int(pick.split()[0].lstrip("#"))
        st.dataframe(pd.DataFrame(audit.get_history(conn, doc_id)), use_container_width=True)


# --------------------------------------------------------------- metrics ---
def metrics_page(conn):
    _css()
    st.title("Workflow Metrics")
    m = ws.metrics(conn)
    cols = st.columns(4)
    cols[0].metric("Total", m["total"])
    cols[1].metric("Processed", m["processed"])
    cols[2].metric("Needs review", m["needs_review"])
    cols[3].metric("Failed", m["failed"])
    cols = st.columns(3)
    cols[0].metric("Approved", m["approved"])
    cols[1].metric("Rejected", m["rejected"])
    cols[2].metric("Completed", m["completed"])
    left, right = st.columns(2)
    left.subheader("By document type")
    if m["by_type"]:
        left.bar_chart(pd.Series(m["by_type"]))
    right.subheader("By status")
    if m["by_status"]:
        right.bar_chart(pd.Series(m["by_status"]))
    if m["avg_processing_ms"] is not None:
        st.caption(f"Average measured rule-processing time: {m['avg_processing_ms']:.1f} ms "
                   "(workflow rules only, excludes OCR/upload time)")
