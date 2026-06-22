from __future__ import annotations

from src.services import report_service
from src.services.report_service import DISCLAIMER, build_report_prompt, build_template_report


def test_template_report_contains_disclaimer_and_recommendation_detail() -> None:
    prompt = build_report_prompt(
        {
            "request": {
                "target_year": 2026,
                "major_name": "计算机技术",
                "degree_type": "professional",
                "study_mode": "full_time",
                "total_score": 355,
            },
            "recommendation_result": {
                "recommendations": {
                    "rush": [
                        {
                            "university_name": "重庆大学",
                            "major_name": "计算机技术",
                            "score_line": 355,
                            "score_diff": 0,
                            "score_line_history": [
                                {"year": 2024, "total_score_line": 340},
                                {"year": 2025, "total_score_line": 350},
                                {"year": 2026, "total_score_line": 355},
                            ],
                            "plan_history": [
                                {"year": 2024, "plan_count": 18},
                                {"year": 2025, "plan_count": 20},
                                {"year": 2026, "plan_count": 22},
                            ],
                            "reason": "样例推荐理由",
                        }
                    ],
                    "stable": [],
                    "safe": [],
                },
                "warnings": ["样例风险提示"],
            },
        }
    )
    report = build_template_report(prompt)
    assert "重庆大学" in report
    assert "2026年 355分" in report
    assert "2026年 22人" in report
    assert "样例风险提示" in report
    assert DISCLAIMER in report


def test_template_report_can_fallback_to_summary() -> None:
    report = build_template_report(
        {
            "request": {"target_year": 2026, "major_category": "电子信息", "total_score": 355},
            "result": {"summary": {"candidate_count": 21, "returned_count": 9, "rush": 3, "stable": 3, "safe": 3}},
            "warnings": [],
            "data_source": "测试数据源",
            "disclaimer": DISCLAIMER,
        }
    )
    assert "候选学校数：21" in report
    assert DISCLAIMER in report


def test_generate_report_uses_llm_when_available(monkeypatch) -> None:
    monkeypatch.setattr(
        report_service,
        "call_llm_report",
        lambda prompt: report_service.LlmReportResult(content="# AI 推荐报告", model="test-model"),
    )
    monkeypatch.setattr(report_service, "save_report_record", lambda **kwargs: 9)

    result = report_service.generate_report(
        {
            "report_type": "llm",
            "request": {"target_year": 2026, "major_name": "计算机技术", "total_score": 355},
            "recommendation_result": {"recommendations": {"rush": [], "stable": [], "safe": []}},
        }
    )

    assert result["report_type"] == "llm"
    assert result["ai_status"] == "success"
    assert result["llm_model"] == "test-model"


def test_generate_report_falls_back_to_template_when_llm_unavailable(monkeypatch) -> None:
    def raise_unavailable(prompt):
        raise report_service.LlmReportUnavailable("未配置测试密钥")

    monkeypatch.setattr(report_service, "call_llm_report", raise_unavailable)
    monkeypatch.setattr(report_service, "save_report_record", lambda **kwargs: 10)

    result = report_service.generate_report(
        {
            "report_type": "llm",
            "request": {"target_year": 2026, "major_category": "电子信息", "total_score": 355},
            "recommendation_result": {"recommendations": {"rush": [], "stable": [], "safe": []}},
        }
    )

    assert result["report_type"] == "template"
    assert result["ai_status"] == "fallback"
    assert "未配置测试密钥" in result["fallback_reason"]
    assert DISCLAIMER in result["report_content"]
