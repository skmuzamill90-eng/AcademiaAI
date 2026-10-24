from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import RISK_CONFIG, SCORE_CONFIG
from .risk_service import assess_risk
from .utils import is_missing

MODEL_VERSION = "prediction-contract-v2"

_TASKS = {
    "semester_performance": {
        "horizon": "next semester",
        "label": "Semester performance",
        "requirement": "Dated prior-semester features linked to actual subsequent-semester outcomes.",
        "limitation": "The available records contain one current-semester snapshot, not a later-semester outcome.",
    },
    "backlog_risk": {
        "horizon": "next academic term",
        "label": "Future backlog risk",
        "requirement": "Dated backlog history linked to subsequent new-backlog and backlog-clearance outcomes.",
        "limitation": "The available records contain current backlog counts only; they do not identify new or cleared future backlogs.",
    },
    "placement_readiness": {
        "horizon": "before the placement-season deadline",
        "label": "Future placement readiness",
        "requirement": "Pre-deadline features linked to a verified future readiness outcome.",
        "limitation": "The available placement status and readiness values are current records without a future outcome date.",
    },
    "engagement_drop": {
        "horizon": "next 30 days",
        "label": "Engagement decline",
        "requirement": "Repeated dated engagement snapshots linked to a defined subsequent 30-day decline outcome.",
        "limitation": "The available attendance and engagement values are one current snapshot, not a time series.",
    },
}

_OBSERVED_FIELDS = {
    "semester_performance": (
        ("cgpa", "CGPA"), ("semester_score_pct", "Current semester score"),
        ("internal_score_pct", "Internal assessment score"), ("backlogs", "Existing backlogs"),
        ("success_score", "Round 1 Student Success Score"),
    ),
    "backlog_risk": (
        ("backlogs", "Existing backlogs"), ("cgpa", "CGPA"),
        ("semester_score_pct", "Current semester score"), ("overall_attendance_pct", "Attendance"),
    ),
    "placement_readiness": (
        ("placement_status", "Current placement status"),
        ("placement_readiness_score", "Current placement-readiness assessment"),
        ("aptitude_score", "Aptitude score"), ("coding_score", "Coding score"),
        ("mock_interview_score", "Mock interview score"), ("resume_readiness_pct", "Resume readiness"),
        ("technical_skill_score", "Technical skill score"), ("soft_skill_score", "Soft skill score"),
    ),
    "engagement_drop": (
        ("overall_attendance_pct", "Current attendance"), ("subjects_below_attendance_threshold", "Subjects below attendance threshold"),
        ("logins_last_30_days", "LMS logins in the last 30 days"),
        ("assignment_completion_pct", "Assignment completion"),
        ("avg_weekly_learning_hours", "Average weekly learning hours"),
        ("events_attended", "Events attended"), ("club_participation", "Club participation"),
    ),
}

_CURRENT_RISK_TYPES = {
    "semester_performance": "academic",
    "backlog_risk": "academic",
    "placement_readiness": "placement",
    "engagement_drop": "academic",
}


