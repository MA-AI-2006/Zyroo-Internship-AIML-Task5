"""
test_repository.py
Week 4 - Task 9: automated tests for the complete repository.

Uses samples/ (run generate_samples.py first if that folder is empty) plus
a throw-away database and storage folder, so this never touches the real
data/ or storage/ used by the running app.

    python test_repository.py
"""

import functools
import shutil
import sys
import tempfile
from pathlib import Path

import database as db
import ingest
import processing
import storage

SAMPLES = Path(__file__).resolve().parent / "samples"
passed = failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ok   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}  {detail}")


def main() -> int:
    if not SAMPLES.exists() or not any(SAMPLES.iterdir()):
        print("No sample files found — run `python generate_samples.py` first.")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="doc_repo_test_"))
    db_path = tmp / "documents.db"
    storage_root = tmp / "storage"
    # Rule-based classification only, so results don't depend on whether a
    # model has been trained on this machine.
    process = functools.partial(processing.process_document, use_ml=False)

    print(f"Test workspace: {tmp}\n")

    # --- Task 9: at least 10 documents, several kinds ------------------
    print("Uploading sample documents...")
    files = sorted(p for p in SAMPLES.iterdir() if p.is_file())
    check("at least 10 sample files exist", len(files) >= 10, f"found {len(files)}")

    outcomes = {}
    for f in files:
        outcomes[f.name] = ingest.ingest_upload(
            f.name, f.read_bytes(), db_path=db_path, storage_root=storage_root, process=process
        )

    # --- individual expectations ---------------------------------------
    check("a normal invoice is Processed",
         outcomes["invoice_northwind.pdf"].kind == "new"
         and outcomes["invoice_northwind.pdf"].document["status"] == "Processed")
    check("a normal resume is Processed",
         outcomes["resume_ayesha.pdf"].kind == "new"
         and outcomes["resume_ayesha.pdf"].document["status"] == "Processed")
    check("a duplicate file is detected",
         outcomes["invoice_northwind_copy.pdf"].kind == "duplicate")
    check("a scanned document is read",
         outcomes["scanned_invoice.png"].kind == "new"
         and outcomes["scanned_invoice.png"].document["document_type"] == "Invoice")
    check("an invoice missing its total goes to Needs Review",
         outcomes["invoice_missing_total.pdf"].document["status"] == "Needs Review")
    check("a resume missing its email goes to Needs Review",
         outcomes["resume_missing_email.pdf"].document["status"] == "Needs Review")
    check("a damaged PDF is marked Failed",
         outcomes["damaged.pdf"].document is not None
         and outcomes["damaged.pdf"].document["status"] == "Failed")
    check("an unsupported file type is rejected",
         outcomes["notes.txt"].kind == "rejected")
    check("an 'other' document is not misfiled as invoice/resume",
         outcomes["meeting_notes.pdf"].document["document_type"] == "Other")

    # --- search across different fields (Task 4) ------------------------
    print("\nSearching...")
    by_company = db.search_documents(query="Northwind", db_path=db_path)
    check("search by company name finds the invoice", len(by_company) >= 1)

    by_invoice_no = db.search_documents(query="ACM-88431", db_path=db_path)
    check("search by invoice number works", len(by_invoice_no) == 1)

    by_type_word = db.search_documents(query="resume", db_path=db_path)
    check("search matches stored text preview",
         any(d["original_filename"].startswith("resume") for d in by_type_word))

    # --- filters and sorting (Task 5) ------------------------------------
    print("\nFiltering and sorting...")
    invoices_only = db.search_documents(document_type="Invoice", db_path=db_path)
    check("type filter returns only invoices",
         all(d["document_type"] == "Invoice" for d in invoices_only) and len(invoices_only) >= 4)

    needs_review = db.search_documents(status="Needs Review", db_path=db_path)
    check("status filter returns only Needs Review",
         all(d["status"] == "Needs Review" for d in needs_review) and len(needs_review) == 2)

    newest = db.search_documents(sort="newest", db_path=db_path)
    oldest = db.search_documents(sort="oldest", db_path=db_path)
    check("newest/oldest sort reverse each other",
         newest[0]["id"] == oldest[-1]["id"] and newest[-1]["id"] == oldest[0]["id"])

    # --- detail view has what it needs (Task 6) ---------------------------
    doc = outcomes["invoice_acme.pdf"].document
    full = db.get_document(doc["id"], db_path=db_path)
    check("detail view has metadata, fields, and a file path",
         full is not None and full["fields"].get("Invoice Number") == "ACM-88431"
         and full["file_path"])
    check("the stored file can actually be opened",
         storage.read_file(full["file_path"], storage_root) is not None)

    # --- error handling (Task 8) -------------------------------------------
    print("\nError handling...")
    empty_outcome = ingest.ingest_upload("empty.pdf", b"", db_path=db_path, storage_root=storage_root)
    check("an empty file is rejected, not crashed on", empty_outcome.kind == "rejected")

    fake_pdf = ingest.ingest_upload("fake.pdf", b"not a pdf at all", db_path=db_path, storage_root=storage_root)
    check("a file with a fake extension is rejected", fake_pdf.kind == "rejected")

    big = ingest.ingest_upload("big.pdf", b"%PDF-1.4" + b"0" * (storage_root and 11 * 1024 * 1024),
                               db_path=db_path, storage_root=storage_root)
    check("an oversized file is rejected", big.kind == "rejected")

    # --- restart persistence (Task 9) --------------------------------------
    print("\nSimulating an app restart...")
    processing.load_ml_model.cache_clear()
    remaining = db.count_documents(db_path=db_path)
    stored_count = sum(1 for o in outcomes.values() if o.kind == "new")
    check("records are still present after reopening the database", remaining == stored_count,
         f"expected {stored_count}, got {remaining}")

    print(f"\n{passed} passed, {failed} failed")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
