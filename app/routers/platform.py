"""Platform operations. Never returns student records, password hashes or stored tokens."""
import secrets
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from ..auth import (require_roles, transaction, read_store, audit, new_user, public_user,
                    setup_token, revoke, now_iso)
from ..utils import success

router = APIRouter(prefix="/api/platform", tags=["Platform"], dependencies=[Depends(require_roles("super_admin"))])
Admin = Depends(require_roles("super_admin"))
Status = Literal["pending", "active", "suspended", "deactivated"]

class InstitutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=160)
    contact_email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    admin_username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    status: Literal["pending", "active"] = "pending"

class InstitutionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=2, max_length=160)
    contact_email: str | None = Field(None, min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    status: Status | None = None

class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool


def institution_view(row, data, request):
    users = [u for u in data["users"].values() if u.get("institution_id") == row["id"]]
    try:
        service = request.app.state.tenants.get(row["id"])
        count, interventions = len(service.students), len(service.interventions)
        available = True
    except HTTPException:
        count, interventions, available = None, None, False
    return {**row, "student_count": count, "intervention_count": interventions,
            "data_available": available, "student_accounts": sum(u["role"] == "student" for u in users),
            "administrators": [public_user(u) for u in users if u["role"] == "college_admin"]}

@router.get("/overview")
def overview(request: Request):
    data = read_store()
    institutions = list(data["institutions"].values())
    return success({"institutions": len(institutions),
        "statuses": {s: sum(i["status"] == s for i in institutions) for s in ("pending", "active", "suspended", "deactivated")},
        "student_accounts": sum(u.get("role") == "student" for u in data["users"].values())})

@router.get("/institutions")
def institutions(request: Request, search: str = Query("", max_length=160), status: Status | None = None,
                 sort: Literal["name", "created_at", "status"] = "name", order: Literal["asc", "desc"] = "asc",
                 limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    data = read_store()
    rows = [r for r in data["institutions"].values() if search.lower() in r["name"].lower() and (not status or r["status"] == status)]
    rows.sort(key=lambda r: (r[sort].lower(), r["id"]), reverse=order == "desc")
    return success([institution_view(r, data, request) for r in rows[offset:offset+limit]],
                   {"total": len(rows), "has_more": offset + limit < len(rows)})

@router.post("/institutions", status_code=201)
def create_institution(body: InstitutionCreate, request: Request, actor: dict = Admin):
    with transaction() as data:
        if body.admin_username in data["users"]:
            raise HTTPException(409, "Username already exists.")
        iid = str(uuid4())
        row = {"id": iid, "name": body.name.strip(), "contact_email": body.contact_email,
               "status": body.status, "created_at": now_iso()}
        account = new_user(body.admin_username, secrets.token_urlsafe(32), "college_admin", iid, must_change=True)
        # Directory must exist and load successfully before committing identity ownership.
        request.app.state.tenants.initialize(iid)
        data["institutions"][iid] = row
        data["users"][body.admin_username] = account
        audit(data, actor["username"], "institution_created", iid)
    return success(row)

@router.get("/institutions/{iid}")
def detail(iid: str, request: Request):
    data = read_store()
    row = data["institutions"].get(iid)
    if not row:
        raise HTTPException(404, "Institution not found.")
    return success(institution_view(row, data, request))

@router.patch("/institutions/{iid}")
def edit(iid: str, body: InstitutionUpdate, actor: dict = Admin):
    with transaction() as data:
        row = data["institutions"].get(iid)
        if not row:
            raise HTTPException(404, "Institution not found.")
        values = body.model_dump(exclude_none=True)
        row.update(values)
        if "status" in values:
            for u in data["users"].values():
                if u.get("institution_id") == iid:
                    revoke(u)
        audit(data, actor["username"], "institution_updated:" + ",".join(sorted(values)), iid)
    return success(row)

@router.post("/institutions/{iid}/administrator/setup")
def admin_setup(iid: str, actor: dict = Admin):
    with transaction() as data:
        if data["institutions"].get(iid, {}).get("status") != "active":
            raise HTTPException(409, "Activate the institution before issuing a setup link.")
        row = next((u for u in data["users"].values() if u.get("institution_id") == iid and u["role"] == "college_admin"), None)
        if not row or not row["active"]:
            raise HTTPException(404, "Active administrator not found.")
        token = setup_token(row)
        audit(data, actor["username"], "administrator_setup_issued", iid)
    # Returned exactly once to the authorized provisioning operator, never in lists/logs.
    return success({"setup_token": token, "expires_in": 3600, "username": row["username"]})

@router.patch("/institutions/{iid}/administrator")
def admin_access(iid: str, body: AccountUpdate, actor: dict = Admin):
    with transaction() as data:
        row = next((u for u in data["users"].values() if u.get("institution_id") == iid and u["role"] == "college_admin"), None)
        if not row:
            raise HTTPException(404, "Administrator not found.")
        row["active"] = body.active
        revoke(row)
        audit(data, actor["username"], "administrator_access_updated", iid)
    return success(public_user(row))

@router.get("/audit")
def audit_log(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    rows = list(reversed(read_store()["audit"]))
    return success(rows[offset:offset+limit], {"total": len(rows), "has_more": offset+limit < len(rows)})
