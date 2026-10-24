"""Bulk student import: upload, mapping, validation, modes, results and permissions.

Tests run against a private temporary copy of the CSV data (see conftest.py) and a temporary upload folder.
"""
import csv
import io
import time

import pytest
from fastapi.testclient import TestClient

from app import import_service
from app.auth import get_current_user
from app.main import create_app

HEADER = ["Roll No", "Name", "Dept", "Year", "Section", "Admission Year", "Email", "CGPA"]


def make_csv(rows, header=HEADER) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue().encode()


def full_mapping(headers=HEADER):
    names = {"Roll No": "student_id", "Name": "student_name", "Dept": "department", "Year": "year_of_study",
             "Section": "section", "Admission Year": "admission_year", "Email": "student_email", "CGPA": "cgpa"}
    return {names[h]: i for i, h in enumerate(headers) if h in names}


@pytest.fixture()
def ic(writable_client, tmp_path, monkeypatch):
    """Admin client whose import manager stores uploads in a temp folder."""
    app = writable_client.app
    app.state.import_manager = import_service.ImportManager(tmp_path / "uploads")
    return writable_client


def upload(client, content: bytes, name="students.csv"):
    return client.post("/api/imports/uploads", files={"file": (name, content, "application/octet-stream")})


def run_job(client, kind, upload_id, mapping, mode):
    res = client.post(f"/api/imports/uploads/{upload_id}/{kind}", json={"mapping": mapping, "mode": mode})
    assert res.status_code == 202, res.text
    job_id = res.json()["data"]["job_id"]
    for _ in range(200):
        data = client.get(f"/api/imports/jobs/{job_id}").json()["data"]
        if data["status"] in ("completed", "failed", "cancelled"):
            return data
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def student_ids(client):
    """Every student ID, paging through the API (it caps pages at 200 rows)."""
    ids, offset = set(), 0
    while True:
        body = client.get(f"/api/students?limit=200&offset={offset}").json()
        ids |= {r["student_id"] for r in body["data"]}
        if not body["meta"]["has_more"]:
            return ids
        offset += 200


# ---------------------------------------------------------------- permissions
def test_import_routes_require_authentication():
    with TestClient(create_app()) as client:
        assert client.get("/api/imports/config").status_code == 401
        assert client.get("/api/imports/roster").status_code == 401
        assert client.post("/api/imports/uploads", files={"file": ("a.csv", b"a", "text/csv")}).status_code == 401


@pytest.mark.parametrize("role", ["super_admin", "student"])
def test_non_college_admin_roles_are_forbidden(role):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"username": "x", "role": role, "institution_id": "inst-1", "student_id": "STU1"}
    with TestClient(app) as client:
        assert client.get("/api/imports/config").status_code == 403
        assert client.get("/api/imports/template").status_code == 403
        assert client.get("/api/imports/roster").status_code == 403
        assert client.post("/api/imports/uploads", files={"file": ("a.csv", b"a,b\n1,2", "text/csv")}).status_code == 403


# ---------------------------------------------------------------- template + config
def test_template_lists_every_importable_field(ic):
    res = ic.get("/api/imports/template")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    header = next(csv.reader(io.StringIO(res.text)))
    assert header[0] == "student_id" and "student_name" in header and "cgpa" in header
    assert len(header) == 33
    cfg = ic.get("/api/imports/config").json()["data"]
    assert [f["key"] for f in cfg["fields"]] == header
    assert {f["key"] for f in cfg["fields"] if f["required_for_insert"]} == {
        "student_id", "student_name", "department", "year_of_study", "section", "admission_year"
    }
    assert {m["value"] for m in cfg["modes"]} == {"insert_only", "update_existing", "insert_or_update"}


def test_template_round_trips_through_import(ic):
    body = ic.get("/api/imports/template").content
    data = upload(ic, body).json()["data"]
    mapping = {k: v["column"] for k, v in data["suggested_mapping"].items()}
    assert len(mapping) == len(data["headers"])             # every template column maps automatically
    job = run_job(ic, "validate", data["upload_id"], mapping, "insert_only")
    assert job["status"] == "completed" and job["summary"]["invalid_rows"] == 0


