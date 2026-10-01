# Week 5 - Advanced Document Workflow & Automation

## Workflow
`Upload -> Process -> Classify -> Extract -> Validate -> Apply Rules -> Review / Approve / Reject -> Complete -> Audit History`

## States and valid transitions
| From | Allowed next states |
|---|---|
| New | Processing |
| Processing | Needs Review, Completed, New (processing failed - retry) |
| Needs Review | Approved, Rejected |
| Approved | Completed |
| Rejected | New (resubmit) |
| Completed | none |

Any other change raises `InvalidTransition` and is blocked.

## Modules
| File | Purpose |
|---|---|
| `workflow.py` | States, transitions, rule engine (no UI, no DB) |
| `validator.py` | Required-field + format validation, records exactly which fields failed |
| `audit.py` | `audit_log` table: document id, action, previous/new status, timestamp, reason |
| `workflow_service.py` | Connects rules to SQLite: migration, processing, batch, review, search, metrics |
| `workflow_pages.py` | Streamlit pages: review queue, batch, search/filters, metrics |
| `test_week5.py` | Automated tests for the failure scenarios |

## Rules (edit `RULES` in `workflow.py`)
1. No readable fields -> Needs Review
2. Unsupported document type -> Needs Review
3. Classifier confidence below **0.60** -> Needs Review (only if the classifier provides one; never estimated)
4. Missing or invalid required fields -> Needs Review
5. Possible duplicate -> Needs Review
6. Otherwise -> Completed automatically

## Testing
Run `pytest test_week5.py -v`. Add a table of your 10-15 real test documents and screenshots below.

| # | Document | Scenario | Expected | Actual |
|---|---|---|---|---|
| 1 | | Normal invoice | Completed | |
