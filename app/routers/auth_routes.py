"""Extend the existing bearer authentication flow with setup and revocation."""
import hashlib
import time
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, ConfigDict
from ..auth import (authenticate_user, issue_token, get_current_user, transaction, audit,
                    _hash_password, _verify_password, revoke, throttle, allowed_identity)
from ..utils import success

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=12, max_length=256)

class PasswordSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=40, max_length=128)
    new_password: str = Field(min_length=12, max_length=256)

@router.post("/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(),
          login_type: str | None = Form(default=None)):
    throttle(request, form.username)
    if login_type not in (None, "admin", "campus", "student"):
        raise HTTPException(422, "Invalid login type.")
    expected_role = {"admin": "super_admin", "campus": "college_admin", "student": "student"}.get(login_type)
    user = authenticate_user(form.username, form.password, expected_role)
    if not user:
        raise HTTPException(401, "Incorrect username or password.")
    token, expires_in = issue_token(user)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in, "user": user}

@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return success(user)

@router.post("/logout")
def logout(user: dict = Depends(get_current_user)):
    with transaction() as data:
        revoke(data["users"][user["username"]])
        audit(data, user["username"], "logout_all_sessions", user["username"])
    return success({"logged_out": True})

@router.post("/password")
def change_password(body: PasswordChange, request: Request, user: dict = Depends(get_current_user)):
    throttle(request, user["username"])
    with transaction() as data:
        row = data["users"][user["username"]]
        if not _verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(400, "Current password is incorrect.")
        if body.current_password == body.new_password:
            raise HTTPException(422, "Choose a different password.")
        row["password_hash"] = _hash_password(body.new_password)
        row["must_change_password"] = False
        revoke(row)
        audit(data, user["username"], "password_changed", user["username"])
    return success({"sign_in_required": True})

@router.post("/setup")
def setup(body: PasswordSetup, request: Request):
    throttle(request, "password-setup")
    digest = hashlib.sha256(body.token.encode()).hexdigest()
    with transaction() as data:
        row = next((u for u in data["users"].values() if u.get("setup_hash") == digest), None)
        if not row or row.get("setup_expires", 0) < time.time() or not allowed_identity(row, data):
            raise HTTPException(400, "Setup link is invalid, expired, or unavailable.")
        row["password_hash"] = _hash_password(body.new_password)
        row["must_change_password"] = False
        revoke(row)
        audit(data, row["username"], "password_setup_completed", row["username"])
    return success({"sign_in_required": True})

@router.post("/users", status_code=403)
def legacy_user_create(_: dict = Depends(get_current_user)):
    raise HTTPException(403, "Use institution provisioning or student account management.")