# ---------------------------------------------------------------- upload + mapping suggestions
def test_upload_returns_preview_and_suggested_mapping(ic):
    data = upload(ic, make_csv([["", "Asha K", "CSE", "2", "A", "2025", "a@x.edu", "8.1"]])).json()["data"]
    assert data["headers"] == HEADER and data["total_rows"] == 1
    assert data["preview"][0] == {"row": 2, "cells": ["", "Asha K", "CSE", "2", "A", "2025", "a@x.edu", "8.1"]}
    sm = data["suggested_mapping"]
    assert sm["student_id"]["column"] == 0 and sm["student_name"]["column"] == 1
    assert sm["department"]["column"] == 2 and sm["year_of_study"]["column"] == 3
    assert sm["student_email"]["column"] == 6 and sm["cgpa"]["column"] == 7
    assert all(0 < v["confidence"] <= 1 for v in sm.values())


def test_suggestion_never_maps_one_column_twice():
    sm = import_service.suggest_mapping(["Year", "Year of study", "Admission year"])
    cols = [v["column"] for v in sm.values()]
    assert len(cols) == len(set(cols))


def test_upload_rejects_bad_files(ic, monkeypatch):
    assert upload(ic, b"x", "notes.txt").status_code == 415
    assert upload(ic, b"", "empty.csv").status_code == 422
    assert upload(ic, b"not a zip", "fake.xlsx").status_code == 422
    assert upload(ic, b"PK\x03\x04junk", "disguised.csv").status_code == 422
    assert upload(ic, b"Name,Dept\n", "header-only.csv").status_code == 422
    monkeypatch.setattr("app.routers.imports.MAX_UPLOAD_BYTES", 10)
    assert upload(ic, b"a,b\n" + b"1,2\n" * 20).status_code == 413


def test_xlsx_upload_end_to_end(ic):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    ws.append(["STU20269001", "Excel Student", "CSE", 2.0, "B", 2025, "e@x.edu", 7.5])   # numbers arrive as floats
    buf = io.BytesIO()
    wb.save(buf)
    data = upload(ic, buf.getvalue(), "roster.xlsx").json()["data"]
    assert data["format"] == "xlsx" and data["preview"][0]["cells"][3] == "2"
    job = run_job(ic, "import", data["upload_id"], full_mapping(), "insert_only")
    assert job["status"] == "completed" and job["result"]["inserted"] == 1
    assert "STU20269001" in student_ids(ic)

    created = ic.post("/api/students", json={
        "student_name": "Added In App", "department": "Computer Science and Engineering", "year_of_study": 1,
        "section": "A", "admission_year": 2026,
    })
    assert created.status_code == 201, created.text
    new_id = created.json()["data"]["student_id"]
    assert new_id in student_ids(ic)
    assert job["result"]["roster_saved"] is True

    downloaded = ic.get("/api/imports/roster")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    updated_workbook = openpyxl.load_workbook(io.BytesIO(downloaded.content), data_only=True)
    updated_rows = list(updated_workbook.active.iter_rows(values_only=True))
    assert updated_rows[-1][0] == new_id
    assert updated_rows[-1][1] == "Added In App"
    assert updated_rows[-1][2] == "Computer Science and Engineering"
    changed = ic.patch(f"/api/students/{new_id}", json={"student_name": "Updated In App"})
    assert changed.status_code == 200, changed.text
    updated_workbook.close()
    downloaded = ic.get("/api/imports/roster")
    updated_workbook = openpyxl.load_workbook(io.BytesIO(downloaded.content), data_only=True)
    assert updated_workbook.active.cell(updated_workbook.active.max_row, 2).value == "Updated In App"
    updated_workbook.close()


def test_csv_roster_is_updated_when_a_student_is_added_in_the_app(ic):
    content = make_csv([["STU20269003", "CSV Student", "CSE", "2", "A", "2025", "csv@example.edu", "8.1"]])
    data = upload(ic, content, "students.csv").json()["data"]
    mapping = {key: value["column"] for key, value in data["suggested_mapping"].items()}
    job = run_job(ic, "import", data["upload_id"], mapping, "insert_only")
    assert job["status"] == "completed" and job["result"]["roster_saved"] is True

    created = ic.post("/api/students", json={
        "student_name": "CSV App Student", "department": "Computer Science and Engineering", "year_of_study": 1,
        "section": "A", "admission_year": 2026,
    })
    assert created.status_code == 201, created.text
    new_id = created.json()["data"]["student_id"]
    roster = ic.get("/api/imports/roster")
    assert roster.status_code == 200
    rows = list(csv.DictReader(io.StringIO(roster.text)))
    assert rows[-1]["Roll No"] == new_id
    assert rows[-1]["Name"] == "CSV App Student"


