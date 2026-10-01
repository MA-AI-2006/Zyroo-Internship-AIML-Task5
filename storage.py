"""
storage.py
Week 4 - Task 1 (structured file storage), Task 3 (hashing) and the
"Validate" step of the upload flow.

No Streamlit and no database code in here.
"""

import hashlib
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import config

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """An upload was rejected. The message is safe to show to users."""


class StorageError(Exception):
    """A file could not be written or removed. The message is safe to show."""


# First bytes of each allowed format, so a renamed .exe cannot pass as a .pdf.
_MAGIC_BYTES = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
}


def get_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower().lstrip(".")


def validate_upload(filename: str, data: bytes) -> str:
    """Check type, size and content signature. Returns the extension."""
    ext = get_extension(filename)
    if ext not in config.ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"'{filename}' is not a supported file type. "
            "Upload a PDF, JPG or PNG file."
        )
    if not data:
        raise ValidationError(f"'{filename}' is empty.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        size_mb = len(data) / (1024 * 1024)
        raise ValidationError(
            f"'{filename}' is {size_mb:.1f} MB. "
            f"The upload limit is {config.MAX_UPLOAD_MB} MB."
        )
    if not data.startswith(_MAGIC_BYTES[ext]):
        raise ValidationError(
            f"'{filename}' does not look like a real {ext.upper()} file. "
            "Check the file and try again."
        )
    return ext


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_safe_filename(original_filename: str, ext: str) -> str:
    """timestamp + random id + sanitised stem. Never trusts the original name."""
    stem = re.sub(r"[^A-Za-z0-9]+", "_", Path(original_filename).stem)
    stem = stem.strip("_")[:40] or "document"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}_{stem}.{ext}"


def folder_for(doc_type: str) -> str:
    return config.FOLDERS.get(doc_type, config.FOLDERS["Other"])


def save_file(data: bytes, original_filename: str, ext: str, doc_type: str,
              storage_root: Path = config.STORAGE_DIR) -> tuple[str, str]:
    """Write the file into storage/<type-folder>/.

    Returns (stored_filename, relative_path). The relative path (for example
    "storage/invoices/20260921_101500_ab12cd34_bill.pdf") is what the database
    keeps, so the project folder can be moved without breaking records.
    """
    storage_root = Path(storage_root)
    folder = folder_for(doc_type)
    stored_filename = make_safe_filename(original_filename, ext)
    target = storage_root / folder / stored_filename
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)  # atomic: no half-written files
    except OSError as exc:
        logger.exception("Could not write %s", target)
        raise StorageError(
            "The file could not be saved to disk. Check free space and folder "
            "permissions, then try again."
        ) from exc
    relative_path = f"{storage_root.name}/{folder}/{stored_filename}"
    return stored_filename, relative_path


def resolve_path(relative_path: str, storage_root: Path = config.STORAGE_DIR) -> Path | None:
    """Turn a stored relative path into a real path, staying inside storage."""
    storage_root = Path(storage_root).resolve()
    candidate = (storage_root.parent / relative_path).resolve()
    if storage_root not in candidate.parents:
        return None  # refuses paths that try to escape the storage folder
    return candidate


def read_file(relative_path: str, storage_root: Path = config.STORAGE_DIR) -> bytes | None:
    """Return the file's bytes, or None when it is missing or unreadable."""
    path = resolve_path(relative_path, storage_root)
    if path is None or not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        logger.exception("Could not read %s", path)
        return None


def delete_file(relative_path: str, storage_root: Path = config.STORAGE_DIR) -> bool:
    path = resolve_path(relative_path, storage_root)
    if path is None or not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        logger.exception("Could not delete %s", path)
        return False
