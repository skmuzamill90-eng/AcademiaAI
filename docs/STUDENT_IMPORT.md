# Bulk student import

Administrators can add or update many students at once from an Excel or CSV file.

**Where:** sign in as an administrator → sidebar **Manage → Import students** (`/import`).
Other roles do not see the menu item, are redirected away from the page, and receive `403` from every `/api/imports/*` endpoint.

## Before you start

- Download the **template** (button at the top of the page) to get the exact column names, or use your own headers and map them in step 2.
- **Required to add a new student:** Student ID (`STU` + 8 digits, e.g. `STU20260501`), Student Name, Department, Year of Study, Section, Admission Year. IDs are matched case-insensitively.
- Every other field is optional. A blank cell is stored as "not measured", never as zero.
- Limits: 10 MB and 20,000 data rows per file (override with `IMPORT_MAX_UPLOAD_MB` and `IMPORT_MAX_ROWS`). Excel files use the first visible sheet; the first non-blank row is the header.

## The four steps

1. **Upload** – drag a `.xlsx`, `.xls` or `.csv` file onto the drop area or use *Choose file*. File type, size, emptiness and content-vs-extension are checked in the browser and again on the server.
2. **Preview & mapping** – the first 100 rows are shown with spreadsheet row numbers, sticky headers and horizontal scrolling. Headers are matched to student fields automatically (exact names, labels, common aliases such as "Roll No", "Dept", "Email ID", and close spellings); each match shows an *Auto / Likely / Manual* badge. Change any mapping with the dropdowns. A column can feed one field only. Choose the **import mode**:
   | Mode | Existing ID | New ID | Blank ID |
   |---|---|---|---|
   | Insert only | skipped (never overwritten) | added | error |
   | Update existing | updated (blank cells keep current values) | skipped, reported *not found* | error |
   | Insert or update | updated | added | error |
3. **Validate** – a background job checks every row on the server. Summary cards show **total rows, valid records, duplicates and invalid records**. Each problem is listed with its spreadsheet row, field, column, value and a fix. Invalid cells are outlined in the preview. *Error report* downloads the same list as CSV.
4. **Import** – confirm in the dialog. The server **re-validates the whole file** (client results are never trusted), then saves. Progress is shown live; **Cancel** is available until the final save begins. The result page shows rows added, updated and skipped, with a downloadable error report.

### What counts as what
- **Duplicates:** a Student ID repeated earlier in the same file (the first occurrence wins; later ones are skipped), or, in *Insert only* mode, an ID that already exists.
- **Invalid:** a row with a bad value (out of range, not a number, unknown category such as Club participation, bad email, bad ID format), a missing required value for a new student, or, in *Update existing* mode, an unknown ID.
- Validation rules are the same as the single-student form (`StudentCreate` / `StudentUpdate`): CGPA 0–10, percentages 0–100, year of study 1–8, categories case-insensitive, and so on.

## How data is saved

This project stores student data in CSV files (`data/students.csv`, `academics.csv`, `attendance.csv`, `lms.csv`, `engagement.csv`, `placements.csv`, `skills.csv`, `feedback.csv`); there is no SQL/MySQL layer in this codebase, so the import writes to those same files exactly like *Add student* does. An import:
- reads and validates the whole file in batches of 500 rows (bounded memory and regular progress/cancel checks);
- writes **nothing** until validation of the entire file has finished;
- stages all CSV files, swaps them in together, and restores the originals if any step fails;
- reloads the analytics service once, so scores, risk indicators, segments and dashboards update immediately;
- allows only one import at a time (a second one gets `409`).

Uploaded files are kept in a private temporary folder (`IMPORT_STORAGE_DIR`, default `<system temp>/academia_imports`) for up to 2 hours and are only visible to the administrator who uploaded them. Upload and job state is held in the API process's memory: run a single worker (`uvicorn` default) or the status of a job will not be found across processes, and restarting the API discards pending uploads and job history.

## API (administrator only)

| Method & path | Purpose |
|---|---|
| `GET /api/imports/config` | Importable fields, modes, limits |
| `GET /api/imports/template` | CSV template download |
| `POST /api/imports/uploads` (multipart `file`) | Upload; returns headers, preview rows, suggested mapping |
| `GET /api/imports/uploads/{id}/rows?offset&limit` | Page through uploaded rows |
| `DELETE /api/imports/uploads/{id}` | Discard an upload |
| `POST /api/imports/uploads/{id}/validate` `{mapping, mode}` | Start validation job (202) |
| `POST /api/imports/uploads/{id}/import` `{mapping, mode}` | Start import job (202) |
| `GET /api/imports/jobs/{job}` | Progress, summary, result |
| `GET /api/imports/jobs/{job}/issues?offset&limit&code` | Problems with row numbers |
| `GET /api/imports/jobs/{job}/issues/by-row?first_row&last_row` | Problems for preview highlighting |
| `POST /api/imports/jobs/{job}/cancel` | Cancel (409 once saving has begun) |
| `GET /api/imports/jobs/{job}/errors.csv` | Error report download |

`mapping` is `{ "<student field>": <zero-based column index> }`. Error-report cells that begin with `= + - @` are prefixed with `'` so spreadsheets cannot execute them as formulas.

## Running the tests

```bash
# backend (from the project root)
pip install -r requirements.txt        # now includes openpyxl and xlrd
pip install xlwt                       # optional: enables the legacy .xls upload test
python -m pytest

# frontend
cd frontend
npm install
npm test            # vitest: mapping logic + upload/mapping/validation/results flow
npm run build       # tsc -b && vite build
```

## Known limitations

- Only the first visible sheet of a workbook is read.
- The preview and in-grid highlighting cover the first 100 rows; *all* problems are still listed in the table below and in the error report.
- Problem lists are capped at 50,000 entries per job (the summary says when this happens).
- Interventions are not part of this import.
- Cancellation is not possible once the final save has started (a few seconds at most for files near the limit).
