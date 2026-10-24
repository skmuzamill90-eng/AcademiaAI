from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path

from ..auth import require_roles
from ..data_service import DataService, NotFoundError
from ..deps import get_service, not_found
from ..prediction_service import build_prediction_service

router = APIRouter(prefix="/api", tags=["Predictions"], dependencies=[Depends(require_roles("college_admin"))])


@router.get("/predictions/evaluation", summary="Model evaluation and data sufficiency status")
def prediction_evaluation(service: DataService = Depends(get_service)):
    model_service = build_prediction_service()
    return {"status": "success", "data": model_service.evaluate_models(total_students=len(service.students)), "meta": {}}


@router.get("/predictions/{student_id}/summary", summary="All predictive model outputs for a single student")
def prediction_summary(student_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,32}$"), service: DataService = Depends(get_service)):
    try:
        row = service.student_row(student_id)
    except NotFoundError as exc:
        raise not_found(exc)
    model_service = build_prediction_service()
    return {"status": "success", "data": model_service.predict_all(student_id, row), "meta": {}}


@router.get("/students/{student_id}/predictions", summary="All predictive model outputs for a student")
def student_predictions(student_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,32}$"), service: DataService = Depends(get_service)):
    try:
        row = service.student_row(student_id)
    except NotFoundError as exc:
        raise not_found(exc)
    model_service = build_prediction_service()
    return {"status": "success", "data": model_service.predict_all(student_id, row), "meta": {}}


@router.get("/predictions/{student_id}/{prediction_type}", summary="A single predictive model output")
def student_prediction(
    prediction_type: str,
    student_id: str = Path(..., pattern=r"^[A-Za-z0-9_-]{1,32}$"),
    service: DataService = Depends(get_service),
):
    try:
        row = service.student_row(student_id)
    except NotFoundError as exc:
        raise not_found(exc)
    model_service = build_prediction_service()
    try:
        prediction = model_service.predict_student(student_id, row, prediction_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    return {"status": "success", "data": prediction, "meta": {}}
