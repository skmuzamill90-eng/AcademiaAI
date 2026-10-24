"""Bulk student import API. Every route is administrator-only and follows the existing response envelope."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

from ..auth import require_roles
from ..deps import get_service
from ..data_service import DataService
from ..import_service import (ALLOWED_EXTENSIONS, BATCH_SIZE, MAX_ROWS, MAX_UPLOAD_BYTES, MODE_LABELS,
                              MODES, PREVIEW_ROWS, ImportError_, ImportManager, error_report_csv, field_catalogue,
                              normalise_mapping, parse_sheet, suggest_mapping, template_csv)
from ..roster_service import roster_download
from ..utils import success

router = APIRouter(prefix="/api/imports", tags=["Student import"], dependencies=[Depends(require_roles("college_admin"))])
Admin = Depends(require_roles("college_admin"))
logger = logging.getLogger("smart_campus.import")


def manager(request: Request) -> ImportManager:
    mgr = getattr(request.app.state, "import_manager", None)
    if mgr is None:
        mgr = request.app.state.import_manager = ImportManager()
    return mgr


def _fail(exc: ImportError_) -> HTTPException:
    return HTTPException(exc.status, detail={"message": exc.message})


@router.get("/config", summary="Importable fields, modes and limits")
def import_config():
    return success({
        "fields": field_catalogue(),
        "modes": [{"value": m, "label": MODE_LABELS[m]} for m in MODES],
        "limits": {"max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024), "max_rows": MAX_ROWS,
                   "batch_size": BATCH_SIZE, "extensions": list(ALLOWED_EXTENSIONS)},
        "identifier": "student_id",
    })


@router.get("/template", summary="Download the CSV import template")
def import_template():
    return Response(template_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="academia-student-import-template.csv"'})


@router.get("/roster", summary="Download this institution's latest imported roster")
def download_roster(service: DataService = Depends(get_service)):
    try:
        path, filename = roster_download(service.data_dir)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={"message": str(exc)}) from exc
    except (OSError, ValueError) as exc:
        logger.exception("Could not read the retained roster for download")
        raise HTTPException(500, detail={"message": "The saved student roster is unavailable."}) from exc
    media_type = "text/csv" if path.suffix.lower() == ".csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path, media_type=media_type, filename=filename)


@router.post("/uploads", status_code=201, summary="Upload a spreadsheet and preview it")
async def upload_file(request: Request, file: UploadFile = File(...), user: dict = Admin,
                      mgr: ImportManager = Depends(manager), service: DataService = Depends(get_service)):
    collected: list[bytes] = []
    received = 0
    while chunk := await file.read(1024 * 1024):
        received += len(chunk)
        if received > MAX_UPLOAD_BYTES:       # stop reading early instead of buffering an oversized file
            raise HTTPException(413, detail={"message": f"The file is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."})
        collected.append(chunk)
    try:
        upload = mgr.save_upload(user["username"], file.filename or "upload", collected)
        parsed = parse_sheet(upload.path, upload.fmt, limit=PREVIEW_ROWS)
    except ImportError_ as exc:
        raise _fail(exc)
    return success({
        "upload_id": upload.upload_id, "filename": upload.filename, "format": upload.fmt, "size": upload.size,
        "headers": upload.headers, "total_rows": upload.total_rows, "blank_rows_skipped": upload.blank_rows,
        "preview": [{"row": n, "cells": cells} for n, cells in parsed.rows],
        "preview_limit": PREVIEW_ROWS, "suggested_mapping": suggest_mapping(upload.headers),
        "existing_student_count": int(len(service.students)),
    })


@router.get("/uploads/{upload_id}/rows", summary="Page through the uploaded rows")
def upload_rows(upload_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
                user: dict = Admin, mgr: ImportManager = Depends(manager)):
    try:
        upload = mgr.get_upload(upload_id, user["username"])
        parsed = parse_sheet(upload.path, upload.fmt)
    except ImportError_ as exc:
        raise _fail(exc)
    page = parsed.rows[offset: offset + limit]
    return success([{"row": n, "cells": c} for n, c in page],
                   {"total": len(parsed.rows), "offset": offset, "limit": limit, "has_more": offset + limit < len(parsed.rows)})


@router.delete("/uploads/{upload_id}", summary="Discard an uploaded file")
def discard_upload(upload_id: str, user: dict = Admin, mgr: ImportManager = Depends(manager)):
    try:
        mgr.discard_upload(upload_id, user["username"])
    except ImportError_ as exc:
        raise _fail(exc)
    return success({"discarded": True})


def _start(kind: str, upload_id: str, body: dict, user: dict, mgr: ImportManager, service: DataService):
    try:
        upload = mgr.get_upload(upload_id, user["username"])
        mode = str(body.get("mode", ""))
        mapping = normalise_mapping(body.get("mapping") or {}, len(upload.headers), mode)
        job = mgr.submit(upload, kind, mapping, mode, service)
    except ImportError_ as exc:
        raise _fail(exc)
    return success(job.public())


@router.post("/uploads/{upload_id}/validate", status_code=202, summary="Start server-side validation (background job)")
def start_validation(upload_id: str, body: dict = Body(...), user: dict = Admin,
                     mgr: ImportManager = Depends(manager), service: DataService = Depends(get_service)):
    return _start("validate", upload_id, body, user, mgr, service)


@router.post("/uploads/{upload_id}/import", status_code=202, summary="Start the import (background job)")
def start_import(upload_id: str, body: dict = Body(...), user: dict = Admin,
                 mgr: ImportManager = Depends(manager), service: DataService = Depends(get_service)):
    return _start("import", upload_id, body, user, mgr, service)


@router.get("/jobs/{job_id}", summary="Job progress and results")
def job_status(job_id: str, user: dict = Admin, mgr: ImportManager = Depends(manager)):
    try:
        return success(mgr.get_job(job_id, user["username"]).public())
    except ImportError_ as exc:
        raise _fail(exc)


@router.get("/jobs/{job_id}/issues", summary="Validation issues with spreadsheet row numbers")
def job_issues(job_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
               code: str | None = Query(None, max_length=40), user: dict = Admin,
               mgr: ImportManager = Depends(manager)):
    try:
        job = mgr.get_job(job_id, user["username"])
    except ImportError_ as exc:
        raise _fail(exc)
    issues = sorted(job.issues, key=lambda i: (i.row, i.field or ""))
    if code:
        issues = [i for i in issues if i.code == code]
    page = issues[offset: offset + limit]
    return success([i.as_dict(job.headers) for i in page],
                   {"total": len(issues), "offset": offset, "limit": limit, "has_more": offset + limit < len(issues)})


@router.get("/jobs/{job_id}/issues/by-row", summary="Issues for specific spreadsheet rows (used to highlight the preview)")
def job_issues_for_rows(job_id: str, first_row: int = Query(..., ge=1), last_row: int = Query(..., ge=1),
                        user: dict = Admin, mgr: ImportManager = Depends(manager)):
    try:
        job = mgr.get_job(job_id, user["username"])
    except ImportError_ as exc:
        raise _fail(exc)
    selected = [i.as_dict(job.headers) for i in job.issues if first_row <= i.row <= last_row]
    return success(selected, {"count": len(selected)})


@router.post("/jobs/{job_id}/cancel", summary="Request cancellation (only before changes are saved)")
def cancel_job(job_id: str, user: dict = Admin, mgr: ImportManager = Depends(manager)):
    try:
        return success(mgr.cancel(job_id, user["username"]).public())
    except ImportError_ as exc:
        raise _fail(exc)


@router.get("/jobs/{job_id}/errors.csv", summary="Download the error report")
def error_report(job_id: str, user: dict = Admin, mgr: ImportManager = Depends(manager)):
    try:
        job = mgr.get_job(job_id, user["username"])
    except ImportError_ as exc:
        raise _fail(exc)
    return Response(error_report_csv(job), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="import-errors-{job.job_id[:8]}.csv"'})
