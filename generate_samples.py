"""
generate_samples.py
Week 4 - Task 9: builds a small, repeatable set of test documents in samples/.

    python generate_samples.py

Creates invoices, resumes, "other" documents, a scanned image, a duplicate
file, a document with missing fields, a damaged PDF and an unsupported .txt,
so every Task 9 case can be tried without hunting for files.
"""

import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

INVOICES = {
    "invoice_northwind.pdf": """INVOICE
Company: Northwind Traders
Invoice Number: INV-2026-001
Date: 12/03/2026
Bill To: Zyroo Labs, Lahore
Item: Cloud hosting (annual)     $1,180.00
Item: Support add-on             $70.00
Total Amount: $1,250.00
Payment due within 30 days.""",
    "invoice_acme.pdf": """TAX INVOICE
Company: Acme Stationers
Invoice No: ACM-88431
Date: 2026-04-21
Bill To: City Print House
Item: A4 paper, 40 reams         PKR 48,000
Grand Total: PKR 48,000
Thank you for your business.""",
    "invoice_globex.pdf": """INVOICE
Company: Globex Logistics
Invoice #: GLX-5520
Date: 05-06-2026
Bill To: Fresh Fields Grocers
Freight, Karachi to Lahore
Amount Due: $3,940.50""",
    "invoice_missing_total.pdf": """INVOICE
Company: Blue Harbor Supplies
Invoice Number: BHS-2210
Date: 18/07/2026
Bill To: Riverside Cafe
Item: Coffee beans, 25 kg
Payment terms: net 15 days.""",
}

RESUMES = {
    "resume_ayesha.pdf": """RESUME
Name: Ayesha Khan
Email: ayesha.khan@example.com
Phone: +92 300 1234567
Skills: Python, SQL, Machine Learning, Streamlit
Education: BS Artificial Intelligence, 2027
Experience: AI/ML intern, 2026""",
    "resume_bilal.pdf": """CURRICULUM VITAE
Name: Bilal Ahmed
Email: bilal.ahmed@example.org
Phone: 0321-7654321
Skills: Java, Spring Boot, PostgreSQL, Docker
Education: BSc Computer Science, 2025
Experience: Backend developer, 2 years""",
    "resume_missing_email.pdf": """RESUME
Name: Sara Malik
Phone: +92 333 9876543
Skills: Figma, UX research, Prototyping
Education: BDes Communication Design
Experience: Junior designer, 1 year""",
}

OTHERS = {
    "meeting_notes.pdf": """Weekly sync notes
Agenda: review the Q3 roadmap, assign action items.
Attendees: Hina, Omar, Zeeshan.
Decision: ship the search feature before the demo day.
Next meeting: Monday 10am.""",
    "travel_itinerary.pdf": """Trip plan: Lahore to Islamabad
Departure: Friday 7:30am by coach.
Hotel booking confirmed for two nights near Blue Area.
Return: Sunday evening.""",
}

SCANNED_TEXT = [
    "INVOICE",
    "Company: Sunrise Bakery",
    "Invoice Number: SB-7741",
    "Date: 09/09/2026",
    "Bill To: Corner Cafe",
    "Total Amount: $860.00",
]


def write_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), text, fontsize=12, lineheight=1.6)
    doc.save(path)
    doc.close()


def write_scanned_png(path: Path) -> None:
    """An image-only 'scan': there is no selectable text, only pixels."""
    img = Image.new("RGB", (1240, 700), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=44)
    except TypeError:  # very old Pillow
        font = ImageFont.load_default()
    y = 60
    for line in SCANNED_TEXT:
        draw.text((80, y), line, fill="black", font=font)
        y += 90
    img.save(path)


def build_samples(target: Path = SAMPLES_DIR) -> list[dict]:
    """Create every sample file. Returns what each one is expected to do."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    plan = []

    for name, text in INVOICES.items():
        write_pdf(target / name, text)
        missing = "missing_total" in name
        plan.append({"file": name, "type": "Invoice",
                     "status": "Needs Review" if missing else "Processed",
                     "note": "Total Amount missing" if missing else ""})
    for name, text in RESUMES.items():
        write_pdf(target / name, text)
        missing = "missing_email" in name
        plan.append({"file": name, "type": "Resume",
                     "status": "Needs Review" if missing else "Processed",
                     "note": "Email missing" if missing else ""})
    for name, text in OTHERS.items():
        write_pdf(target / name, text)
        plan.append({"file": name, "type": "Other", "status": "Processed", "note": ""})

    write_scanned_png(target / "scanned_invoice.png")
    plan.append({"file": "scanned_invoice.png", "type": "Invoice", "status": "Processed",
                 "note": "Scanned image, needs Tesseract OCR"})

    # Same bytes, different name: the duplicate test.
    (target / "invoice_northwind_copy.pdf").write_bytes((target / "invoice_northwind.pdf").read_bytes())
    plan.append({"file": "invoice_northwind_copy.pdf", "type": "-", "status": "Duplicate",
                 "note": "Same content as invoice_northwind.pdf"})

    # A file that starts like a PDF but is damaged.
    (target / "damaged.pdf").write_bytes(b"%PDF-1.4\nthis is not a real pdf body")
    plan.append({"file": "damaged.pdf", "type": "Other", "status": "Failed",
                 "note": "Unreadable PDF"})

    # An unsupported type.
    (target / "notes.txt").write_text("plain text is not a supported upload type\n")
    plan.append({"file": "notes.txt", "type": "-", "status": "Rejected",
                 "note": "Unsupported file type"})
    return plan


if __name__ == "__main__":
    rows = build_samples()
    print(f"Created {len(rows)} sample files in {SAMPLES_DIR}")
    for row in rows:
        print(f"  {row['file']:<30} expected: {row['status']}")
    sys.exit(0)
