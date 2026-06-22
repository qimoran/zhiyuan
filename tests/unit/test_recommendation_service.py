from __future__ import annotations

import pytest

from src.common.exceptions import ValidationError
from src.services.recommendation_service import (
    calculate_data_quality_score,
    calculate_plan_stability_score,
    classify_rank_type,
    finalize_grouped_recommendations,
    parse_recommend_input,
    sort_recommendation_groups_by_score_diff,
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


def test_data_quality_warns_when_plan_history_is_short() -> None:
    score, warnings = calculate_data_quality_score({"plan_count": 20}, [{"year": 2026, "plan_count": 20}])
    assert score < 100
    assert any("招生计划数据不足" in warning for warning in warnings)


def test_finalize_keeps_safe_candidate_out_of_rush_when_rush_empty() -> None:
    grouped = {
        "rush": [],
        "stable": [{"candidate_school_id": 1, "university_name": "稳妥学校", "score_diff": 14, "recommend_score": 95}],
        "safe": [{"candidate_school_id": 2, "university_name": "保底学校", "score_diff": 86, "recommend_score": 60}],
    }

    finalized, warnings = finalize_grouped_recommendations(grouped, 5)

    assert finalized["rush"] == []
    assert finalized["stable"][0]["score_diff"] == 14
    assert finalized["safe"][0]["score_diff"] == 86
    assert warnings == []


def test_sort_recommendation_groups_uses_score_diff_not_recommend_score() -> None:
    grouped = {
        "rush": [
            {"candidate_school_id": 1, "university_name": "A", "score_diff": 8, "plan_count": 99, "recommend_score": 99},
            {"candidate_school_id": 2, "university_name": "B", "score_diff": -3, "plan_count": 5, "recommend_score": 50},
            {"candidate_school_id": 7, "university_name": "G", "score_diff": -3, "plan_count": 30, "recommend_score": 40},
        ],
        "stable": [
            {"candidate_school_id": 3, "university_name": "C", "score_diff": 12, "plan_count": 99, "recommend_score": 99},
            {"candidate_school_id": 4, "university_name": "D", "score_diff": 22, "plan_count": 4, "recommend_score": 50},
            {"candidate_school_id": 8, "university_name": "H", "score_diff": 22, "plan_count": 40, "recommend_score": 40},
        ],
        "safe": [
            {"candidate_school_id": 5, "university_name": "E", "score_diff": 30, "plan_count": 99, "recommend_score": 99},
            {"candidate_school_id": 6, "university_name": "F", "score_diff": 80, "plan_count": 6, "recommend_score": 50},
            {"candidate_school_id": 9, "university_name": "I", "score_diff": 80, "plan_count": 60, "recommend_score": 40},
        ],
    }

    sort_recommendation_groups_by_score_diff(grouped)

    assert [(item["score_diff"], item["plan_count"]) for item in grouped["rush"]] == [(-3, 30), (-3, 5), (8, 99)]
    assert [(item["score_diff"], item["plan_count"]) for item in grouped["stable"]] == [(22, 40), (22, 4), (12, 99)]
    assert [(item["score_diff"], item["plan_count"]) for item in grouped["safe"]] == [(80, 60), (80, 6), (30, 99)]


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
