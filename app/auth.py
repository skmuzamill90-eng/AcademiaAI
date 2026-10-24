"""JWT authentication with a JSON file-backed user store (no database required)."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from contextlib import contextmanager
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

ROLES = {"super_admin", "college_admin", "student"}
DEFAULT_SECRET_WARNING = "development-only-insecure-secret-change-before-deployment"
SECRET_KEY = os.getenv("AUTH_SECRET_KEY", DEFAULT_SECRET_WARNING)
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = max(5, min(int(os.getenv("ACCESS_TOKEN_MINUTES", "30")), 60))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
USERS_FILE = Path(os.getenv("AUTH_USERS_FILE", str(PROJECT_ROOT / "data" / "users.json")))
if not USERS_FILE.is_absolute():
    USERS_FILE = PROJECT_ROOT / USERS_FILE
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
_users_lock = threading.RLock()
logger = logging.getLogger("smart_campus.auth")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_store() -> dict:
    if not USERS_FILE.exists():
        return {"schema_version": 2, "users": {}, "institutions": {}, "audit": []}
    with USERS_FILE.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError("Invalid authentication store")
    if data.get("schema_version") == 2:
        return data
    # Preserve every legacy row; never implicitly promote or assign ownership.
    return {"schema_version": 2, "users": data, "institutions": {}, "audit": []}


def write_store(data):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(dir=USERS_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(path, USERS_FILE)
        USERS_FILE.chmod(0o600)
    finally:
        if os.path.exists(path):
            os.unlink(path)


@contextmanager
def transaction():
    with _users_lock:
        data = read_store()
        yield data
        write_store(data)


def _read_users():
    return read_store()["users"]


def _write_users(users):
    with transaction() as data:
        data["users"] = users


def audit(data, actor, action, target):
    data["audit"].append({"at": now_iso(), "actor": actor, "action": action, "target": target})


def init_auth_store():
    # Provisioning is deliberately CLI-only, never on startup.
    with transaction() as data:
        pass


def public_user(row):
    return {key: row.get(key) for key in ("username", "role", "institution_id", "student_id",
            "active", "must_change_password", "created_at", "last_login_at")}


def new_user(username, password, role, institution_id=None, student_id=None, must_change=False):
    if not 3 <= len(username) <= 64 or not username.isascii() or not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Username must contain 3-64 ASCII letters, numbers, underscores or hyphens.")
    if not 12 <= len(password) <= 256 or role not in ROLES:
        raise ValueError("Invalid role or password length (12-256 required).")
    if role != "super_admin" and not institution_id:
        raise ValueError("Institution ownership is required.")
    if role == "student" and not student_id:
        raise ValueError("Student mapping is required.")
    return {"username": username, "password_hash": _hash_password(password), "role": role,
            "institution_id": institution_id, "student_id": student_id, "active": True,
            "must_change_password": must_change, "version": 1, "created_at": now_iso()}


def create_user(username, password, role, institution_id=None, student_id=None):
    with transaction() as data:
        if username in data["users"]:
            raise ValueError("That username already exists.")
        if role != "super_admin" and institution_id not in data["institutions"]:
            raise ValueError("Unknown institution.")
        row = new_user(username, password, role, institution_id, student_id)
        data["users"][username] = row
    return public_user(row)


def allowed_identity(row, data):
    if not row or not row.get("active") or row.get("role") not in ROLES:
        return False
    if row["role"] == "super_admin":
        return row.get("institution_id") is None
    institution = data["institutions"].get(row.get("institution_id"))
    return bool(institution and institution["status"] == "active" and
                (row["role"] != "student" or row.get("student_id")))


def authenticate_user(username, password, expected_role: str | tuple[str, ...] | None = None):
    if len(password) > 256 or len(username) > 64:
        return None
    with transaction() as data:
        row = data["users"].get(username.strip())
        valid = _verify_password(password, row.get("password_hash", "")) if row else False
        if row is None:
            _hash_password(password)
        expected_roles = (expected_role,) if isinstance(expected_role, str) else expected_role
        if not valid or not allowed_identity(row, data) or (expected_roles and row["role"] not in expected_roles):
            audit(data, "anonymous", "login_failed", "authentication")
            return None
        row["last_login_at"] = now_iso()
        audit(data, row["username"], "login", row["username"])
        return public_user(row)


def setup_token(row):
    token = secrets.token_urlsafe(32)
    row["setup_hash"] = hashlib.sha256(token.encode()).hexdigest()
    row["setup_expires"] = time.time() + 3600
    row["must_change_password"] = True
    row["version"] += 1
    return token


def revoke(row):
    row["version"] += 1
    row.pop("setup_hash", None)
    row.pop("setup_expires", None)


# Bounded per-IP and per-username windows. Single-process runtime is enforced.
_attempts = {}
def throttle(request, username=""):
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _users_lock:
        for key in list(_attempts):
            if now - _attempts[key][0] >= 900:
                del _attempts[key]
        keys = [("ip:" + ip, 50), ("user:" + username[:64].lower(), 10)]
        if len(_attempts) > 10000:
            raise HTTPException(429, "Too many authentication attempts. Try again later.")
        for key, limit in keys:
            start, count = _attempts.get(key, (now, 0))
            if count >= limit:
                raise HTTPException(429, "Too many authentication attempts. Try again later.")
        for key, _ in keys:
            start, count = _attempts.get(key, (now, 0))
            _attempts[key] = (start, count + 1)


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 600_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def issue_token(user: dict) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user["username"], "role": user["role"],
               "iat": int(now.timestamp()), "exp": int(expires.timestamp()),
               "ver": _read_users()[user["username"]]["version"]}
    head = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{head}.{body}".encode("ascii")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{head}.{body}.{_b64encode(signature)}", ACCESS_TOKEN_MINUTES * 60


def get_current_user(token: str | None = Depends(oauth2_scheme)) -> dict:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"message": "Authentication required. Sign in to continue."},
        headers={"WWW-Authenticate": "Bearer"})
    if not token:
        raise unauthorized
    try:
        head, body, signature = token.split(".", 2)
        header = json.loads(_b64decode(head))
        payload = json.loads(_b64decode(body))
        if not isinstance(header, dict) or not isinstance(payload, dict) or header.get("alg") != "HS256":
            raise unauthorized
        expected = hmac.new(SECRET_KEY.encode("utf-8"), f"{head}.{body}".encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature)):
            raise unauthorized
        username, role, expires = payload.get("sub"), payload.get("role"), payload.get("exp")
        if not username or role not in ROLES or not isinstance(expires, (int, float)) or expires <= datetime.now(timezone.utc).timestamp():
            raise unauthorized
    except (ValueError, TypeError, KeyError, AttributeError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
        raise unauthorized
    with _users_lock:
        row = _read_users().get(username)
    if not allowed_identity(row, read_store()) or row.get("role") != role or payload.get("ver") != row.get("version"):
        raise unauthorized
    return public_user(row)


def require_roles(*allowed_roles: str) -> Callable:
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user.get("must_change_password"):
            raise HTTPException(403, "Set a new password before using this account.")
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail={"message": "Your account does not have permission for this action."})
        return user
    return dependency