def test_existing_roster_is_retained_when_import_contains_only_existing_students(ic):
    existing_id = next(iter(student_ids(ic)))
    content = make_csv([[existing_id, "Existing Student", "CSE", "2", "A", "2025", "", ""]])
    data = upload(ic, content, "existing-students.csv").json()["data"]
    mapping = {key: value["column"] for key, value in data["suggested_mapping"].items()}
    job = run_job(ic, "import", data["upload_id"], mapping, "insert_only")
    assert job["status"] == "completed"
    assert job["result"]["inserted"] == 0
    assert job["result"]["roster_saved"] is True
    assert ic.get("/api/imports/roster").status_code == 200


def test_legacy_xls_upload(ic):
    xlwt = pytest.importorskip("xlwt")
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    for c, h in enumerate(HEADER):
        ws.write(0, c, h)
    for c, v in enumerate(["STU20269002", "Old Excel", "CSE", 3, "C", 2024, "o@x.edu", 6.5]):
        ws.write(1, c, v)
    buf = io.BytesIO()
    wb.save(buf)
    data = upload(ic, buf.getvalue(), "legacy.xls").json()["data"]
    assert data["format"] == "xls" and data["total_rows"] == 1
    job = run_job(ic, "import", data["upload_id"], full_mapping(), "insert_only")
    assert job["result"]["inserted"] == 1


def test_mapping_is_validated_before_a_job_starts(ic):
    uid = upload(ic, make_csv([["", "A", "CSE", "1", "A", "2025", "", ""]])).json()["data"]["upload_id"]
    post = lambda mapping, mode="insert_only": ic.post(f"/api/imports/uploads/{uid}/validate", json={"mapping": mapping, "mode": mode})
    assert post({"student_name": 1}).status_code == 422                                   # required fields unmapped
    assert post({**full_mapping(), "cgpa": 1}).status_code == 422                          # one column used twice
    assert post({**full_mapping(), "cgpa": 99}).status_code == 422                         # column does not exist
    assert post({**full_mapping(), "nonsense": 2}).status_code == 422                      # unknown field
    assert post(full_mapping(), "overwrite_everything").status_code == 422                 # unknown mode
    assert post({"student_name": 1}, "update_existing").status_code == 422                 # no Student ID for update
    assert post({"student_id": 0}, "update_existing").status_code == 422                   # nothing to update


# ---------------------------------------------------------------- validation + error reporting
def test_validation_reports_row_numbers_and_summary(ic):
    existing = sorted(student_ids(ic))[0]
    rows = [
        ["STU20269101", "Valid One", "CSE", "2", "A", "2025", "v@x.edu", "8.0"],      # row 2 valid
        ["STU20269102", "Bad Year", "CSE", "12", "A", "2025", "b@x.edu", "8.0"],      # row 3 year out of range
        ["STU20269101", "Dup Of Row 2", "CSE", "2", "A", "2025", "d@x.edu", "8.0"],   # row 4 duplicate in file
        ["STU2026", "Bad Id", "CSE", "2", "A", "2025", "i@x.edu", "8.0"],             # row 5 bad id
        ["STU20269103", "", "CSE", "2", "A", "2025", "n@x.edu", "8.0"],               # row 6 missing name
        ["STU20269104", "Bad Email", "CSE", "2", "A", "2025", "no-at-sign", "11"],    # row 7 email + cgpa
        [existing, "Already There", "CSE", "2", "A", "2025", "e@x.edu", "8.0"],       # row 8 exists
    ]
    uid = upload(ic, make_csv(rows)).json()["data"]["upload_id"]
    job = run_job(ic, "validate", uid, full_mapping(), "insert_only")
    s = job["summary"]
    assert (s["total_rows"], s["valid_rows"], s["duplicate_rows"], s["invalid_rows"]) == (7, 1, 2, 4)
    issues = ic.get(f"/api/imports/jobs/{job['job_id']}/issues?limit=200").json()["data"]
    by = {(i["row"], i["field"]): i for i in issues}
    assert by[(3, "year_of_study")]["code"] == "invalid_value" and "1–8" in by[(3, "year_of_study")]["message"]
    assert by[(4, "student_id")]["code"] == "duplicate_in_file" and "row 2" in by[(4, "student_id")]["message"]
    assert by[(5, "student_id")]["code"] == "invalid_id"
    assert by[(6, "student_name")]["code"] == "required_missing"
    assert by[(7, "student_email")]["column"] == 6 and by[(7, "cgpa")]["source_column"] == "CGPA"
    assert by[(8, "student_id")]["code"] == "already_exists"
    # nothing is written by a validation job
    assert "STU20269101" not in student_ids(ic)


