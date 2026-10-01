"""
ingest.py
Week 4 - the whole upload pipeline in one place:

  Validate -> Hash -> Duplicate check -> Read/OCR -> Clean -> Classify ->
  Extract -> Store file -> Store metadata

It ties storage.py, processing.py and database.py together. It never raises
for a problem with the user's file: it returns an IngestOutcome whose message
is safe to show (Task 8).
"""

import logging
from dataclasses import dataclass, field

import config
import database as db
import storage
from extraction import NOT_FOUND
from processing import ProcessingResult, columns_from_fields, determine_status, process_document

logger = logging.getLogger(__name__)


@dataclass
class IngestOutcome:
    kind: str                      # "new" | "duplicate" | "rejected" | "error"
    message: str
    document: dict | None = None
    trace: list = field(default_factory=list)   # [(label, "ok" | "fail" | "skip" | "stop")]


def ingest_upload(filename: str, data: bytes, *, db_path=config.DB_PATH,
                  storage_root=config.STORAGE_DIR, process=process_document) -> IngestOutcome:
    trace: list = []

    # 1. Validate
    try:
        ext = storage.validate_upload(filename, data)
    except storage.ValidationError as exc:
        return IngestOutcome("rejected", str(exc), trace=[("Validate", "fail")])
    trace.append(("Validate", "ok"))

    # 2. Hash + duplicate check
    file_hash = storage.compute_sha256(data)
    trace.append(("Hash", "ok"))
    try:
        existing = db.get_by_hash(file_hash, db_path)
    except db.DatabaseError as exc:
        return IngestOutcome("error", str(exc), trace=trace + [("Duplicate check", "fail")])
    if existing:
        trace.append(("Duplicate check", "stop"))
        return IngestOutcome(
            "duplicate",
            f"This file is already in the library as '{existing['original_filename']}'.",
            existing, trace)
    trace.append(("Duplicate check", "ok"))

    # 3. Read, clean, classify, extract
    try:
        result = process(data, ext)
    except Exception:
        logger.exception("Processing crashed")
        result = ProcessingResult(
            status=config.STATUS_FAILED,
            status_reason="This file could not be processed.",
            steps=[("Read / OCR", "fail"), ("Clean", "skip"), ("Classify", "skip"), ("Extract", "skip")])
    trace.extend(result.steps)

    # 4. Store the file, then the metadata
    try:
        stored_filename, file_path = storage.save_file(
            data, filename, ext, result.document_type, storage_root)
    except storage.StorageError as exc:
        return IngestOutcome("error", str(exc), trace=trace + [("Store file", "fail")])
    trace.append(("Store file", "ok"))

    record = {
        "original_filename": filename,
        "stored_filename": stored_filename,
        "document_type": result.document_type,
        "file_path": file_path,
        "text_preview": result.text[:config.TEXT_PREVIEW_CHARS],
        "file_hash": file_hash,
        "status": result.status,
        "status_reason": result.status_reason,
        "fields": result.fields,
        "confidence": result.confidence,
        "used_ocr": result.used_ocr,
        "file_size": len(data),
        **columns_from_fields(result.fields),
    }
    try:
        doc_id = db.create_document(record, db_path)
        document = db.get_document(doc_id, db_path)
    except db.DuplicateDocumentError:
        # Two uploads of the same file raced each other; keep the first.
        storage.delete_file(file_path, storage_root)
        existing = db.get_by_hash(file_hash, db_path)
        return IngestOutcome("duplicate", "This file is already in the library.",
                             existing, trace[:3] + [("Duplicate check", "stop")])
    except db.DatabaseError as exc:
        storage.delete_file(file_path, storage_root)  # do not leave orphan files
        return IngestOutcome("error", str(exc), trace=trace + [("Store metadata", "fail")])
    trace.append(("Store metadata", "ok"))

    message = {
        config.STATUS_PROCESSED: "Saved and processed.",
        config.STATUS_REVIEW: "Saved, but it needs a quick review.",
        config.STATUS_FAILED: "Saved, but it could not be processed.",
    }[result.status]
    return IngestOutcome("new", message, document, trace)


def update_fields(doc_id: int, new_fields: dict, *, db_path=config.DB_PATH) -> tuple[bool, str]:
    """Save a person's corrections to the extracted fields, then re-check the
    status. Returns (ok, message)."""
    try:
        doc = db.get_document(doc_id, db_path)
        if doc is None:
            return False, "That document no longer exists."
        fields = {k: (v.strip() if v and v.strip() else NOT_FOUND) for k, v in new_fields.items()}
        status, reason = determine_status(doc["document_type"], fields)
        db.update_document(
            doc_id, db_path,
            extracted_fields=fields, status=status, status_reason=reason,
            **columns_from_fields(fields))
        return True, f"Changes saved. Status: {status}."
    except db.DatabaseError as exc:
        return False, str(exc)


def delete_document(doc_id: int, *, db_path=config.DB_PATH,
                    storage_root=config.STORAGE_DIR) -> tuple[bool, str]:
    """Remove the record and its stored file."""
    try:
        file_path = db.delete_document(doc_id, db_path)
    except db.DatabaseError as exc:
        return False, str(exc)
    if file_path is None:
        return False, "That document no longer exists."
    storage.delete_file(file_path, storage_root)
    return True, "Document deleted."
