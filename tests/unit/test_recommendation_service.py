from __future__ import annotations

import pytest

from src.common.exceptions import ValidationError
from src.services.recommendation_service import (
    calculate_data_quality_score,
    calculate_plan_stability_score,
    classify_rank_type,
    parse_recommend_input,
)


def test_classify_rank_type_rush_for_small_score_diff() -> None:
    rank_type = classify_rank_type(
        total_diff=5,
        overall_status="warning",
        row={"school_level": "985 / 211 / 双一流"},
        rules={"score_thresholds": {"rush_avg_score_diff_min": -10, "rush_avg_score_diff_max": 10}},
    )
    assert rank_type == "rush"


def test_classify_rank_type_stable_for_middle_score_diff() -> None:
    rank_type = classify_rank_type(
        total_diff=18,
        overall_status="safe",
        row={"school_level": "普通院校"},
        rules={"score_thresholds": {"stable_avg_score_diff_min": 10, "safe_min_score_diff_min": 25}},
    )
    assert rank_type == "stable"


def test_classify_rank_type_safe_for_large_score_diff() -> None:
    rank_type = classify_rank_type(
        total_diff=30,
        overall_status="safe",
        row={"school_level": "普通院校"},
        rules={"score_thresholds": {"safe_min_score_diff_min": 25}},
    )
    assert rank_type == "safe"


def test_plan_stability_score_is_higher_for_stable_plan_counts() -> None:
    stable = calculate_plan_stability_score(
        [{"year": 2024, "plan_count": 30}, {"year": 2025, "plan_count": 31}, {"year": 2026, "plan_count": 30}]
    )
    volatile = calculate_plan_stability_score(
        [{"year": 2024, "plan_count": 10}, {"year": 2025, "plan_count": 60}, {"year": 2026, "plan_count": 20}]
    )
    assert stable > volatile


def test_data_quality_warns_when_admission_records_missing() -> None:
    score, warnings = calculate_data_quality_score({"plan_count": 20}, [{"year": 2026, "plan_count": 20}])
    assert score < 100
    assert any("拟录取名单" in warning for warning in warnings)


def test_parse_recommend_input_rejects_invalid_school_levels() -> None:
    with pytest.raises(ValidationError):
        parse_recommend_input(
            {
                "target_year": 2026,
                "major_name": "计算机技术",
                "total_score": 355,
                "preferred_school_levels": {"bad": "value"},
            }
        )