def test_issue_filters_and_row_lookup(ic):
    rows = [["STU20269201", "A", "CSE", "99", "A", "2025", "", ""], ["STU20269202", "B", "CSE", "2", "A", "2025", "", ""]]
    uid = upload(ic, make_csv(rows)).json()["data"]["upload_id"]
    job = run_job(ic, "validate", uid, full_mapping(), "insert_only")
    jid = job["job_id"]
    assert ic.get(f"/api/imports/jobs/{jid}/issues?code=required_missing").json()["meta"]["total"] == 0
    by_row = ic.get(f"/api/imports/jobs/{jid}/issues/by-row?first_row=2&last_row=2").json()["data"]
    assert [i["field"] for i in by_row] == ["year_of_study"]


def test_error_report_is_csv_and_neutralises_formulas(ic):
    rows = [["STU20269301", "=HYPERLINK(\"http://evil\")", "CSE", "99", "A", "2025", "", ""]]
    uid = upload(ic, make_csv(rows)).json()["data"]["upload_id"]
    job = run_job(ic, "validate", uid, full_mapping(), "insert_only")
    res = ic.get(f"/api/imports/jobs/{job['job_id']}/errors.csv")
    assert res.status_code == 200 and "attachment" in res.headers["content-disposition"]
    parsed = list(csv.DictReader(io.StringIO(res.text)))
    assert parsed and parsed[0]["spreadsheet_row"] == "2" and parsed[0]["description"]
    assert not any(cell.startswith("=") for r in parsed for cell in r.values())


# ---------------------------------------------------------------- import modes
def test_insert_only_adds_new_and_skips_existing_without_overwriting(ic):
    existing = sorted(student_ids(ic))[0]
    before = ic.get(f"/api/students/{existing}").json()["data"]["personal"]["student_name"]
    before_count = len(student_ids(ic))
    rows = [["STU20269401", "New One", "Computer Science and Engineering", "1", "A", "2026", "n1@x.edu", "7.2"],
            [existing, "Should Not Overwrite", "CSE", "1", "A", "2026", "", ""]]
    uid = upload(ic, make_csv(rows)).json()["data"]["upload_id"]
    job = run_job(ic, "import", uid, full_mapping(), "insert_only")
    assert job["status"] == "completed"
    assert (job["result"]["inserted"], job["result"]["updated"], job["result"]["skipped"]) == (1, 0, 1)
    assert ic.get(f"/api/students/{existing}").json()["data"]["personal"]["student_name"] == before
    new = ic.get("/api/students/STU20269401").json()["data"]
    assert new["personal"]["student_name"] == "New One" and new["academics"]["cgpa"] == 7.2
    assert len(student_ids(ic)) <= before_count + 1


def test_insert_only_rejects_rows_when_student_id_is_blank(ic):
    rows = [["", "Gen One", "CSE", "1", "A", "2026", "", ""], ["", "Gen Two", "CSE", "1", "A", "2026", "", ""]]
    uid = upload(ic, make_csv(rows)).json()["data"]["upload_id"]
    before = student_ids(ic)
    job = run_job(ic, "import", uid, full_mapping(), "insert_only")
    assert job["result"]["inserted"] == 0 and job["result"]["generated_ids"] == 0
    assert job["result"]["invalid_rows"] == 2
    assert student_ids(ic) == before
    issues = ic.get(f"/api/imports/jobs/{job['job_id']}/issues").json()["data"]
    assert {i["code"] for i in issues} == {"required_missing"}


