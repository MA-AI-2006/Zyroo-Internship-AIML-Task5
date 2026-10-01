"""
processing.py
Week 4 - the "Read/OCR -> Clean -> Classify -> Extract" part of the flow,
moved out of app.py so the interface stays thin.

Nothing here raises for a bad document. process_document() always returns a
ProcessingResult; problems become status "Failed" or "Needs Review" with a
plain-language reason (Tasks 7 and 8).
"""

import functools
import io
import logging
import os
import pickle
from dataclasses import dataclass, field

import fitz  # PyMuPDF
from PIL import Image

import config
from extraction import NOT_FOUND, extract_fields, rule_based_classify
from text_utils import clean_text, is_text_too_short, preprocess_image_for_ocr

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "model")


# ---------------------------------------------------------------- OCR check
@functools.lru_cache(maxsize=1)
def ocr_available() -> bool:
    """True only if pytesseract is installed AND the Tesseract program runs."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


# ------------------------------------------------------------ ML classifier
@functools.lru_cache(maxsize=1)
def load_ml_model():
    """(vectorizer, bundle) from model/, or (None, None) when not trained."""
    vec_path = os.path.join(MODEL_DIR, "vectorizer.pkl")
    clf_path = os.path.join(MODEL_DIR, "classifier.pkl")
    if not (os.path.exists(vec_path) and os.path.exists(clf_path)):
        return None, None
    try:
        with open(vec_path, "rb") as f:
            vectorizer = pickle.load(f)
        with open(clf_path, "rb") as f:
            bundle = pickle.load(f)
        return vectorizer, bundle
    except Exception:
        logger.exception("Could not load the trained model; using rules instead")
        return None, None


def environment_status() -> dict:
    _, bundle = load_ml_model()
    return {"model_name": bundle["name"] if bundle else None, "ocr": ocr_available()}


def ml_classify(text: str, vectorizer, bundle):
    """(label, confidence_percent_or_None) from the trained model."""
    model = bundle["model"]
    X = vectorizer.transform([text])
    label = model.predict(X)[0]
    confidence = None
    if hasattr(model, "predict_proba"):
        confidence = round(float(max(model.predict_proba(X)[0])) * 100, 1)
    return label, confidence


# ------------------------------------------------------------- reading text
class UnreadableFileError(Exception):
    """The file could not be opened. The message is safe to show."""


def _ocr_image(img: Image.Image) -> str:
    import pytesseract
    return pytesseract.image_to_string(preprocess_image_for_ocr(img))


def read_text(file_bytes: bytes, ext: str) -> tuple[str, bool, list[str]]:
    """Returns (raw_text, used_ocr, notes). Notes explain any OCR problems."""
    notes: list[str] = []
    used_ocr = False
    parts: list[str] = []

    if ext == "pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise UnreadableFileError(
                "This PDF could not be opened. It may be damaged."
            ) from exc
        try:
            if doc.needs_pass:
                raise UnreadableFileError(
                    "This PDF is password-protected, so its text cannot be read."
                )
            for page in doc:
                page_text = page.get_text().strip()
                if page_text:
                    parts.append(page_text)
                    continue
                if not ocr_available():
                    if "OCR is not available" not in " ".join(notes):
                        notes.append("OCR is not available, so scanned pages were skipped.")
                    continue
                try:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    parts.append(_ocr_image(img))
                    used_ocr = True
                except Exception:
                    logger.exception("OCR failed on a PDF page")
                    notes.append("OCR failed on at least one page.")
        finally:
            doc.close()
    else:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            img.load()
        except Exception as exc:
            raise UnreadableFileError(
                "This image could not be opened. It may be damaged."
            ) from exc
        if not ocr_available():
            notes.append("OCR is not available, so this image could not be read.")
        else:
            try:
                parts.append(_ocr_image(img))
                used_ocr = True
            except Exception:
                logger.exception("OCR failed on an image")
                notes.append("OCR failed while reading this image.")

    return "\n".join(parts).strip(), used_ocr, notes


# ------------------------------------------------------------------ status
def determine_status(doc_type: str, fields: dict, confidence=None) -> tuple[str, str]:
    """Task 7: Processed or Needs Review, with a reason. (Failed is decided
    earlier, when nothing could be read.)"""
    missing = [
        name for name in config.IMPORTANT_FIELDS.get(doc_type, ())
        if fields.get(name, NOT_FOUND) in (NOT_FOUND, "", None)
    ]
    if missing:
        return config.STATUS_REVIEW, "Missing: " + ", ".join(missing) + "."
    if confidence is not None and confidence < config.LOW_CONFIDENCE_THRESHOLD:
        return config.STATUS_REVIEW, (
            f"The classifier is only {confidence:.0f}% sure about the document type."
        )
    return config.STATUS_PROCESSED, "All important fields were found."


def columns_from_fields(fields: dict) -> dict:
    """Copy the searchable fields into their own database columns."""
    def clean(value):
        return None if value in (None, "", NOT_FOUND) else value
    return {
        "company": clean(fields.get("Company Name")),
        "invoice_number": clean(fields.get("Invoice Number")),
        "total_amount": clean(fields.get("Total Amount")),
    }


# ---------------------------------------------------------------- pipeline
@dataclass
class ProcessingResult:
    document_type: str = "Other"
    fields: dict = field(default_factory=dict)
    text: str = ""
    used_ocr: bool = False
    status: str = config.STATUS_FAILED
    status_reason: str = ""
    confidence: float | None = None
    classifier: str = ""
    steps: list = field(default_factory=list)  # [(label, "ok" | "fail" | "skip")]


def _failed(reason: str, steps: list, used_ocr: bool = False) -> ProcessingResult:
    return ProcessingResult(used_ocr=used_ocr, status=config.STATUS_FAILED,
                            status_reason=reason, steps=steps)


def process_document(file_bytes: bytes, ext: str, use_ml: bool = True) -> ProcessingResult:
    steps = [("Read / OCR", "skip"), ("Clean", "skip"), ("Classify", "skip"), ("Extract", "skip")]

    def mark(index: int, state: str):
        steps[index] = (steps[index][0], state)

    # Read / OCR
    try:
        raw_text, used_ocr, notes = read_text(file_bytes, ext)
    except UnreadableFileError as exc:
        mark(0, "fail")
        return _failed(str(exc), steps)
    except Exception:
        logger.exception("Unexpected error while reading a document")
        mark(0, "fail")
        return _failed("This file could not be read.", steps)
    mark(0, "ok")
    if used_ocr:
        steps[0] = ("Read / OCR (scanned)", "ok")

    # Clean
    text = clean_text(raw_text)
    if is_text_too_short(text):
        mark(1, "fail")
        reason = "No readable text was found in this file."
        if notes:
            reason += " " + " ".join(notes)
        else:
            reason += " If it is a scan, try a clearer image."
        return _failed(reason, steps, used_ocr)
    mark(1, "ok")

    # Classify
    try:
        vectorizer, bundle = load_ml_model() if use_ml else (None, None)
        confidence, classifier = None, "Rule-based"
        if bundle is not None:
            doc_type, confidence = ml_classify(text, vectorizer, bundle)
            classifier = bundle["name"]
        else:
            doc_type = rule_based_classify(text)
    except Exception:
        logger.exception("Classification failed; falling back to rules")
        doc_type, confidence, classifier = rule_based_classify(text), None, "Rule-based"
    mark(2, "ok")

    # Extract
    try:
        fields = extract_fields(doc_type, text)
    except Exception:
        logger.exception("Field extraction failed")
        mark(3, "fail")
        return ProcessingResult(
            document_type=doc_type, text=text, used_ocr=used_ocr,
            status=config.STATUS_REVIEW,
            status_reason="Fields could not be extracted automatically.",
            confidence=confidence, classifier=classifier, steps=steps)
    mark(3, "ok")

    status, reason = determine_status(doc_type, fields, confidence)
    return ProcessingResult(
        document_type=doc_type, fields=fields, text=text, used_ocr=used_ocr,
        status=status, status_reason=reason, confidence=confidence,
        classifier=classifier, steps=steps)
