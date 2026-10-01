"""validator.py - Week 5 validation rules.

Validates extracted fields per document type and records EXACTLY which
fields failed (missing vs. invalid, with a reason for each).
"""
import re
from datetime import datetime

REQUIRED_FIELDS = {
    "invoice": ["invoice_number", "date", "company_name", "total_amount"],
    "resume": ["name", "email", "skills"],
}

# Map whatever labels your Week 3 extractor produced onto canonical keys.
FIELD_ALIASES = {
    "invoice no": "invoice_number", "invoice number": "invoice_number",
    "invoice_no": "invoice_number", "invoice_id": "invoice_number",
    "company": "company_name", "company name": "company_name", "vendor": "company_name",
    "total": "total_amount", "total amount": "total_amount", "amount": "total_amount",
    "full name": "name", "candidate_name": "name",
    "e-mail": "email", "email address": "email",
    "mobile": "phone", "phone number": "phone", "contact": "phone",
}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y",
                "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%Y/%m/%d"]


def normalize_fields(fields):
    """Lower-case keys, map aliases to canonical names, drop blank values."""
    out = {}
    for key, value in (fields or {}).items():
        k = str(key).strip().lower().replace("_", " ")
        k = FIELD_ALIASES.get(k, FIELD_ALIASES.get(k.replace(" ", "_"), k.replace(" ", "_")))
        out[k] = value
    return out


def _is_blank(value):
    if value is None:
        return True
    if isinstance(value, (list, tuple, set)):
        return len([v for v in value if str(v).strip()]) == 0
    return str(value).strip() == ""


def validate_email(value):
    return bool(EMAIL_RE.match(str(value).strip()))


def validate_phone(value):
    s = str(value).strip()
    digits = re.sub(r"\D", "", s)
    return bool(re.fullmatch(r"\+?[\d\s\-().]+", s)) and 7 <= len(digits) <= 15


def validate_date(value):
    s = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False


def parse_amount(value):
    """Return a float or None. Accepts '$1,234.50', 'PKR 5,000', '1234'."""
    s = re.sub(r"[^\d.,-]", "", str(value))
    if not s:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def validate_amount(value):
    amount = parse_amount(value)
    return amount is not None and amount > 0


def validate_document(doc_type, fields):
    """Return a dict:
        is_valid       bool
        missing_fields list[str]
        invalid_fields dict[field -> reason]
        failed_fields  list[str]   (missing + invalid, for easy display)
        checked        list[str]   (fields that were looked at)
    """
    doc_type = (doc_type or "").strip().lower()
    f = normalize_fields(fields)
    required = REQUIRED_FIELDS.get(doc_type, [])
    missing = [name for name in required if _is_blank(f.get(name))]
    invalid = {}

    # Format checks apply to any present field ("where applicable").
    checks = {
        "email": (validate_email, "not a valid email address"),
        "phone": (validate_phone, "not a valid phone number"),
        "date": (validate_date, "not a recognised date format"),
        "total_amount": (validate_amount, "not a positive numeric amount"),
    }
    for name, (fn, reason) in checks.items():
        if name in f and not _is_blank(f[name]) and not fn(f[name]):
            invalid[name] = reason

    failed = list(dict.fromkeys(missing + list(invalid)))
    return {
        "is_valid": not failed,
        "missing_fields": missing,
        "invalid_fields": invalid,
        "failed_fields": failed,
        "checked": sorted(set(required) | {k for k in checks if k in f}),
    }
