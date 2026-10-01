"""workflow.py - workflow states, valid transitions and the rule engine.

Pure Python: no Streamlit, no SQLite. It receives document data and returns a
Decision (next state + clear reason). To change behaviour, edit RULES or the
constants below - the UI never needs to change.
"""
from dataclasses import dataclass

# ---- States ---------------------------------------------------------------
NEW = "New"
PROCESSING = "Processing"
NEEDS_REVIEW = "Needs Review"
APPROVED = "Approved"
REJECTED = "Rejected"
COMPLETED = "Completed"
ALL_STATES = [NEW, PROCESSING, NEEDS_REVIEW, APPROVED, REJECTED, COMPLETED]

# Valid transitions. Anything not listed is blocked.
TRANSITIONS = {
    NEW: {PROCESSING},
    PROCESSING: {NEEDS_REVIEW, COMPLETED, NEW},   # NEW = processing failed, retry later
    NEEDS_REVIEW: {APPROVED, REJECTED},
    APPROVED: {COMPLETED},
    REJECTED: {NEW},                              # allow re-submission
    COMPLETED: set(),
}

# ---- Configuration ---------------------------------------------------------
# Classifications with confidence BELOW this value go to Needs Review.
# Documented threshold: 0.60 (60%). Only applied when the classifier actually
# supplies a confidence - we never invent or estimate one.
CONFIDENCE_THRESHOLD = 0.60
SUPPORTED_TYPES = {"invoice", "resume"}


class InvalidTransition(Exception):
    pass


def can_transition(current, new):
    return new in TRANSITIONS.get(current, set())


def assert_transition(current, new):
    if not can_transition(current, new):
        raise InvalidTransition(f"Invalid transition: {current} -> {new}")


@dataclass
class Decision:
    next_state: str
    action: str
    reason: str


# ---- Rules -----------------------------------------------------------------
# Each rule takes a context dict and returns a reason string if the document
# must go to review, or None to pass. Rules run in order; first hit wins.
# ctx keys: doc_type, fields, validation, confidence (may be None), is_duplicate

def rule_unreadable(ctx):
    fields = ctx.get("fields") or {}
    if not any(str(v).strip() for v in fields.values() if v is not None):
        return "No readable text/fields extracted (unreadable or scanned document)"


def rule_unsupported_type(ctx):
    t = (ctx.get("doc_type") or "").lower()
    if t not in SUPPORTED_TYPES:
        return f"Unsupported or unknown document type: '{t or 'none'}'"


def rule_low_confidence(ctx):
    conf = ctx.get("confidence")
    if conf is not None and conf < CONFIDENCE_THRESHOLD:
        return f"Low classification confidence ({conf:.2f} < {CONFIDENCE_THRESHOLD:.2f})"


def rule_validation(ctx):
    v = ctx.get("validation") or {}
    if v.get("missing_fields"):
        return "Missing required fields: " + ", ".join(v["missing_fields"])
    if v.get("invalid_fields"):
        bad = ", ".join(f"{k} ({r})" for k, r in v["invalid_fields"].items())
        return "Invalid fields: " + bad


def rule_duplicate(ctx):
    if ctx.get("is_duplicate"):
        return "Possible duplicate document"


RULES = [rule_unreadable, rule_unsupported_type, rule_low_confidence,
         rule_validation, rule_duplicate]


def decide(doc_type, fields, validation, confidence=None, is_duplicate=False):
    """Determine the next action for a document being processed."""
    ctx = {"doc_type": doc_type, "fields": fields, "validation": validation,
           "confidence": confidence, "is_duplicate": is_duplicate}
    for rule in RULES:
        reason = rule(ctx)
        if reason:
            return Decision(NEEDS_REVIEW, "sent_to_review", reason)
    return Decision(COMPLETED, "auto_completed", "Passed all validation and workflow rules")
