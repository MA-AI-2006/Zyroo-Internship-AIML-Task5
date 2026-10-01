# AI Document Intelligence & Workflow Platform — Week 4

**Zyroo Internship Program • AI/ML Internship • Week 4, Task 02**

Week 3 could read a document and tell you what it was. Week 4 remembers:
every upload is stored on disk, tracked in SQLite, and searchable, filterable,
and viewable from the same Streamlit app — with duplicate detection and
error handling so it stays usable when files are messy.

```
Upload → Validate → Hash → Read/OCR → Clean → Classify → Extract →
Store File → Store Metadata → Search/Filter → View
```

## Project structure

```
.
├── app.py                 Streamlit UI only — no database or file logic
├── config.py              paths, limits, statuses, one place to tune settings
├── storage.py             validation, safe filenames, folders, SHA-256 hashing
├── database.py            SQLite repository: create/read/update/delete, search
├── processing.py          read/OCR → clean → classify → extract pipeline
├── ingest.py              wires storage + processing + database into one flow
├── extraction.py          field extraction rules (from Week 3)
├── text_utils.py          text cleaning + OCR image preprocessing (from Week 3)
├── train_classifier.py    trains/compares the ML classifier (from Week 3)
├── generate_samples.py    builds a repeatable set of test documents
├── test_repository.py     automated tests for Task 9
├── dataset/               labeled training data (from Week 3)
├── samples/                generated test files (git-ignored; regenerate anytime)
├── model/                  trained classifier (generated, not hand-edited)
├── data/documents.db       SQLite database (generated on first run)
├── storage/                 uploaded files, sorted into invoices/resumes/other
├── requirements.txt
├── packages.txt             system deps (tesseract-ocr) for Streamlit Cloud
└── README.md
```

## Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Tesseract OCR is only needed for scanned images/PDFs with no selectable text:

- Windows: [Tesseract at UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
- macOS: `brew install tesseract`
- Linux (Debian/Ubuntu): `sudo apt-get install tesseract-ocr`

The app works fine without it — it just skips OCR and tells you so.

## Create / use the SQLite database

You don't need to set anything up by hand. The first time `app.py` (or any
script that imports `database.py`) runs, it creates `data/documents.db` and
its `documents` table automatically. To create it without starting the app:

```bash
python -c "import database; database.init_db()"
```

The database lives at `data/documents.db` — delete that file to start over
with an empty library (the `storage/` folder is separate, so delete both to
fully reset).

## Run the app

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. Drag files onto the uploader, click
**Process**, and they're read, classified, filed, and added to the library
below — all in one step.

## Supported file types

PDF, JPG, and PNG, up to 10 MB each (see `MAX_UPLOAD_MB` in `config.py`).
Anything else is rejected before it touches the disk or the model, with a
plain-language message.

## How duplicate detection works

Every uploaded file gets a SHA-256 hash of its raw bytes before it's saved.
If that exact hash is already in the database, the upload is skipped — you
see the existing record instead of a second copy on disk. Renaming a file
doesn't get past this, since the hash only depends on content, not the name;
uploading the same document twice under different names is correctly caught
as one duplicate.

## Processing status

Every document gets one of three statuses:

| Status | Meaning |
| --- | --- |
| **Processed** | Classified with no missing important fields (and, if the ML model is used, reasonable confidence). |
| **Needs Review** | An important field (e.g. Total Amount, Email) came back empty, or the classifier's confidence was low. |
| **Failed** | The file couldn't be read at all — damaged, encrypted, or no text/OCR available. |

You can edit extracted fields from a document's detail view; saving
re-checks the status automatically.

## Error handling

- Unsupported file types, empty files, and oversized files are rejected
  before processing starts, with a message naming the problem.
- A damaged or encrypted PDF, or an unreadable image, is caught and the
  document is marked **Failed** with a plain-language reason — never a raw
  traceback.
- OCR failures on individual pages are logged and noted rather than
  crashing the whole upload.
- Database errors are logged in full (for debugging) but only ever show the
  user a short, safe message like "The document database is not available
  right now."

## Testing

```bash
python generate_samples.py   # builds samples/ (invoices, resumes, a scan,
                              # a duplicate, a damaged PDF, an unsupported
                              # file, and documents with missing fields)
python test_repository.py    # runs the full Task 9 checklist against a
                              # throw-away database — the real data/ and
                              # storage/ folders are never touched
```

`test_repository.py` covers: 13 sample documents across invoice/resume/other,
duplicate detection, a scanned document, documents with missing fields,
multi-field search, type/status filters, newest/oldest sorting, the detail
view's data, restart persistence (closing and reopening the database), and
rejecting empty/fake/oversized uploads.

### Manual testing evidence

| # | File | Expected | Result |
| --- | --- | --- | --- |
| 1 | `invoice_northwind.pdf` | Invoice, Processed | ✅ |
| 2 | `invoice_missing_total.pdf` | Invoice, Needs Review (Total Amount) | ✅ |
| 3 | `resume_ayesha.pdf` | Resume, Processed | ✅ |
| 4 | `resume_missing_email.pdf` | Resume, Needs Review (Email) | ✅ |
| 5 | `meeting_notes.pdf` | Other, Processed | ✅ |
| 6 | `scanned_invoice.png` | Invoice, Processed via OCR | ✅ |
| 7 | `invoice_northwind_copy.pdf` | Duplicate of #1, not re-stored | ✅ |
| 8 | `damaged.pdf` | Failed, unreadable PDF | ✅ |
| 9 | `notes.txt` | Rejected, unsupported type | ✅ |
| 10 | restart app | All records still present | ✅ |

## Screenshots

_Add screenshots of the upload flow, library view with filters, and a
document's detail view here before submitting._

## Acceptance criteria

- [x] Files are stored in an organized structure (`storage/invoices`,
     `storage/resumes`, `storage/other`).
- [x] SQLite stores document metadata correctly.
- [x] Duplicate files are detected using a SHA-256 hash.
- [x] Search works across filename, company, invoice number, document type,
     and stored text preview.
- [x] Filters (type, status) and sorting (newest/oldest) work.
- [x] A saved document can be opened/downloaded from its detail view.
- [x] Processing errors are handled clearly, without exposing raw exceptions.
- [x] The complete system is tested (`test_repository.py`) and documented.

## What comes next

Week 5 moves from finding documents to acting on them: workflow actions,
rules, review states, and automated processing steps on top of what's
stored here.
