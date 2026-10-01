"""
app.py
Week 4 - AI Document Intelligence & Workflow Platform
Zyroo Internship Program - AI/ML Internship - Week 4

Streamlit is UI only. Everything else lives in:
    storage.py     file validation, safe filenames, folders
    database.py    SQLite repository, search, filters
    processing.py  read/OCR, clean, classify, extract
    ingest.py      wires the three together into one upload flow

Flow: Upload -> Validate -> Hash -> Read/OCR -> Clean -> Classify ->
      Extract -> Store File -> Store Metadata -> Search/Filter -> View
"""

from datetime import datetime

import streamlit as st

import config
import database as db
import ingest
import processing
from extraction import NOT_FOUND

st.set_page_config(page_title="Document Intelligence", page_icon="🗂️", layout="wide")

STATUS_COLORS = {
    config.STATUS_PROCESSED: "#1E8E5A",
    config.STATUS_REVIEW: "#B8860B",
    config.STATUS_FAILED: "#C0392B",
}
TYPE_ICONS = {"Invoice": "🧾", "Resume": "📄", "Other": "🗒️"}


# --------------------------------------------------------------------- CSS
def inject_style() -> None:
    st.markdown(
        """
        <style>
        html, body, [class*="css"] { font-family: "Source Sans Pro", "Segoe UI", sans-serif; }
        .block-container { padding-top: 1.6rem; max-width: 1200px; }

        .zw-card {
            border: 1px solid #E4E1D8; border-radius: 10px; padding: 1rem 1.2rem;
            margin-bottom: 0.7rem; background: #FCFBF8;
        }
        .zw-card:hover { border-color: #C9C4B4; }
        .zw-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
        .zw-title { font-weight: 600; font-size: 1.02rem; color: #2B2A26; }
        .zw-meta { color: #6E6A5C; font-size: 0.85rem; margin-top: 0.15rem; }
        .zw-badge {
            display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px;
            font-size: 0.78rem; font-weight: 600; color: white; white-space: nowrap;
        }
        .zw-tile {
            border: 1px solid #E4E1D8; border-radius: 10px; padding: 0.9rem 1rem;
            background: #FCFBF8; text-align: center;
        }
        .zw-tile-num { font-size: 1.6rem; font-weight: 700; color: #2B2A26; }
        .zw-tile-lbl { font-size: 0.8rem; color: #6E6A5C; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#6E6A5C")
    return f'<span class="zw-badge" style="background:{color}">{status}</span>'


def init_state() -> None:
    st.session_state.setdefault("search_query", "")
    st.session_state.setdefault("filter_type", "All")
    st.session_state.setdefault("filter_status", "All")
    st.session_state.setdefault("sort_order", "Newest first")
    st.session_state.setdefault("open_doc_id", None)
    st.session_state.setdefault("page", 0)


def clear_filters() -> None:
    st.session_state.search_query = ""
    st.session_state.filter_type = "All"
    st.session_state.filter_status = "All"
    st.session_state.sort_order = "Newest first"
    st.session_state.page = 0


# ---------------------------------------------------------------- sections
def render_upload() -> None:
    st.subheader("Upload documents")
    env = processing.environment_status()
    cols = st.columns(2)
    with cols[0]:
        if env["model_name"]:
            st.caption(f"Classifier: **{env['model_name']}** (trained)")
        else:
            st.caption("Classifier: rule-based only — run `python train_classifier.py` to train a model.")
    with cols[1]:
        if not env["ocr"]:
            st.caption("⚠️ OCR is not available — scanned files will need selectable text instead.")

    files = st.file_uploader(
        "Drop invoices, resumes, or other documents",
        type=list(config.ALLOWED_EXTENSIONS),
        accept_multiple_files=True,
        help=f"PDF, JPG, or PNG. Up to {config.MAX_UPLOAD_MB} MB each.",
    )
    if not files:
        return

    if st.button(f"Process {len(files)} file(s)", type="primary"):
        results = []
        progress = st.progress(0.0)
        for i, f in enumerate(files):
            outcome = ingest.ingest_upload(f.name, f.read())
            results.append((f.name, outcome))
            progress.progress((i + 1) / len(files))
        progress.empty()

        for name, outcome in results:
            if outcome.kind == "new":
                doc = outcome.document
                icon = "✅" if doc["status"] == config.STATUS_PROCESSED else "⚠️"
                st.markdown(f"{icon} **{name}** — {outcome.message} ({doc['document_type']}, {doc['status']})")
            elif outcome.kind == "duplicate":
                st.info(f"↩️ **{name}** — {outcome.message}")
            elif outcome.kind == "rejected":
                st.error(f"🚫 **{name}** — {outcome.message}")
            else:
                st.error(f"❌ **{name}** — {outcome.message}")
            with st.expander(f"Steps for {name}", expanded=False):
                st.write(" → ".join(f"{label} ({state})" for label, state in outcome.trace))
        st.session_state.page = 0


def render_dashboard() -> None:
    stats = db.get_stats()
    cols = st.columns(4)
    tiles = [
        ("Total documents", stats["total"]),
        ("Processed", stats["by_status"].get(config.STATUS_PROCESSED, 0)),
        ("Needs review", stats["by_status"].get(config.STATUS_REVIEW, 0)),
        ("Failed", stats["by_status"].get(config.STATUS_FAILED, 0)),
    ]
    for col, (label, value) in zip(cols, tiles):
        col.markdown(
            f'<div class="zw-tile"><div class="zw-tile-num">{value}</div>'
            f'<div class="zw-tile-lbl">{label}</div></div>',
            unsafe_allow_html=True,
        )


def render_search_bar() -> None:
    st.text_input(
        "Search",
        key="search_query",
        placeholder="Search by filename, company, invoice number, type, or text...",
        label_visibility="collapsed",
    )
    c1, c2, c3, c4 = st.columns([1, 1, 1, 0.6])
    with c1:
        st.selectbox("Document type", ["All", "Invoice", "Resume", "Other"], key="filter_type")
    with c2:
        st.selectbox("Status", ["All"] + list(config.STATUSES), key="filter_status")
    with c3:
        st.selectbox("Sort by", ["Newest first", "Oldest first"], key="sort_order")
    with c4:
        st.write("")
        st.button("Clear filters", on_click=clear_filters, use_container_width=True)


def _current_filters() -> dict:
    return {
        "query": st.session_state.search_query.strip(),
        "document_type": None if st.session_state.filter_type == "All" else st.session_state.filter_type,
        "status": None if st.session_state.filter_status == "All" else st.session_state.filter_status,
        "sort": "oldest" if st.session_state.sort_order == "Oldest first" else "newest",
    }


def render_library() -> None:
    filters = _current_filters()
    total = db.count_documents(**{k: v for k, v in filters.items() if k != "sort"})
    if total == 0:
        st.info("No documents match these filters yet." if any(filters.values())
                else "No documents uploaded yet — add some above to get started.")
        return

    page = st.session_state.page
    offset = page * config.PAGE_SIZE
    docs = db.search_documents(**filters, limit=config.PAGE_SIZE, offset=offset)

    st.caption(f"{total} document(s) found")
    for doc in docs:
        icon = TYPE_ICONS.get(doc["document_type"], "🗒️")
        subtitle = doc.get("company") or doc.get("invoice_number") or doc["document_type"]
        st.markdown(
            f'<div class="zw-card"><div class="zw-row">'
            f'<div><div class="zw-title">{icon} {doc["original_filename"]}</div>'
            f'<div class="zw-meta">{subtitle} • uploaded {doc["upload_date"]}</div></div>'
            f'{badge(doc["status"])}</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("View details", key=f"open_{doc['id']}"):
            st.session_state.open_doc_id = doc["id"]
            st.rerun()

    last_page = max(0, (total - 1) // config.PAGE_SIZE)
    if last_page > 0:
        nav = st.columns([1, 2, 1])
        with nav[0]:
            if st.button("← Previous", disabled=page <= 0):
                st.session_state.page -= 1
                st.rerun()
        with nav[1]:
            st.markdown(f"<div style='text-align:center'>Page {page + 1} of {last_page + 1}</div>",
                       unsafe_allow_html=True)
        with nav[2]:
            if st.button("Next →", disabled=page >= last_page):
                st.session_state.page += 1
                st.rerun()


def render_detail(doc_id: int) -> None:
    doc = db.get_document(doc_id)
    if doc is None:
        st.warning("This document no longer exists.")
        st.session_state.open_doc_id = None
        return

    if st.button("← Back to library"):
        st.session_state.open_doc_id = None
        st.rerun()

    icon = TYPE_ICONS.get(doc["document_type"], "🗒️")
    st.markdown(f"### {icon} {doc['original_filename']}")
    st.markdown(badge(doc["status"]), unsafe_allow_html=True)
    if doc.get("status_reason"):
        st.caption(doc["status_reason"])

    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Metadata**")
        st.write(f"Type: {doc['document_type']}")
        st.write(f"Uploaded: {doc['upload_date']}")
        st.write(f"Read via OCR: {'Yes' if doc['used_ocr'] else 'No'}")
        if doc.get("confidence") is not None:
            st.write(f"Classifier confidence: {doc['confidence']}%")
        st.write(f"File size: {(doc.get('file_size') or 0) / 1024:.1f} KB")
        st.write(f"Stored at: `{doc['file_path']}`")
        st.write(f"SHA-256: `{doc['file_hash'][:16]}…`")

    with right:
        st.markdown("**Extracted fields**")
        fields = doc.get("fields") or {}
        if not fields:
            st.write("This document type has no extracted fields.")
        else:
            with st.form(key=f"fields_{doc_id}"):
                edited = {}
                for name, value in fields.items():
                    edited[name] = st.text_input(
                        name, value="" if value == NOT_FOUND else value, key=f"f_{doc_id}_{name}"
                    )
                if st.form_submit_button("Save corrections"):
                    ok, message = ingest.update_fields(doc_id, edited)
                    (st.success if ok else st.error)(message)
                    if ok:
                        st.rerun()

    st.markdown("**Text preview**")
    with st.expander("Show stored text preview", expanded=False):
        st.text(doc.get("text_preview") or "(no text stored)")

    file_bytes = storage_read(doc["file_path"])
    if file_bytes is not None:
        ext = doc["stored_filename"].rsplit(".", 1)[-1].lower()
        st.download_button(
            "Open / download file", data=file_bytes, file_name=doc["original_filename"],
            mime=config.MIME_TYPES.get(ext, "application/octet-stream"),
        )
    else:
        st.warning("The stored file could not be found on disk.")

    st.divider()
    danger = st.expander("Danger zone")
    with danger:
        if st.button("Delete this document", type="secondary"):
            ok, message = ingest.delete_document(doc_id)
            (st.success if ok else st.error)(message)
            if ok:
                st.session_state.open_doc_id = None
                st.rerun()


def storage_read(relative_path: str):
    import storage
    return storage.read_file(relative_path)


# --------------------------------------------------------------------- main
def main() -> None:
    inject_style()
    init_state()
    db.init_db()

    st.title("🗂️ AI Document Intelligence & Workflow Platform")
    st.caption("Zyroo Internship Program • AI/ML Internship • Week 4")

    render_dashboard()
    st.divider()
    render_upload()
    st.divider()

    st.subheader("Document library")
    render_search_bar()

    if st.session_state.open_doc_id is not None:
        render_detail(st.session_state.open_doc_id)
    else:
        render_library()


if __name__ == "__main__":
    main()
