from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from app.auth import get_current_user
from app.chat_query import query_students
from app.data_service import DataService
from app.deps import get_service
from app.import_service import RowPlan, commit_plans
from app.tenancy import TenantRegistry


def _query(client, question: str):
    response = client.post("/api/ai/chat", json={"message": question})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_top_five_civil_students_by_cgpa_without_groq(client, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    service = client.app.state.service
    expected = service.students[service.students["department"] == "Civil Engineering"].dropna(
        subset=["cgpa"]
    ).sort_values(["cgpa", "student_id"], ascending=[False, True]).head(5)

    data = _query(client, "Top 5 Civil students by CGPA")

    assert data["model"] == "csv-direct"
    assert "| Student | Department | cgpa |" in data["answer"]
    for _, row in expected.iterrows():
        assert str(row["student_name"]) in data["answer"]
        assert f"{row['cgpa']:.2f}".rstrip("0").rstrip(".") in data["answer"]


def test_attendance_filter_and_no_matching_students(client):
    service = client.app.state.service
    expected_count = int((pd.to_numeric(service.students["overall_attendance_pct"], errors="coerce") < 75).sum())

    data = _query(client, "How many students have attendance below 75%?")
    assert data["answer"] == f"Matching students: {expected_count}."

    empty = _query(client, "List students with attendance below 0%")
    assert empty["answer"] == "No matching students were found."


def test_average_cgpa_by_department(client):
    service = client.app.state.service
    data = _query(client, "Average CGPA by department")
    civil_average = pd.to_numeric(
        service.students.loc[service.students["department"] == "Civil Engineering", "cgpa"],
        errors="coerce",
    ).mean()

    assert "| department | Average cgpa |" in data["answer"]
    assert f"| Civil Engineering | {civil_average:.2f} |" in data["answer"]


def test_placement_status_counts(client):
    data = _query(client, "Show placement status distribution")
    assert "| placement_status | Students |" in data["answer"]
    assert "Eligible" in data["answer"]
    assert "Placed" in data["answer"]


def test_top_coding_rank_and_department_comparison(client):
    service = client.app.state.service
    top = query_students(service, "Top 5 students by coding score")
    compare = query_students(service, "Compare Civil and CSE average CGPA")

    expected_top = service.students.dropna(subset=["coding_score"]).sort_values(
        ["coding_score", "student_id"], ascending=[False, True]
    ).head(5)
    assert top is not None
    assert all(str(row["student_name"]) in top["answer"] for _, row in expected_top.iterrows())
    assert compare is not None
    assert "Civil Engineering" in compare["answer"]
    assert "Computer Science and Engineering" in compare["answer"]


def test_named_student_data_query_ignores_me_in_department_initials_and_returns_profile(client):
    service = client.app.state.service
    sid = service.students.index[0]
    service.students.loc[sid, "student_name"] = "Pavan Verma"
    service.students.loc[sid, "department"] = "Mechanical Engineering"

    result = query_students(service, "can you give me this student Pavan Verma data")

    assert result is not None
    assert result["context_scope"] == "Filtered institution student records"
    assert "No matching students were found." not in result["answer"]
    assert "Pavan Verma" in result["answer"]
    assert "Mechanical Engineering" in result["answer"]
    for field in ("cgpa", "overall_attendance_pct", "placement_status", "student_id"):
        assert field in result["answer"]


def test_high_academic_or_placement_risk_uses_union(client):
    service = client.app.state.service
    expected = int((
        (service.students["academic_risk_level"] == "High")
        | (service.students["placement_risk_level"] == "High")
    ).sum())

    result = query_students(service, "How many students have high academic or placement risk?")

    assert result is not None
    assert result["answer"] == f"Matching students: {expected}."


def test_malformed_field_question_returns_local_help(client, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    data = _query(client, "Average mystery score")

    assert data["model"] == "csv-direct"
    assert "couldn't match 'mystery score'" in data["answer"]
    assert "CGPA" in data["answer"]


def test_missing_requested_field_is_reported():
    service = DataService().load()
    service.students = service.students.drop(columns=["cgpa"])

    with pytest.raises(ValueError, match="cgpa"):
        query_students(service, "Average CGPA")


def test_query_works_with_two_hundred_imported_records(data_dir):
    students = pd.read_csv(data_dir / "students.csv", dtype=str)
    keep_ids = set(students["student_id"].head(200))
    for path in data_dir.glob("*.csv"):
        frame = pd.read_csv(path, dtype=str)
        if "student_id" in frame.columns:
            frame = frame[frame["student_id"].isin(keep_ids)]
        frame.to_csv(path, index=False)

    service = DataService(data_dir).load()
    result = query_students(service, "Top 5 Civil students by CGPA")

    assert len(service.students) == 200
    assert result is not None
    assert "| Student | Department | cgpa |" in result["answer"]


def test_tenant_context_limits_chat_to_authenticated_institution(client):
    root = Path(client.data_dir)
    registry = TenantRegistry(root)
    tenant_ids = ("63f784eb-a4a2-46d7-a1b2-220e4d791875", "f786559f-c68a-4c17-870f-c5b3c90aa1e8")
    names = ("Tenant Alpha Student", "Tenant Beta Student")
    for tenant_id, name, offset in zip(tenant_ids, names, (0, 1)):
        path = registry.path(tenant_id)
        path.mkdir(parents=True)
        for source in root.glob("*.csv"):
            shutil.copy(source, path / source.name)
        student_file = path / "students.csv"
        students = pd.read_csv(student_file, dtype=str).head(offset + 1).tail(1)
        student_id = students.iloc[0]["student_id"]
        students.loc[:, "student_name"] = name
        students.to_csv(student_file, index=False)
        for dataset in path.glob("*.csv"):
            if dataset.name == "students.csv":
                continue
            frame = pd.read_csv(dataset, dtype=str)
            if "student_id" in frame.columns:
                frame = frame[frame["student_id"] == student_id]
                frame.to_csv(dataset, index=False)
        registry.services[tenant_id] = DataService(path).load()

    client.app.state.tenants = registry
    client.app.dependency_overrides.pop(get_service, None)
    client.app.dependency_overrides[get_current_user] = lambda: {
        "username": "tenant-admin", "role": "college_admin", "institution_id": tenant_ids[0],
    }
    data = _query(client, "Top 1 student by CGPA")

    assert names[0] in data["answer"]
    assert names[1] not in data["answer"]


def test_query_results_refresh_after_import(client):
    service = client.app.state.service
    previous_count = len(service.students)

    commit_plans(service, [RowPlan(
        1,
        "STU99999999",
        "insert",
        {
            "student_name": "Imported Query Check",
            "department": "Civil Engineering",
            "year_of_study": 1,
            "section": "A",
            "admission_year": 2026,
            "student_email": "imported-query-check@example.edu",
            "cgpa": 9.9,
        },
    )], service.match_department)

    assert len(service.students) == previous_count + 1
    result = query_students(service, "Top 1 Civil student by CGPA")
    assert result is not None
    assert "Imported Query Check" in result["answer"]


def test_student_role_cannot_query_ai_data(client):
    client.app.dependency_overrides[get_current_user] = lambda: {
        "username": "student-user", "role": "student", "institution_id": "tenant",
    }

    response = client.post("/api/ai/chat", json={"message": "Top 5 Civil students by CGPA"})

    assert response.status_code == 403
