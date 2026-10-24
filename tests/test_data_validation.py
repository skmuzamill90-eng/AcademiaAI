"""CSV schema validation tests for the workbook-derived working files."""
import pandas as pd

from tests.conftest import working_student_count
import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.data_service import DataService, DataValidationError
from app.main import create_app


def edit_csv(data_dir, filename, fn):
    path = data_dir / filename
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    fn(df).to_csv(path, index=False)


def test_working_csvs_load_cleanly(data_dir):
    service = DataService(data_dir).load()
    assert len(service.students) == working_student_count()
    assert service.warnings == []
    assert service.students.index.is_unique
    assert len(service.interventions) == 0
    assert service.students.index[0] == "STU20260001"
    assert "student_email" in service.students.columns


def test_missing_required_column_is_rejected(data_dir):
    edit_csv(data_dir, "academics.csv", lambda frame: frame.drop(columns=["cgpa"]))
    with pytest.raises(DataValidationError) as error:
        DataService(data_dir).load()
    assert any("academics" in item and "cgpa" in item for item in error.value.errors)


def test_missing_file_is_rejected(data_dir):
    (data_dir / "lms.csv").unlink()
    with pytest.raises(DataValidationError) as error:
        DataService(data_dir).load()
    assert any("lms.csv" in item and "not found" in item for item in error.value.errors)


def test_duplicate_student_ids_are_rejected(data_dir):
    edit_csv(data_dir, "skills.csv", lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True))
    with pytest.raises(DataValidationError) as error:
        DataService(data_dir).load()
    assert any("skills" in item and "duplicate student_id" in item for item in error.value.errors)


def test_api_reports_unavailable_for_invalid_tenant_dataset(data_dir):
    from uuid import uuid4
    import shutil
    iid = str(uuid4())
    tenant = data_dir / 'tenants' / iid
    shutil.copytree(data_dir, tenant, ignore=shutil.ignore_patterns('tenants'))
    edit_csv(tenant, "academics.csv", lambda frame: frame.drop(columns=["backlogs"]))
    app = create_app(str(data_dir))
    app.dependency_overrides[get_current_user] = lambda: {"username": "test-admin", "role": "college_admin", "institution_id": iid}
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200  # liveness exposes no tenant data
        assert client.get("/api/students").status_code == 503
