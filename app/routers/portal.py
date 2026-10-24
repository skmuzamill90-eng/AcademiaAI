"""Student self-service and institution-bound student provisioning."""
import secrets
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from ..auth import (get_current_user, require_roles, read_store, transaction, new_user,
                    public_user, audit, setup_token, revoke)
from ..deps import get_service, get_tenant_service, not_found
from ..data_service import DataService, NotFoundError
from .. import profile_service
from ..utils import success
from .platform import AccountUpdate, InstitutionUpdate

router = APIRouter(prefix="/api", tags=["Institution portal"])
College = Depends(require_roles("college_admin"))
Student = Depends(require_roles("student"))

class StudentAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    student_id: str = Field(min_length=1, max_length=32)

@router.get("/student/me")
def own_profile(user: dict = Student, service: DataService = Depends(get_tenant_service)):
    try:
        profile = profile_service.build_profile(service, user["student_id"])
    except NotFoundError as exc:
        raise not_found(exc)
    # Staff intervention notes and faculty feedback are private even from the subject.
    fields = ("student_id", "personal", "academics", "attendance", "lms", "engagement",
              "skills", "placement", "success_score", "risk", "data_quality")
    result = {k: profile[k] for k in fields}
    result["success_score"].pop("details_endpoint", None)
    result["feedback"] = {k: v for k, v in profile["feedback"].items() if k != "faculty_feedback_1_to_5"}
    result["interventions"] = [
        {key: intervention[key] for key in ("intervention_id", "intervention_type", "assigned_date", "status")}
        for intervention in profile["interventions"]
    ]
    # Recommendations use only intervention identifiers and statuses, never staff-only notes.
    from ..recommendation_service import build_recommendations
    result["recommendations"] = build_recommendations(
        service.student_row(user["student_id"]), service.open_interventions_for(user["student_id"]))
    institution = read_store()["institutions"][user["institution_id"]]
    result["institution"] = {"id": institution["id"], "name": institution["name"]}
    return success(result)

@router.get("/institution")
def institution(user: dict = College):
    return success(read_store()["institutions"][user["institution_id"]])

class InstitutionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=160)
    contact_email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

@router.patch("/institution")
def edit_institution(body: InstitutionProfile, user: dict = College):
    with transaction() as data:
        row = data["institutions"][user["institution_id"]]
        row.update(body.model_dump())
        audit(data, user["username"], "institution_profile_updated", row["id"])
    return success(row)

@router.get("/institution/accounts")
def accounts(user: dict = College, search: str = Query("", max_length=64),
             limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    rows = [public_user(u) for u in read_store()["users"].values()
            if u.get("institution_id") == user["institution_id"] and u["role"] == "student"
            and search.lower() in (u["username"] + u["student_id"]).lower()]
    return success(rows[offset:offset+limit], {"total": len(rows), "has_more": offset+limit < len(rows)})

@router.post("/institution/accounts", status_code=201)
def provision_student(body: StudentAccount, user: dict = College, service: DataService = Depends(get_service)):
    sid = body.student_id.upper()
    if not service.has_student(sid):
        raise HTTPException(404, "Student not found in your institution.")
    with transaction() as data:
        if body.username in data["users"] or any(u.get("institution_id") == user["institution_id"] and u.get("student_id") == sid for u in data["users"].values()):
            raise HTTPException(409, "An account already exists for this username or student.")
        row = new_user(body.username, secrets.token_urlsafe(32), "student", user["institution_id"], sid, True)
        data["users"][body.username] = row
        audit(data, user["username"], "student_account_created", body.username)
    return success(public_user(row))


def scoped_account(data, username, user):
    row = data["users"].get(username)
    if not row or row.get("institution_id") != user["institution_id"] or row["role"] != "student":
        raise HTTPException(404, "Student account not found.")
    return row

@router.patch("/institution/accounts/{username}")
def account_access(username: str, body: AccountUpdate, user: dict = College):
    with transaction() as data:
        row = scoped_account(data, username, user)
        row["active"] = body.active
        revoke(row)
        audit(data, user["username"], "student_access_updated", username)
    return success(public_user(row))

@router.post("/institution/accounts/{username}/setup")
def account_setup(username: str, user: dict = College):
    with transaction() as data:
        row = scoped_account(data, username, user)
        if not row["active"]:
            raise HTTPException(409, "Activate the account first.")
        token = setup_token(row)
        audit(data, user["username"], "student_setup_issued", username)
    return success({"setup_token": token, "expires_in": 3600, "username": username})

@router.get("/institution/health")
def institution_health(service: DataService = Depends(get_service)):
    return success({"service": "healthy", **service.health()})
