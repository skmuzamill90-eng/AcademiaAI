"""FastAPI dependencies shared by all institutional routers."""
from fastapi import Depends, HTTPException, Request
from .auth import get_current_user, require_roles
from .data_service import DataService, NotFoundError


def get_tenant_service(request: Request, user: dict = Depends(get_current_user)) -> DataService:
    if user.get("must_change_password"):
        raise HTTPException(403, "Set a new password before using this account.")
    if user["role"] not in {"college_admin", "student"} or not user.get("institution_id"):
        raise HTTPException(403, "An authorized institution account is required.")
    return request.app.state.tenants.get(user["institution_id"])


def get_service(service: DataService = Depends(get_tenant_service),
                _: dict = Depends(require_roles("college_admin"))) -> DataService:
    return service


def not_found(exc: NotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))
