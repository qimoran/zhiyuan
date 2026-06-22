from __future__ import annotations

from src.services import chart_service, metadata_service


def test_line_trend_uses_score_line_major_name_total_score(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_all(sql: str, params: dict[str, object]) -> list[dict[str, object]]:
        captured["sql"] = sql
        captured["params"] = params
        return [
            {"year": 2025, "total_score_line": 341, "distinct_score_count": 1},
            {"year": 2026, "total_score_line": 365, "distinct_score_count": 1},
        ]

    monkeypatch.setattr(chart_service, "fetch_all", fake_fetch_all)

    result = chart_service.get_line_trend(
        {"university_id": "20", "score_line_major_name": "心理健康教育"}
    )

    assert "FROM score_lines" in str(captured["sql"])
    assert "JOIN majors" not in str(captured["sql"])
    assert "major_category = %(score_line_major_name)s" in str(captured["sql"])
    assert "line_type = 'major'" in str(captured["sql"])
    assert "MAX(total_score_line) AS total_score_line" in str(captured["sql"])
    assert "politics_line" not in str(captured["sql"])
    assert "english_line" not in str(captured["sql"])
    assert captured["params"] == {
        "university_id": 20,
        "score_line_major_name": "心理健康教育",
    }
    assert result["x_axis"] == [2025, 2026]
    assert result["series"] == [{"name": "总分线", "data": [341, 365]}]


def test_plan_trend_filters_by_major_code_and_name(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_all(sql: str, params: dict[str, object]) -> list[dict[str, object]]:
        captured["sql"] = sql
        captured["params"] = params
        return [
            {"year": 2024, "total_plan": 40, "major_count": 3},
            {"year": 2025, "total_plan": 45, "major_count": 4},
        ]

    monkeypatch.setattr(chart_service, "fetch_all", fake_fetch_all)

    result = chart_service.get_plan_trend(
        {"major_category": "工学", "major_code": "085404", "major_name": "计算机技术"}
    )

    assert "m.major_category = %(major_category)s" in str(captured["sql"])
    assert "m.major_code = %(major_code)s" in str(captured["sql"])
    assert "m.major_name = %(major_name)s" in str(captured["sql"])
    assert captured["params"] == {
        "major_category": "工学",
        "major_code": "085404",
        "major_name": "计算机技术",
    }
    assert result["x_axis"] == [2024, 2025]
    assert result["series"][0]["data"] == [40, 45]
    assert result["series"][1]["data"] == [3, 4]


def test_plan_major_options_are_loaded_from_enrollment_plans(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_all(sql: str, params: dict[str, object]) -> list[dict[str, object]]:
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "major_code": "085404",
                "major_name": "计算机技术",
                "major_category": "工学",
                "total_plan": 120,
                "year_count": 3,
                "major_count": 8,
            }
        ]

    monkeypatch.setattr(metadata_service, "fetch_all", fake_fetch_all)

    result = metadata_service.list_plan_major_options({"major_category": "工学"})

    assert "FROM enrollment_plans ep" in str(captured["sql"])
    assert "JOIN majors m ON m.id = ep.major_id" in str(captured["sql"])
    assert captured["params"] == {"limit": metadata_service.MAX_PLAN_MAJOR_OPTIONS, "major_category": "工学"}
    assert result["items"] == [
        {
            "major_code": "085404",
            "major_name": "计算机技术",
            "major_category": "工学",
            "total_plan": 120,
            "year_count": 3,
            "major_count": 8,
        }
    ]


def test_score_line_major_options_use_score_line_major_name(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_all(sql: str, params: dict[str, object]) -> list[dict[str, object]]:
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "score_line_major_name": "哲学",
                "year_count": 3,
                "min_year": 2024,
                "max_year": 2026,
                "score_line_count": 6,
            }
        ]

    monkeypatch.setattr(metadata_service, "fetch_all", fake_fetch_all)

    result = metadata_service.list_score_line_major_options({"university_id": "1"})

    assert "FROM score_lines sl" in str(captured["sql"])
    assert "JOIN majors" not in str(captured["sql"])
    assert "GROUP BY sl.major_category" in str(captured["sql"])
    assert captured["params"] == {"university_id": 1, "limit": metadata_service.MAX_SCORE_LINE_MAJOR_OPTIONS}
    assert result["items"] == [
        {
            "score_line_major_name": "哲学",
            "year_count": 3,
            "min_year": 2024,
            "max_year": 2026,
            "score_line_count": 6,
        }
    ]
