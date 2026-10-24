"""
Application entry point.

Run with:   uvicorn app.main:app --reload
Docs at:    http://127.0.0.1:8000/docs

All responses use one of two shapes:
  success: {"status": "success", "data": ..., "meta": {...}}
  error:   {"status": "error", "error": {"code": 404, "type": "not_found", "message": "...", "details": ...}}
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import CORS_ORIGINS, get_data_dir
from .tenancy import TenantRegistry, acquire_process_lock
from . import auth
from .auth import init_auth_store, SECRET_KEY, DEFAULT_SECRET_WARNING
from .data_service import DataService, DataValidationError, PersistenceError
from .routers import platform, portal, analytics, dashboard, interventions, students, system, auth_routes, ai_chat, imports, predictions
from .utils import clean

logger = logging.getLogger("smart_campus")

ERROR_TYPES = {401: "unauthenticated", 403: "forbidden", 429: "rate_limited", 400: "bad_request", 404: "not_found", 405: "method_not_allowed", 422: "validation_error",
               500: "internal_error", 503: "service_unavailable"}


def error_response(status_code: int, message: str, details=None, error_type: str | None = None):
    body = {"status": "error",
            "error": {"code": status_code, "type": error_type or ERROR_TYPES.get(status_code, "error"),
                      "message": message, "details": details}}
    return JSONResponse(status_code=status_code, content=clean(body))


def _production_secret_is_usable(secret: str) -> bool:
    normalized = secret.strip().lower()
    return (
        len(secret) >= 32
        and secret != DEFAULT_SECRET_WARNING
        and not normalized.startswith(("replace_", "your_", "change_me"))
    )


def create_app(data_dir: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if os.getenv("ENVIRONMENT", "development").lower() == "production" and not _production_secret_is_usable(SECRET_KEY):
            raise RuntimeError("AUTH_SECRET_KEY must be set to a strong random value in production.")
        if SECRET_KEY == DEFAULT_SECRET_WARNING:
            logger.warning("Set AUTH_SECRET_KEY before deployment.")
        process_lock = acquire_process_lock(auth.USERS_FILE.with_suffix(".lock"))
        data_lock = None
        try:
            data_lock = acquire_process_lock(get_data_dir(data_dir) / ".tenant-writer.lock")
            init_auth_store()
            app.state.tenants = TenantRegistry(get_data_dir(data_dir))
            yield
        finally:
            if data_lock:
                data_lock.close()
            process_lock.close()

    app = FastAPI(
        title="Smart Campus Analytics API",
        version="1.0.0",
        description=("Prototype backend: unified student profiles, a transparent success score, "
                     "rule-based support indicators and dashboard analytics, computed from CSV files. "
                     "Uses a local JSON user store and CSV persistence. Protected API routes require JWT authentication."),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            message = detail.get("message", "Request failed")
            details = {k: v for k, v in detail.items() if k != "message"} or None
        else:
            message, details = str(detail), None
        return error_response(exc.status_code, message, details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"] if p not in ("query", "path", "body")),
                    "message": e["msg"]} for e in exc.errors()]
        return error_response(422, "The request is invalid. Check the 'details' list.", details)

    @app.exception_handler(PersistenceError)
    async def persistence_error(_: Request, exc: PersistenceError):
        return error_response(500, str(exc), error_type="persistence_error")

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        logger.exception("Unhandled error")  # full traceback goes to the server log only
        return error_response(500, "Something went wrong on the server. Please try again later.")

    for router in (system.router, auth_routes.router, dashboard.router, students.router, analytics.router,
                   interventions.router, ai_chat.router, imports.router, platform.router, portal.router,
                   predictions.router):
        app.include_router(router)
    return app


app = create_app()