def test_update_existing_changes_only_provided_cells(ic):
    sid = sorted(student_ids(ic))[0]
    before = ic.get(f"/api/students/{sid}").json()["data"]
    header = ["Roll No", "Name", "CGPA"]
    rows = [[sid, "", "9.1"], ["STU29999999", "Ghost", "5"]]
    uid = upload(ic, make_csv(rows, header)).json()["data"]["upload_id"]
    mapping = {"student_id": 0, "student_name": 1, "cgpa": 2}
    job = run_job(ic, "import", uid, mapping, "update_existing")
    assert job["result"]["updated"] == 1 and job["result"]["inserted"] == 0
    after = ic.get(f"/api/students/{sid}").json()["data"]
    assert after["academics"]["cgpa"] == 9.1
    assert after["personal"]["student_name"] == before["personal"]["student_name"]    # blank cell left unchanged
    assert "STU29999999" not in student_ids(ic)                                        # never created
    issues = ic.get(f"/api/imports/jobs/{job['job_id']}/issues").json()["data"]
    assert [(i["row"], i["code"]) for i in issues] == [(3, "not_found")]


def test_insert_or_update_does_both(ic):
    sid = sorted(student_ids(ic))[1]
    rows = [[sid, "Renamed Student", "CSE", "3", "B", "2024", "", "6.6"],
            ["STU20269501", "Brand New", "CSE", "1", "A", "2026", "", "7.7"],
            ["", "No Id", "CSE", "1", "A", "2026", "", ""]]
    uid = upload(ic, make_csv(rows)).json()["data"]["upload_id"]
    job = run_job(ic, "import", uid, full_mapping(), "insert_or_update")
    assert (job["result"]["inserted"], job["result"]["updated"]) == (1, 1)         # row 4 lacks the identifier
    assert ic.get(f"/api/students/{sid}").json()["data"]["personal"]["student_name"] == "Renamed Student"
    assert "STU20269501" in student_ids(ic)
    codes = {i["code"] for i in ic.get(f"/api/imports/jobs/{job['job_id']}/issues").json()["data"]}
    assert codes == {"missing_id"}


def test_import_revalidates_on_the_server_and_ignores_bad_rows(ic):
    rows = [["STU20269601", "Good", "CSE", "1", "A", "2026", "", "8"], ["STU20269602", "Bad", "CSE", "1", "A", "2026", "", "not-a-number"]]
    uid = upload(ic, make_csv(rows)).json()["data"]["upload_id"]
    job = run_job(ic, "import", uid, full_mapping(), "insert_only")       # no prior validate call
    assert (job["result"]["inserted"], job["result"]["invalid_rows"]) == (1, 1)
    ids = student_ids(ic)
    assert "STU20269601" in ids and "STU20269602" not in ids


def test_existing_students_endpoints_still_work_after_import(ic):
    before = ic.get("/api/dashboard/summary").json()["data"]
    uid = upload(ic, make_csv([["STU20269701", "Dash", "CSE", "1", "A", "2026", "", ""]])).json()["data"]["upload_id"]
    run_job(ic, "import", uid, full_mapping(), "insert_only")
    after = ic.get("/api/dashboard/summary").json()["data"]
    assert after != before                       # analytics reloaded with the new student
    assert ic.get("/api/health").status_code == 200


# ---------------------------------------------------------------- large files, cancellation, rollback
def test_large_file_is_processed_in_bounded_batches(ic, monkeypatch):
    calls = []
    original = import_service.validate_rows

    def spy(parsed, mapping, mode, existing, progress=None, should_cancel=None):
        return original(parsed, mapping, mode, existing, lambda d, t: (calls.append(d), progress and progress(d, t)), should_cancel)

    monkeypatch.setattr(import_service, "validate_rows", spy)
    rows = [[f"STU{30000000 + i}", f"Bulk {i}", "CSE", "1", "A", "2026", f"b{i}@x.edu", "7.0"] for i in range(2600)]
    uid = upload(ic, make_csv(rows)).json()["data"]["upload_id"]
    job = run_job(ic, "import", uid, full_mapping(), "insert_only")
    assert job["status"] == "completed" and job["result"]["inserted"] == 2600 and job["percent"] == 100
    assert calls == [500, 1000, 1500, 2000, 2500, 2600]
    assert len(student_ids(ic)) > 0 and ic.get("/api/students?search=Bulk 2599").json()["meta"]["total"] == 1


