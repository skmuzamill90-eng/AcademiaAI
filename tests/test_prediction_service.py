from app.prediction_service import PredictionService


def sample_student(**overrides):
    row = {
        "student_id": "STU00000001",
        "cgpa": 8.0,
        "backlogs": 1,
        "internal_score_pct": 65.0,
        "semester_score_pct": 68.0,
        "overall_attendance_pct": 52.5,
        "subjects_below_attendance_threshold": 2,
        "assignment_completion_pct": 36.9,
        "logins_last_30_days": 5,
        "avg_weekly_learning_hours": 2.0,
        "events_attended": 1,
        "club_participation": "Occasional",
        "placement_status": "Eligible",
        "placement_readiness_score": 61.5,
        "aptitude_score": 70.0,
        "coding_score": 60.0,
        "mock_interview_score": 55.0,
        "resume_readiness_pct": 50.0,
        "technical_skill_score": 65.0,
        "soft_skill_score": 70.0,
        "success_score": 62.0,
    }
    row.update(overrides)
    return row


def test_all_future_predictions_are_unavailable_without_future_labels():
    result = PredictionService().predict_all("STU00000001", sample_student())

    assert set(result["predictions"]) == {
        "semester_performance", "backlog_risk", "placement_readiness", "engagement_drop",
    }
    for prediction in result["predictions"].values():
        assert prediction["model_status"] == "insufficient_data"
        assert prediction["predicted_outcome"] is None
        assert prediction["probability"] is None
        assert prediction["predicted_probability"] is None
        assert prediction["predicted_value"] is None
        assert prediction["risk_level"] is None
        assert prediction["current_assessment"]["status"] == "current_assessment_only"
        assert prediction["limitations"]


def test_placement_shows_observed_status_not_classifier_probability():
    prediction = PredictionService().predict_student(
        "STU00000001", sample_student(), "placement_readiness",
    )

    assert prediction["observed_value"]["placement_status"] == "Eligible"
    assert prediction["recorded_placement_status"] == "Eligible"
    assert prediction["current_assessment"]["score"] == 61.5
    assert prediction["probability"] is None
    assert prediction["predicted_probability"] is None
    assert "Eligible" in prediction["current_assessment"]["summary"]
    aptitude = next(
        item for item in prediction["current_assessment"]["benchmarks"]["indicators"]
        if item["label"] == "Aptitude"
    )
    assert [rule["threshold"] for rule in aptitude["thresholds"]] == [40, 55]


def test_current_low_attendance_and_assignment_trigger_existing_rules():
    prediction = PredictionService().predict_student(
        "STU00000001", sample_student(), "semester_performance",
    )

    assert prediction["current_assessment"]["summary"] == (
        "Academic standing from the student's recorded CGPA, semester and internal scores, and backlog count."
    )
    reasons = " ".join(item["reason"] for item in prediction["current_assessment"]["triggered_indicators"])
    assert "52.5%" in reasons
    assert "36.9%" in reasons
    assert prediction["current_assessment"]["risk_level"] == "High"
    assert prediction["current_assessment"]["risk_is_probability"] is False


def test_missing_current_values_remain_unavailable_not_zero():
    row = sample_student(
        cgpa=None,
        backlogs=None,
        internal_score_pct=None,
        semester_score_pct=None,
        overall_attendance_pct=None,
        assignment_completion_pct=None,
    )
    prediction = PredictionService().predict_student("STU00000001", row, "backlog_risk")

    assert prediction["observed_value"]["backlogs"] is None
    assert prediction["observed_value"]["cgpa"] is None
    assert prediction["current_assessment"]["risk_level"] == "Insufficient data"
    assert prediction["predicted_probability"] is None


def test_evaluation_reports_each_task_and_does_not_publish_cross_sectional_metrics():
    evaluation = PredictionService().evaluate_models(total_students=500)

    assert evaluation["model_evaluation_status"] == "insufficient_data"
    assert evaluation["available_models"] == []
    assert evaluation["metrics"] is None
    assert set(evaluation["model_statuses"]) == {
        "semester_performance", "backlog_risk", "placement_readiness", "engagement_drop",
    }
    assert all(task["status"] == "insufficient_data" for task in evaluation["model_statuses"].values())
    assert any("cross-sectional" in item for item in evaluation["limitations"])
