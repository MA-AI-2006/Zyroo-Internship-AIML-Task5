"""
extraction.py
Week 3 — Step 7 & 8: improved information extraction rules + consistent
"Not Found" handling so the app never breaks on a missing field.
"""

import re

NOT_FOUND = "Not Found"

# Broadened keyword lists used by the rule-based classifier fallback
INVOICE_KEYWORDS = [
    "invoice", "invoice number", "invoice no", "total", "amount due",
    "bill to", "grand total", "tax invoice", "payment due",
]
RESUME_KEYWORDS = [
    "resume", "curriculum vitae", "cv", "skills", "education",
    "experience", "objective", "career summary",
]


def rule_based_classify(text: str) -> str:
    lower = text.lower()
    invoice_score = sum(1 for kw in INVOICE_KEYWORDS if kw in lower)
    resume_score = sum(1 for kw in RESUME_KEYWORDS if kw in lower)
    if invoice_score == 0 and resume_score == 0:
        return "Other"
    if invoice_score >= resume_score:
        return "Invoice"
    return "Resume"


def extract_invoice_fields(text: str) -> dict:
    fields = {
        "Invoice Number": NOT_FOUND,
        "Date": NOT_FOUND,
        "Company Name": NOT_FOUND,
        "Total Amount": NOT_FOUND,
    }

    # Invoice number: several common label variants
    inv_num = re.search(
        r"invoice\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9\-]+)",
        text, re.IGNORECASE,
    )
    if inv_num:
        fields["Invoice Number"] = inv_num.group(1).strip()
    else:
        # fallback: a bare "#12345" style number near the top of the doc
        bare_num = re.search(r"#\s*([A-Za-z0-9\-]{4,})", text)
        if bare_num:
            fields["Invoice Number"] = bare_num.group(1).strip()

    # Date: multiple common formats (DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, etc.)
    date = re.search(
        r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\b",
        text,
    )
    if date:
        fields["Date"] = date.group(1).strip()

    # Total amount: look for common labels, allow currency symbols/codes
    total = re.search(
        r"(?:grand total|amount due|total amount|total)\s*[:\-]?\s*"
        r"([A-Za-z]{0,3}\s?[\$€£]?\s?[\d,]+\.?\d*)",
        text, re.IGNORECASE,
    )
    if total:
        fields["Total Amount"] = total.group(1).strip()

    # Company name: prefer a line explicitly labeled "Company" / "Company Name"
    company = re.search(r"company(?:\s*name)?\s*[:\-]\s*(.+)", text, re.IGNORECASE)
    if company:
        fields["Company Name"] = company.group(1).strip().split("\n")[0][:80]
    else:
        # fallback: first reasonably short line that isn't the word "invoice"
        for line in text.splitlines():
            clean = line.strip()
            if clean and "invoice" not in clean.lower() and 0 < len(clean) < 60:
                fields["Company Name"] = clean
                break

    return fields


def extract_resume_fields(text: str) -> dict:
    fields = {
        "Name": NOT_FOUND,
        "Email": NOT_FOUND,
        "Phone": NOT_FOUND,
        "Skills": NOT_FOUND,
    }

    email = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    if email:
        fields["Email"] = email.group(0).strip()

    # Phone: accept +country codes, dashes, spaces, parentheses
    phone = re.search(r"(\+?\d[\d\-\s\(\)]{7,}\d)", text)
    if phone:
        fields["Phone"] = phone.group(1).strip()

    # Skills: text after a "Skills" label, stopping at the next section label
    skills_match = re.search(
        r"skills\s*[:\-]?\s*(.+?)(?:education|experience|$)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if skills_match:
        skills_text = skills_match.group(1).strip().replace("\n", " ")[:200]
        if skills_text:
            fields["Skills"] = skills_text

    # Name: prefer a label like "Name:" else fall back to the first non-empty line
    name_label = re.search(r"\bname\s*[:\-]\s*(.+)", text, re.IGNORECASE)
    if name_label:
        fields["Name"] = name_label.group(1).strip().split("\n")[0][:60]
    else:
        for line in text.splitlines():
            clean = line.strip()
            if clean and clean.lower() not in ("resume", "curriculum vitae", "cv"):
                fields["Name"] = clean[:60]
                break

    return fields


def extract_fields(doc_type: str, text: str) -> dict:
    if doc_type == "Invoice":
        return extract_invoice_fields(text)
    if doc_type == "Resume":
        return extract_resume_fields(text)
    return {}
