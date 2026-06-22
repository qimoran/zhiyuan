from __future__ import annotations

from src.services.recommendation_agent_service import (
    apply_agent_evidence,
    best_text_chunk,
    build_source_confidence,
    is_matching_rag_file,
)


def test_apply_agent_evidence_adjusts_score_with_local_and_web_hits() -> None:
    item = {"recommend_score": 70.0, "data_quality_score": 80.0}
    evidence = {
        "local_rag": [{"title": "招生简章", "snippet": "计算机技术 招生计划"}],
        "tavily": [{"title": "学校官网", "snippet": "研究生招生"}],
    }

    apply_agent_evidence(item, evidence)

    assert item["agent_adjustment_score"] == 3.0
    assert item["recommend_score"] == 73.0
    assert item["data_quality_score"] == 83.0
    assert item["source_confidence"] == "high"
    assert "本地资料匹配" in item["evidence_summary"]


def test_apply_agent_evidence_warns_when_no_evidence() -> None:
    item = {"recommend_score": 70.0, "data_quality_score": 80.0}

    apply_agent_evidence(item, {"local_rag": [], "tavily": []})

    assert item["source_confidence"] == "unknown"
    assert item["recommend_score"] == 70.0
    assert any("人工核对" in warning for warning in item["warnings"])


def test_build_source_confidence_prefers_local_and_web_combination() -> None:
    assert build_source_confidence([{}], [{}]) == "high"
    assert build_source_confidence([{}], []) == "medium"
    assert build_source_confidence([], [{}]) == "low"
    assert build_source_confidence([], []) == "unknown"


def test_best_text_chunk_finds_relevant_chunk() -> None:
    text = "重庆大学 招生简章 计算机技术 招生计划 127 人。其他说明。"
    chunk, score = best_text_chunk(text, ["重庆大学", "计算机技术", "招生计划"])

    assert score >= 3
    assert "计算机技术" in chunk


def test_is_matching_rag_file_requires_school_or_major() -> None:
    assert is_matching_rag_file(
        "重庆师范大学2026年硕士研究生招生专业目录.pdf",
        "重庆师范大学",
        "计算机技术",
        "2026",
    )
    assert not is_matching_rag_file(
        "重庆交通大学2026年硕士研究生招生专业目录.pdf",
        "重庆师范大学",
        "计算机技术",
        "2026",
    )
