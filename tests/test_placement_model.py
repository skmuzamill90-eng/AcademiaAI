import pandas as pd
import pytest

from app.placement_model import placement_model_metrics, predict_placement_status, train_placement_model


def test_current_placement_status_is_rejected_as_a_future_training_target():
    frame = pd.DataFrame([
        {"student_id": "STU00000001", "placement_status": "Eligible", "coding_score": 70},
        {"student_id": "STU00000002", "placement_status": "Placed", "coding_score": 85},
    ])

    with pytest.raises(ValueError, match="Current placement_status is an observed status"):
        train_placement_model(frame)


def test_future_training_requires_temporal_outcomes_and_evaluation_data():
    frame = pd.DataFrame([{
        "student_id": "STU00000001",
        "snapshot_date": "2026-01-01",
        "future_readiness_outcome": "Ready",
    }])

    with pytest.raises(ValueError, match="chronological held-out evaluation"):
        train_placement_model(frame)


def test_legacy_model_is_not_loaded_or_reported_as_a_future_model():
    metrics = placement_model_metrics()

    assert metrics["model_evaluation_status"] == "insufficient_data"
    assert metrics["metrics"] is None
    assert metrics["baseline"] is None
    assert predict_placement_status({"placement_status": "Eligible"}, "STU00000001") is None
