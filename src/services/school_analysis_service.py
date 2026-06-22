"""院校分析服务 - 为推荐结果中的单个院校生成详细分析。

基于 agentic_school 的分析功能，提供院校优劣势分析和备考建议。
"""

from __future__ import annotations

from typing import Any

from src.common.logger import get_logger
from src.common.llm_client import chat_with_system, LLMClientError

logger = get_logger(__name__)


def analyze_school(
    school_name: str,
    score_line: int,
    user_score: int,
    province: str | None = None,
    level: str | None = None,
    target_major: str | None = None,
    subject_level: str | None = None,
    match_score: int | None = None,
) -> dict[str, Any]:
    """生成单个院校的详细分析。

    Args:
        school_name: 学校名称
        score_line: 复试分数线
        user_score: 考生预估分
        province: 所在省份
        level: 学校层次
        target_major: 目标专业
        subject_level: 学科评估等级
        match_score: 匹配度评分

    Returns:
        {
            "school_name": str,
            "analysis": str,  # Markdown 格式的分析内容
            "status": "success" | "fallback"
        }
    """
    prompt = f"""你是一位专业的考研择校顾问。请分析以下院校的报考优劣势：

院校信息：
- 学校名称：{school_name}
- 所在地区：{province or '未知'}
- 学校层次：{level or '普通院校'}
- 复试分数线：{score_line}分
- 考生预估分：{user_score}分
- 分差：{user_score - score_line}分
- 匹配度评分：{match_score or '未知'}分
- 学科评估：{subject_level or '未知'}
- 目标专业：{target_major or '未知'}

请从以下角度分析（每点不超过50字）：

1. **报考优势**（2-3点）
2. **潜在风险**（2-3点）
3. **备考建议**（具体可执行的建议）

请用简洁专业的语言回答，使用 Markdown 格式，不要使用emoji。"""

    try:
        analysis = chat_with_system(
            "你是一位专业的考研择校顾问，擅长分析院校报考优劣势并给出备考建议。",
            prompt,
            temperature=0.7,
        )
        return {
            "school_name": school_name,
            "analysis": analysis,
            "status": "success",
        }
    except LLMClientError as exc:
        logger.error("院校分析失败：%s", exc)
        fallback_analysis = _build_fallback_analysis(
            school_name, score_line, user_score, level, target_major
        )
        return {
            "school_name": school_name,
            "analysis": fallback_analysis,
            "status": "fallback",
            "error": str(exc),
        }


def _build_fallback_analysis(
    school_name: str,
    score_line: int,
    user_score: int,
    level: str | None,
    target_major: str | None,
) -> str:
    """LLM 不可用时的降级分析。"""
    score_diff = user_score - score_line
    risk_level = "较低" if score_diff >= 20 else "中等" if score_diff >= 10 else "较高"

    return f"""# {school_name} 报考分析

## 基本情况
- 学校层次：{level or '普通院校'}
- 目标专业：{target_major or '未知'}
- 复试分数线：{score_line}分
- 预估分数：{user_score}分
- 分数差：{score_diff:+d}分

## 报考风险
当前分数{'高出' if score_diff > 0 else '低于'}复试线 {abs(score_diff)} 分，报考风险为 **{risk_level}**。

## 建议
{'建议重点关注专业课复习，确保初试成绩稳定。' if score_diff >= 10 else '分数压线，建议同时准备其他院校作为保底选项。'}

---
*注：此分析为系统降级模板，建议配置 LLM API Key 以获取更详细的个性化分析。*
"""