class PredictionService:
    """Expose current recorded assessments without implying unsupported forecasts."""

    def __init__(self, *, model_version: str = MODEL_VERSION):
        self.model_version = model_version

    @staticmethod
    def _observed(row: dict[str, Any], key: str) -> Any:
        value = row.get(key)
        if is_missing(value):
            return None
        if isinstance(value, (int, float, str, bool)):
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            return str(value)

    def _current_assessment(self, prediction_type: str, row: dict[str, Any]) -> dict[str, Any]:
        task = _TASKS[prediction_type]
        observed = {
            key: self._observed(row, key)
            for key, _ in _OBSERVED_FIELDS[prediction_type]
        }
        rules = assess_risk(_CURRENT_RISK_TYPES[prediction_type], row)
        evidence = [
            {
                "label": item["label"],
                "value": item["value"],
                "threshold": item["threshold"],
                "reason": item["reason"],
            }
            for item in rules["triggered_indicators"]
        ]
        benchmarks = None
        if prediction_type == "placement_readiness":
            benchmarks = {
                "indicators": [
                    {
                        "label": rule["label"],
                        "direction": rule["direction"],
                        "thresholds": (
                            [
                                {"threshold": tier["threshold"], "points": tier["points"]}
                                for tier in rule["tiers"]
                            ]
                            if "tiers" in rule else [
                                {"threshold": rule.get("equals"), "points": rule.get("points")}
                            ]
                        ),
                    }
                    for rule in RISK_CONFIG["placement"]["rules"]
                ],
                "risk_point_cutoffs": {
                    "medium_at": RISK_CONFIG["levels"]["medium_min_points"],
                    "high_at": RISK_CONFIG["levels"]["high_min_points"],
                },
                "readiness_score_weights": SCORE_CONFIG["placement_readiness"]["weights"],
                "configured_in": "app/config.py (SCORE_CONFIG and RISK_CONFIG)",
            }
        risk_level: str | None = rules["level"]
        suggested_actions = rules["suggested_actions"]

        if prediction_type == "semester_performance":
            summary = "Academic standing from the student's recorded CGPA, semester and internal scores, and backlog count."
            score = observed["success_score"]
            score_label = "Round 1 Student Success Score (current snapshot)"
        elif prediction_type == "backlog_risk":
            count = observed["backlogs"]
            summary = (
                f"{count:g} existing backlog(s) recorded; this is not a prediction of new backlogs or backlog clearance."
                if isinstance(count, (int, float))
                else "Existing backlog count is unavailable; future backlog outcomes cannot be inferred."
            )
            score, score_label = None, None
        elif prediction_type == "placement_readiness":
            status = observed["placement_status"]
            summary = (
                f"Current placement status: {status}."
                if status is not None else "Current placement status is unavailable."
            )
            score = observed["placement_readiness_score"]
            score_label = "Placement-readiness assessment (current snapshot)"
        else:
            summary = "Current attendance, LMS, and participation indicators; no change-over-time assessment is available."
            score, score_label = None, None
            risk_level = None
            evidence = []
            suggested_actions = [
                "Review the student's recorded attendance and learning-platform activity; this is not a future decline alert."
            ]

        return {
            "status": "current_assessment_only",
            "label": task["label"] + " — current records",
            "summary": summary,
            "observed_values": observed,
            "score": score,
            "score_label": score_label,
            "risk_level": risk_level,
            "risk_is_probability": False,
            "triggered_indicators": evidence,
            "suggested_actions": suggested_actions,
            "assessment_disclaimer": rules["disclaimer"],
            "benchmarks": benchmarks,
        }

    def predict_student(
        self,
        student_id: str,
        row: dict[str, Any],
        prediction_type: str | None = None,
    ) -> dict[str, Any]:
        prediction_type = (prediction_type or "semester_performance").strip().lower()
        if prediction_type == "semester-performance":
            prediction_type = "semester_performance"
        if prediction_type not in _TASKS:
            raise ValueError(f"Unknown prediction type '{prediction_type}'.")

        task = _TASKS[prediction_type]
        current = self._current_assessment(prediction_type, row)
        factors = [
            {"factor": key, "label": label, "value": self._observed(row, key)}
            for key, label in _OBSERVED_FIELDS[prediction_type]
        ]
        factors = [factor for factor in factors if factor["value"] is not None]
        limitation = task["limitation"]
        if current["risk_level"] == "Not applicable" and prediction_type == "placement_readiness":
            action = "Confirm the recorded placed status; this service does not predict a future placement outcome."
        else:
            action = next(
                (item for item in current["suggested_actions"] if item != "No specific support indicated by these rules; continue routine monitoring"),
                "Use existing current-indicator recommendations and gather dated follow-up records.",
            )

        return {
            "student_id": student_id,
            "prediction_type": prediction_type,
            "prediction_timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "forecast_horizon": task["horizon"],
            "prediction_horizon": task["horizon"],
            "observed_value": current["observed_values"],
            "current_assessment": current,
            "predicted_outcome": None,
            "probability": None,
            "predicted_probability": None,
            "predicted_value": None,
            "risk_category": "Forecast unavailable",
            "risk_level": None,
            "top_contributing_factors": factors,
            "model_version": self.model_version,
            "model_status": "insufficient_data",
            "model_evaluation_status": "insufficient_data",
            "data_sufficiency_status": "no_temporal_future_outcomes",
            "evaluation_summary": "Not evaluated: there are no suitable dated future outcome labels for this task.",
            "explanation": (
                f"No future estimate is produced. {limitation} "
                "The displayed values are observed records and current rule-based assessments only."
            ),
            "limitations": [limitation, task["requirement"]],
            "caveats": [limitation, task["requirement"]],
            "recommended_action": action,
            "prediction_validation_status": "not_trained_no_future_labels",
            "recorded_placement_status": row.get("placement_status") if prediction_type == "placement_readiness" else None,
        }

    def predict_all(self, student_id: str, row: dict[str, Any]) -> dict[str, Any]:
        predictions = {key: self.predict_student(student_id, row, key) for key in _TASKS}
        return {
            "student_id": student_id,
            "predictions": predictions,
            "model_version": self.model_version,
            "model_evaluation_status": "insufficient_data",
            "data_sufficiency_status": "no_temporal_future_outcomes",
        }

    def evaluate_models(self, total_students: int | None = None) -> dict[str, Any]:
        statuses = {
            key: {
                "status": "insufficient_data",
                "label": task["label"],
                "horizon": task["horizon"],
                "reason": task["limitation"],
                "required_data": task["requirement"],
            }
            for key, task in _TASKS.items()
        }
        return {
            "model_version": self.model_version,
            "model_evaluation_status": "insufficient_data",
            "data_sufficiency_status": "no_temporal_future_outcomes",
            "summary": (
                "No validated future-outcome models are available. Current indicators remain viewable, "
                "but one snapshot cannot establish future performance, backlog, placement, or engagement outcomes."
            ),
            "model_statuses": statuses,
            "available_models": [],
            "students_checked": total_students,
            "metrics": None,
            "baseline": None,
            "limitations": [
                "The source data has current academic-year records but no subsequent-semester or other dated future outcome labels.",
                "The existing placement-status classifier was a cross-sectional status classifier, not a future placement model; its score is not shown as a probability.",
            ],
        }


def build_prediction_service() -> PredictionService:
    return PredictionService()


__all__ = ["PredictionService", "build_prediction_service", "MODEL_VERSION"]
