"""Placement prediction is unavailable until dated future outcomes are supplied."""
from __future__ import annotations

from typing import Any

MODEL_VERSION = "future-placement-not-trained-v1"
REQUIRED_FUTURE_COLUMNS = {"student_id", "snapshot_date", "future_readiness_outcome"}


def train_placement_model(frame: Any, *, random_state: int = 42, n_splits: int = 5) -> dict[str, Any]:
    """Reject cross-sectional placement labels instead of training a misleading forecast."""
    columns = set(getattr(frame, "columns", ()))
    missing = sorted(REQUIRED_FUTURE_COLUMNS - columns)
    if missing:
        raise ValueError(
            "Cannot train a future placement-readiness model: the data is missing "
            f"{', '.join(missing)}. Current placement_status is an observed status, not a future outcome."
        )
    raise ValueError(
        "Future placement model training is not enabled until dated outcomes, a documented placement-season "
        "deadline, and a chronological held-out evaluation dataset are available."
    )


def placement_model_metrics(artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "model_version": MODEL_VERSION,
        "model_evaluation_status": "insufficient_data",
        "data_sufficiency_status": "no_temporal_future_outcomes",
        "summary": (
            "No future placement-readiness model is trained. A cross-sectional classifier of current placement "
            "status is not a future placement forecast."
        ),
        "metrics": None,
        "baseline": None,
        "class_counts": None,
        "caveats": [
            "Current placement_status is an observed label, not a future readiness outcome.",
            "No dated future outcomes are available for temporal evaluation or probability calibration.",
        ],
    }


def predict_placement_status(row: dict[str, Any], student_id: str) -> None:
    """There is no validated future placement model to serve."""
    return None
