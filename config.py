"""
config.py
Week 4 - central settings for the document repository.

Everything that might change (paths, limits, statuses) lives here so the
other modules stay free of magic numbers.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Where the SQLite file and the stored documents live.
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "documents.db"
STORAGE_DIR = BASE_DIR / "storage"

# Task 1: one folder per document type.
FOLDERS = {"Invoice": "invoices", "Resume": "resumes", "Other": "other"}

# Task 8: what we accept, and how big.
ALLOWED_EXTENSIONS = ("pdf", "jpg", "jpeg", "png")
MIME_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}
MAX_UPLOAD_MB = 10
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# How much cleaned text is stored in the database for search and preview.
TEXT_PREVIEW_CHARS = 1500

# Task 7: processing statuses.
STATUS_PROCESSED = "Processed"
STATUS_REVIEW = "Needs Review"
STATUS_FAILED = "Failed"
STATUSES = (STATUS_PROCESSED, STATUS_REVIEW, STATUS_FAILED)

# A document with any of these fields missing is sent to "Needs Review".
IMPORTANT_FIELDS = {
    "Invoice": ("Invoice Number", "Company Name", "Total Amount"),
    "Resume": ("Name", "Email"),
}

# An ML prediction below this confidence (percent) also needs a human look.
LOW_CONFIDENCE_THRESHOLD = 60.0

# Library page size.
PAGE_SIZE = 20
