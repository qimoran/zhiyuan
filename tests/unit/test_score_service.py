from __future__ import annotations

import pytest

from src.common.exceptions import ValidationError
from src.services.score_service import (
    build_overall_status,
    parse_score_input,
    score_status,
)


def test_score_status_levels() -> None:
    assert score_status(-1, 5) == "unsafe"
    assert score_status(0, 5) == "warning"
    assert score_status(4, 5) == "warning"
    assert score_status(5, 5) == "safe"


def test_overall_status_unsafe_when_single_subject_below_line() -> None:
    status = build_overall_status(
        total_diff=30,
        single_results=[{"diff": -1}],
        thresholds={"total_score_warning_diff": 10, "single_subject_warning_diff": 5},
    )
    assert status == "unsafe"


def test_overall_status_warning_when_total_close_to_line() -> None:
    status = build_overall_status(
        total_diff=9,
        single_results=[{"diff": 20}],
        thresholds={"total_score_warning_diff": 10, "single_subject_warning_diff": 5},
    )
    assert status == "warning"


def test_overall_status_safe_when_all_scores_above_warning_margin() -> None:
    status = build_overall_status(
        total_diff=30,
        single_results=[{"diff": 10}, {"diff": 12}],
        thresholds={"total_score_warning_diff": 10, "single_subject_warning_diff": 5},
    )
    assert status == "safe"


def test_parse_score_input_requires_major_identifier() -> None:
    with pytest.raises(ValidationError):
        parse_score_input({"target_year": 2026, "total_score": 355})


def test_parse_score_input_rejects_score_out_of_range() -> None:
    with pytest.raises(ValidationError):
        parse_score_input(
            {
                "target_year": 2026,
                "major_name": "计算机技术",
                "total_score": 355,
                "english_score": 180,
            }
        )
