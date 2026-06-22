"""S14 推荐报告生成服务。

支持 OpenAI 兼容的大模型接口；未配置密钥或调用失败时自动回退模板报告。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.common.config import get_env
from src.common.database import fetch_one, mysql_connection
from src.common.exceptions import ValidationError
from src.common.logger import get_logger
from src.common.trace import get_trace_id
from src.common.llm_client import chat, LLMClientError

DISCLAIMER = "仅供参考，最终以官方招生政策和当年复试录取结果为准。"
RANK_LABELS = {"rush": "冲刺档", "stable": "稳妥档", "safe": "保底档"}
SUPPORTED_REPORT_TYPES = {"template", "llm", "auto"}
logger = get_logger(__name__)


@dataclass(frozen=True)
class LlmReportResult:
    """大模型报告结果。"""

    content: str
    model: str


class LlmReportUnavailable(Exception):
    """大模型未配置或调用失败。"""


def generate_report(payload: dict[str, Any]) -> dict[str, Any]:
    """生成择校推荐报告并保存到 ``report_records``。"""
    report_type = str(payload.get("report_type") or "template").strip().lower()
    if report_type not in SUPPORTED_REPORT_TYPES:
        raise ValidationError("report_type 仅支持 template、llm 或 auto")

    prompt = build_report_prompt(payload)
    actual_report_type = "template"
    ai_status = "not_requested"
    fallback_reason = ""
    llm_model = None

    if report_type in {"llm", "auto"}:
        try:
            llm_result = call_llm_report(prompt)
            report_content = llm_result.content
            actual_report_type = "llm"
            ai_status = "success"
            llm_model = llm_result.model
        except LlmReportUnavailable as exc:
            logger.warning("大模型报告生成失败，切换模板报告：%s", exc)
            fallback_reason = str(exc)
            ai_status = "fallback"
            report_content = build_template_report(prompt)
    else:
        report_content = build_template_report(prompt)

    record_id = save_report_record(
        recommendation_log_id=prompt.get("recommendation_log_id"),
        report_type=actual_report_type,
        prompt=prompt,
        report_content=report_content,
    )
    response = {
        "report_id": record_id,
        "report_type": actual_report_type,
        "report_content": report_content,
        "disclaimer": DISCLAIMER,
        "source_note": build_source_note(actual_report_type),
        "warnings": prompt.get("warnings", []),
        "ai_status": ai_status,
    }
    if llm_model:
        response["llm_model"] = llm_model
    if fallback_reason:
        response["fallback_reason"] = fallback_reason
    return response


def build_report_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    """整理报告输入，优先使用前端传入的完整推荐结果。"""
    recommendation_log_id = parse_optional_int(payload.get("recommendation_log_id"))
    recommendation_trace_id = clean_text(payload.get("recommendation_trace_id"))
    request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    result_payload = payload.get("recommendation_result")
    if not isinstance(result_payload, dict):
        result_payload = payload.get("result") if isinstance(payload.get("result"), dict) else {}

    log_row = load_recommendation_log(recommendation_log_id, recommendation_trace_id)
    warnings: list[str] = []
    if log_row:
        recommendation_log_id = int(log_row["id"])
        if not request_payload:
            request_payload = parse_json_field(log_row.get("request_json"), {})
        if not result_payload:
            stored_result = parse_json_field(log_row.get("result_summary_json"), {})
            if isinstance(stored_result, dict) and (
                "recommendations" in stored_result or "score_evaluation" in stored_result or "summary" in stored_result
            ):
                result_payload = stored_result
            else:
                result_payload = {"summary": stored_result}
            result_payload["warnings"] = parse_json_field(log_row.get("warning_json"), [])
    else:
        warnings.append("未找到对应推荐日志，本次报告仅根据当前请求内容生成。")

    result_warnings = result_payload.get("warnings") if isinstance(result_payload, dict) else []
    if isinstance(result_warnings, list):
        warnings.extend(str(item) for item in result_warnings if str(item).strip())

    return {
        "recommendation_log_id": recommendation_log_id,
        "recommendation_trace_id": recommendation_trace_id or (log_row or {}).get("trace_id"),
        "request": request_payload,
        "result": result_payload,
        "warnings": dedupe(warnings),
        "data_source": "掌上考研 V2 公开接口 + 本项目 MySQL 清洗入库数据",
        "disclaimer": DISCLAIMER,
    }


def call_llm_report(prompt: dict[str, Any]) -> LlmReportResult:
    """调用 OpenAI 兼容 Chat Completions 接口生成报告。"""
    try:
        messages = build_llm_messages(prompt)
        content = chat(messages, temperature=0.2)
        model = get_env("LLM_MODEL") or get_env("OPENAI_MODEL") or "gpt-4o-mini"
        return LlmReportResult(content=content, model=model)
    except LLMClientError as exc:
        raise LlmReportUnavailable(str(exc)) from exc


def build_llm_messages(prompt: dict[str, Any]) -> list[dict[str, str]]:
    context = build_llm_context(prompt)
    return [
        {
            "role": "system",
            "content": (
                "你是考研择校推荐系统的报告生成助手。必须只基于用户输入和系统提供的数据库推荐结果写报告，"
                "不得编造学校、专业、分数线、招生人数、录取概率或不存在的数据。"
                "不得使用'保证录取''一定上岸'等承诺性表达。"
                "如果某项数据缺失，明确写'暂无数据'。输出中文 Markdown。\n\n"
                "重要：系统已经通过本地 RAG 知识库和联网搜索为每个推荐院校提供了资料证据（agent_evidence），"
                "包括本地 PDF 资料（local_rag）和联网搜索结果（tavily）。"
                "你必须优先引用这些证据来支撑推荐理由，尤其是招生简章、招生计划、复试分数线等关键信息。"
                "对于 source_confidence 为 high 或 medium 的推荐，应重点说明本地资料的匹配情况。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请根据以下 JSON 数据生成一份可直接展示给考生的考研择校建议报告。\n"
                "报告结构包括：一、考生输入概况；二、冲刺/稳妥/保底推荐概览；"
                "三、重点院校推荐理由；四、备考与填报建议；五、数据风险提示。\n"
                "重点说明每所推荐学校与用户分数、近年专业复试线、招生计划变化之间的关系。\n"
                "对于每个推荐院校，如果 agent_evidence 中有本地 PDF 资料或联网搜索结果，"
                "请在推荐理由中引用这些证据（如'根据本地资料XXX招生简章''联网搜索显示XXX'）。\n\n"
                f"{json.dumps(context, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def build_llm_context(prompt: dict[str, Any]) -> dict[str, Any]:
    result = prompt.get("result") if isinstance(prompt.get("result"), dict) else {}
    recommendations = result.get("recommendations") if isinstance(result.get("recommendations"), dict) else {}
    return {
        "request": prompt.get("request") if isinstance(prompt.get("request"), dict) else {},
        "recommendations": {
            rank_key: [compact_recommendation_item(item) for item in recommendations.get(rank_key, [])]
            for rank_key in ("rush", "stable", "safe")
        },
        "score_evaluation": result.get("score_evaluation") if isinstance(result, dict) else {},
        "recommendation_agent": result.get("recommendation_agent") if isinstance(result, dict) else {},
        "warnings": prompt.get("warnings", []),
        "data_source": prompt.get("data_source"),
        "disclaimer": prompt.get("disclaimer"),
    }


def compact_recommendation_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank_type": item.get("rank_type"),
        "university_name": item.get("university_name"),
        "school_level": item.get("school_level"),
        "department_name": item.get("department_name"),
        "major_code": item.get("major_code"),
        "major_name": item.get("major_name"),
        "degree_type": item.get("degree_type"),
        "study_mode": item.get("study_mode"),
        "score_line": item.get("score_line"),
        "score_diff": item.get("score_diff"),
        "score_line_history": item.get("score_line_history") or [],
        "plan_count": item.get("plan_count"),
        "plan_history": item.get("plan_history") or [],
        "plan_stability_score": item.get("plan_stability_score"),
        "data_quality_score": item.get("data_quality_score"),
        "source_confidence": item.get("source_confidence"),
        "evidence_summary": item.get("evidence_summary"),
        "agent_adjustment_score": item.get("agent_adjustment_score"),
        "agent_evidence": item.get("agent_evidence") or {},
        "reason": item.get("reason"),
        "warnings": item.get("warnings") or [],
    }


def build_source_note(report_type: str) -> str:
    if report_type == "llm":
        return "报告由大模型基于本系统推荐结果和当前 MySQL 入库数据生成。"
    return "报告基于本系统推荐接口返回结果和当前 MySQL 入库数据生成。"


def load_recommendation_log(
    recommendation_log_id: int | None,
    recommendation_trace_id: str | None,
) -> dict[str, Any] | None:
    if recommendation_log_id:
        return fetch_one(
            """
            SELECT id, trace_id, request_json, result_summary_json, warning_json
            FROM recommendation_logs
            WHERE id = %(id)s
            """,
            {"id": recommendation_log_id},
        )
    if recommendation_trace_id:
        return fetch_one(
            """
            SELECT id, trace_id, request_json, result_summary_json, warning_json
            FROM recommendation_logs
            WHERE trace_id = %(trace_id)s
            ORDER BY id DESC
            LIMIT 1
            """,
            {"trace_id": recommendation_trace_id},
        )
    return None


def build_template_report(prompt: dict[str, Any]) -> str:
    request_payload = prompt.get("request") if isinstance(prompt.get("request"), dict) else {}
    result = prompt.get("result") if isinstance(prompt.get("result"), dict) else {}
    recommendations = result.get("recommendations") if isinstance(result.get("recommendations"), dict) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}

    target_year = request_payload.get("target_year") or "未填写"
    major_name = request_payload.get("major_name") or request_payload.get("major_category") or "未填写"
    total_score = request_payload.get("total_score") or "未填写"
    lines = [
        "# 考研择校推荐报告",
        "",
        "## 一、输入信息",
        f"- 目标年份：{target_year}",
        f"- 目标专业：{major_name}",
        f"- 初试总分：{total_score}",
        f"- 学位类型：{format_degree_type(request_payload.get('degree_type'))}",
        f"- 学习方式：{format_study_mode(request_payload.get('study_mode'))}",
        "",
        "## 二、推荐概览",
    ]

    if recommendations:
        for rank_key in ("rush", "stable", "safe"):
            items = recommendations.get(rank_key) or []
            lines.append(f"- {RANK_LABELS[rank_key]}：{len(items)} 个")
    else:
        lines.extend(
            [
                f"- 候选学校数：{summary.get('candidate_count', 0)}",
                f"- 返回推荐数：{summary.get('returned_count', 0)}",
                f"- 冲刺档：{summary.get('rush', 0)} 个",
                f"- 稳妥档：{summary.get('stable', 0)} 个",
                f"- 保底档：{summary.get('safe', 0)} 个",
            ]
        )

    lines.extend(["", "## 三、推荐明细"])
    if recommendations:
        for rank_key in ("rush", "stable", "safe"):
            items = recommendations.get(rank_key) or []
            lines.append(f"### {RANK_LABELS[rank_key]}")
            if not items:
                lines.append("- 暂无推荐。")
                continue
            for index, item in enumerate(items, start=1):
                school = item.get("university_name") or "未知学校"
                major = item.get("major_name") or major_name
                score_line = item.get("score_line")
                diff = item.get("score_diff")
                reason = item.get("reason") or "系统根据分数线、招生计划和数据质量综合生成。"
                lines.append(f"{index}. {school} - {major}")
                lines.append(f"   - 参考复试线：{score_line if score_line is not None else '暂无'}")
                lines.append(f"   - 分数差：{format_diff(diff)}")
                lines.append(f"   - 近年复试线：{format_history(item.get('score_line_history'), 'total_score_line', '分')}")
                lines.append(f"   - 近年招生计划：{format_history(item.get('plan_history'), 'plan_count', '人')}")
                if item.get("evidence_summary"):
                    lines.append(f"   - 资料核验：{item.get('evidence_summary')}")
                lines.append(f"   - 推荐理由：{reason}")
    else:
        lines.append("当前请求没有携带完整推荐明细，仅生成推荐摘要报告。")

    warnings = prompt.get("warnings") or []
    lines.extend(["", "## 四、风险提示"])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- 暂无额外风险提示。")
    lines.extend(
        [
            "- 第三方采集数据可能与学校最新公告存在时间差，正式填报前需要核对学校官网。",
            "",
            "## 五、数据来源",
            f"- {prompt.get('data_source')}",
            "",
            DISCLAIMER,
        ]
    )
    return "\n".join(lines)


def save_report_record(
    *,
    recommendation_log_id: int | None,
    report_type: str,
    prompt: dict[str, Any],
    report_content: str,
) -> int:
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO report_records (
                  trace_id, recommendation_log_id, report_type, prompt_json, report_content
                )
                VALUES (
                  %(trace_id)s, %(recommendation_log_id)s, %(report_type)s,
                  %(prompt_json)s, %(report_content)s
                )
                """,
                {
                    "trace_id": get_trace_id(),
                    "recommendation_log_id": recommendation_log_id,
                    "report_type": report_type,
                    "prompt_json": json.dumps(prompt, ensure_ascii=False),
                    "report_content": report_content,
                },
            )
            report_id = int(cursor.lastrowid)
        connection.commit()
    return report_id


def parse_json_field(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def parse_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("recommendation_log_id 必须是整数") from exc
    return parsed if parsed > 0 else None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def format_diff(value: Any) -> str:
    if value is None or value == "":
        return "暂无"
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:+d} 分"


def format_degree_type(value: Any) -> str:
    return {"academic": "学术学位", "professional": "专业学位"}.get(str(value), "未填写")


def format_study_mode(value: Any) -> str:
    return {"full_time": "全日制", "part_time": "非全日制"}.get(str(value), "未填写")


def format_history(items: Any, value_key: str, unit: str) -> str:
    if not isinstance(items, list) or not items:
        return "暂无数据"
    parts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        year = item.get("year")
        value = item.get(value_key)
        if year is None or value is None:
            continue
        parts.append(f"{year}年 {value}{unit}")
    return "；".join(parts) if parts else "暂无数据"


def parse_int_env(name: str, default: int) -> int:
    try:
        value = int(get_env(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def parse_float_env(name: str, default: float) -> float:
    try:
        value = float(get_env(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value


def dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