def test_row_limit_is_enforced(ic, monkeypatch):
    monkeypatch.setattr(import_service, "MAX_ROWS", 3)
    res = upload(ic, make_csv([[f"STU4000000{i}", "N", "CSE", "1", "A", "2026", "", ""] for i in range(5)]))
    assert res.status_code == 413


def test_cancelled_job_writes_nothing(ic):
    mgr = ic.app.state.import_manager
    uid = upload(ic, make_csv([["STU20269801", "Never", "CSE", "1", "A", "2026", "", ""]])).json()["data"]["upload_id"]
    upload_obj = mgr.get_upload(uid, "test-admin")
    job = import_service.Job("j1", uid, "import", "test-admin", "insert_only", "f.csv", upload_obj.headers, cancel_requested=True)
    mgr.jobs["j1"] = job
    mgr._run(job, upload_obj, full_mapping(), ic.app.state.service)
    assert job.status == "cancelled" and "STU20269801" not in student_ids(ic)


def test_cancel_endpoint_and_unknown_jobs(ic):
    assert ic.post("/api/imports/jobs/nope/cancel").status_code == 404
    assert ic.get("/api/imports/jobs/nope").status_code == 404
    uid = upload(ic, make_csv([["STU20269802", "C", "CSE", "1", "A", "2026", "", ""]])).json()["data"]["upload_id"]
    job = run_job(ic, "import", uid, full_mapping(), "insert_only")
    res = ic.post(f"/api/imports/jobs/{job['job_id']}/cancel")
    assert res.status_code == 200 and res.json()["data"]["status"] == "completed"       # too late: remains completed


def test_failed_commit_rolls_back_every_file(ic, monkeypatch):
    data_dir = ic.data_dir
    snapshot = {p.name: p.read_bytes() for p in data_dir.glob("*.csv")}
    real_replace, count = import_service.os.replace, {"n": 0}

    def flaky(src, dst):
        count["n"] += 1
        if count["n"] == 3:
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(import_service.os, "replace", flaky)
    uid = upload(ic, make_csv([["STU20269901", "Rollback", "CSE", "1", "A", "2026", "", "7"]])).json()["data"]["upload_id"]
    job = run_job(ic, "import", uid, full_mapping(), "insert_only")
    assert job["status"] == "failed" and "No changes were applied" in job["error"]
    assert {p.name: p.read_bytes() for p in data_dir.glob("*.csv")} == snapshot
    assert "STU20269901" not in student_ids(ic)
    assert not list(data_dir.glob("*.tmp"))


def test_uploads_are_private_to_their_owner(ic):
    uid = upload(ic, make_csv([["", "A", "CSE", "1", "A", "2026", "", ""]])).json()["data"]["upload_id"]
    ic.app.dependency_overrides[get_current_user] = lambda: {"username": "other-admin", "role": "college_admin"}
    assert ic.get(f"/api/imports/uploads/{uid}/rows").status_code == 404
    assert ic.post(f"/api/imports/uploads/{uid}/validate", json={"mapping": full_mapping(), "mode": "insert_only"}).status_code == 404


def test_cancellation_is_refused_once_the_final_save_has_started(ic, monkeypatch):
    """can_cancel flips to False at the point of no return, so the UI never offers a cancel that cannot work."""
    seen = {}
    real = import_service.commit_plans

    def spy(service, plans, dept, should_cancel=None, on_point_of_no_return=None):
        def wrapped():
            on_point_of_no_return()
            seen["can_cancel_after_lock"] = job_ref["job"].can_cancel
        return real(service, plans, dept, should_cancel, wrapped)

    job_ref = {}
    original_submit = import_service.ImportManager.submit

    def submit(self, *a, **k):
        job = original_submit(self, *a, **k)
        job_ref["job"] = job
        return job

    monkeypatch.setattr(import_service.ImportManager, "submit", submit)
    monkeypatch.setattr(import_service, "commit_plans", spy)
    uid = upload(ic, make_csv([["STU20269911", "Lock", "CSE", "1", "A", "2026", "", ""]])).json()["data"]["upload_id"]
    job = run_job(ic, "import", uid, full_mapping(), "insert_only")
    assert job["status"] == "completed" and seen["can_cancel_after_lock"] is False
