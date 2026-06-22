"""S10 考研择校推荐服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any

from src.common.llm_client import LLMClientError, chat
from src.common.config import get_recommend_rules
from src.common.database import fetch_all, mysql_connection
from src.common.exceptions import ValidationError
from src.common.trace import get_trace_id
from src.services.auth_service import build_recommendation_log_payload
from src.services.recommendation_agent_service import enrich_recommendation_result
from src.services.score_service import (
    SUBJECT_SCORE_FIELDS,
    build_overall_status,
    build_single_subject_results,
    get_score_thresholds,
    parse_score_input,
)

DEFAULT_BUCKET_LIMIT = 5
MAX_CANDIDATES = 300
BUCKET_ORDER = ("rush", "stable", "safe")
RANK_LABELS = {"rush": "冲刺", "stable": "稳妥", "safe": "保底"}


@dataclass(frozen=True)
class RecommendInput:
    payload: dict[str, Any]
    target_year: int
    province: str | None
    major_category: str | None
    major_name: str | None
    major_code: str | None
    degree_type: str | None
    study_mode: str | None
    preferred_school_levels: list[str]
    total_score: int
    politics_score: int | None
    english_score: int | None
    subject_one_score: int | None
    subject_two_score: int | None
    bucket_limit: int


def recommend(payload: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
    """生成冲刺、稳妥、保底三档推荐并写入推荐日志。"""
    recommend_input = parse_recommend_input(payload)
    rules = get_recommend_rules()
    thresholds = get_score_thresholds()
    candidates = query_recommend_candidates(recommend_input)

    warnings: list[str] = []
    if not candidates:
        warnings.append("未匹配到符合条件的学校和专业，请放宽专业、学校层次或学习方式条件。")

    grouped: dict[str, list[dict[str, Any]]] = {"rush": [], "stable": [], "safe": []}
    for row in candidates:
        item = build_recommendation_item(row, recommend_input, rules, thresholds)
        if item is None:
            continue
        grouped[item["rank_type"]].append(item)

    grouped, distribution_warnings = finalize_grouped_recommendations(grouped, recommend_input.bucket_limit)

    warnings.extend(distribution_warnings)
    warnings.extend(build_global_warnings(grouped, candidates))
    score_evaluation = build_score_evaluation_summary(grouped, recommend_input)
    result = {
        "trace_id": get_trace_id(),
        "score_evaluation": score_evaluation,
        "recommendations": grouped,
        "warnings": dedupe(warnings),
        "candidate_count": count_unique_schools(candidates),
        "candidate_record_count": len(candidates),
        "returned_count": sum(len(items) for items in grouped.values()),
    }
    result = enrich_recommendation_result(result, recommend_input)
    sort_recommendation_groups_by_score_diff(result["recommendations"])
    enrich_recommendation_markdown(result, recommend_input)
    log_id = save_recommendation_log(recommend_input.payload, result, user_id=user_id)
    result["recommendation_log_id"] = log_id
    return result


def parse_recommend_input(payload: dict[str, Any]) -> RecommendInput:
    score_input = parse_score_input(payload)
    preferred = payload.get("preferred_school_levels") or []
    if isinstance(preferred, str):
        preferred = [preferred]
    if not isinstance(preferred, list):
        raise ValidationError("preferred_school_levels 必须是数组或字符串")
    bucket_limit = payload.get("bucket_limit") or DEFAULT_BUCKET_LIMIT
    try:
        bucket_limit_int = int(bucket_limit)
    except (TypeError, ValueError) as exc:
        raise ValidationError("bucket_limit 必须是整数") from exc
    if bucket_limit_int <= 0:
        raise ValidationError("bucket_limit 必须是正整数")
    return RecommendInput(
        payload=payload,
        target_year=score_input.target_year,
        province=clean_optional_text(payload.get("province")),
        major_category=score_input.major_category,
        major_name=score_input.major_name,
        major_code=score_input.major_code,
        degree_type=score_input.degree_type,
        study_mode=score_input.study_mode,
        preferred_school_levels=[str(item).strip() for item in preferred if str(item).strip()],
        total_score=score_input.total_score,
        politics_score=score_input.politics_score,
        english_score=score_input.english_score,
        subject_one_score=score_input.subject_one_score,
        subject_two_score=score_input.subject_two_score,
        bucket_limit=min(bucket_limit_int, 20),
    )


def query_recommend_candidates(recommend_input: RecommendInput) -> list[dict[str, Any]]:
    clauses = ["sl.year = %(target_year)s", "sl.line_type = 'major'"]
    params: dict[str, Any] = {"target_year": recommend_input.target_year}
    if recommend_input.province:
        clauses.append("u.province = %(province)s")
        params["province"] = recommend_input.province
    if recommend_input.major_code:
        clauses.append("m.major_code = %(major_code)s")
        params["major_code"] = recommend_input.major_code
    if recommend_input.major_name:
        clauses.append("m.major_name LIKE %(major_name)s")
        params["major_name"] = f"%{recommend_input.major_name}%"
    if recommend_input.major_category and not (recommend_input.major_code or recommend_input.major_name):
        clauses.append("(m.major_category = %(major_category)s OR sl.major_category = %(major_category)s)")
        params["major_category"] = recommend_input.major_category
    if recommend_input.degree_type:
        clauses.append("m.degree_type = %(degree_type)s")
        params["degree_type"] = recommend_input.degree_type
    if recommend_input.study_mode:
        clauses.append("m.study_mode = %(study_mode)s")
        params["study_mode"] = recommend_input.study_mode
    if recommend_input.preferred_school_levels:
        level_clauses = []
        for index, level in enumerate(recommend_input.preferred_school_levels):
            key = f"level_{index}"
            level_clauses.append(f"u.school_level LIKE %({key})s")
            params[key] = f"%{level}%"
        clauses.append("(" + " OR ".join(level_clauses) + ")")

    where_sql = " AND ".join(clauses)
    return fetch_all(
        f"""
        SELECT
          sl.id AS score_line_id,
          sl.year,
          sl.line_type,
          sl.total_score_line,
          sl.politics_line,
          sl.english_line,
          sl.subject_one_line,
          sl.subject_two_line,
          sl.score_diff_to_national,
          u.id AS university_id,
          u.candidate_school_id,
          u.university_name,
          u.province,
          u.school_level,
          u.coverage_priority,
          d.id AS department_id,
          d.department_name,
          m.id AS major_id,
          m.major_code,
          m.major_name,
          m.major_category,
          m.degree_type,
          m.study_mode,
          m.research_direction,
          m.exam_subjects,
          ep.plan_count
        FROM score_lines sl
        JOIN universities u ON u.id = sl.university_id
        JOIN departments d ON d.id = sl.department_id
        JOIN majors m ON m.id = sl.major_id
        LEFT JOIN enrollment_plans ep
          ON ep.year = sl.year
         AND ep.university_id = sl.university_id
         AND ep.major_id = sl.major_id
        WHERE {where_sql}
        ORDER BY sl.total_score_line DESC, u.candidate_school_id, m.major_code, m.id
        LIMIT {MAX_CANDIDATES}
        """,
        params,
    )


def build_recommendation_item(
    row: dict[str, Any],
    recommend_input: RecommendInput,
    rules: dict[str, Any],
    thresholds: dict[str, int],
) -> dict[str, Any] | None:
    total_diff = recommend_input.total_score - int(row["total_score_line"])
    single_results = build_single_subject_results(recommend_input, row, thresholds)
    overall_status = build_overall_status(total_diff, single_results, thresholds)
    if overall_status == "unsafe" and not is_acceptable_rush_candidate(total_diff, single_results, rules):
        return None

    rank_type = classify_rank_type(total_diff, overall_status, row, rules)
    plan_history = query_plan_history(int(row["major_id"]), recommend_input.target_year)
    plan_stability_score = calculate_plan_stability_score(plan_history)
    data_quality_score, warnings = calculate_data_quality_score(row, plan_history)
    school_level_score = calculate_school_level_score(row.get("school_level") or "", rules)
    single_subject_safety = 1.0 if all(item["status"] == "safe" for item in single_results) else 0.6
    recommend_score = calculate_recommend_score(
        total_diff=total_diff,
        single_subject_safety=single_subject_safety,
        plan_stability_score=plan_stability_score,
        data_quality_score=data_quality_score,
        school_level_score=school_level_score,
        rules=rules,
    )
    score_line_history = query_score_line_history(int(row["major_id"]), recommend_input.target_year)
    reason = build_reason(row, rank_type, total_diff, plan_history, score_line_history)
    warnings.extend(build_item_warnings(total_diff, single_results, plan_history))

    return {
        "rank_type": rank_type,
        "recommend_score": round(recommend_score, 2),
        "university_id": row["university_id"],
        "candidate_school_id": row["candidate_school_id"],
        "university_name": row["university_name"],
        "department_id": row["department_id"],
        "department_name": row["department_name"],
        "major_id": row["major_id"],
        "major_code": row["major_code"],
        "major_name": row["major_name"],
        "major_category": row["major_category"],
        "degree_type": row["degree_type"],
        "study_mode": row["study_mode"],
        "research_direction": row["research_direction"],
        "reference_years": [item["year"] for item in plan_history],
        "line_type": row["line_type"],
        "score_line": row["total_score_line"],
        "score_line_history": score_line_history,
        "score_diff": total_diff,
        "single_subject_results": single_results,
        "plan_count": row.get("plan_count"),
        "plan_history": plan_history,
        "plan_stability_score": round(plan_stability_score, 2),
        "admission_avg_score": None,
        "admission_min_score": None,
        "admission_avg_diff": None,
        "admission_min_diff": None,
        "data_quality_score": round(data_quality_score, 2),
        "school_level": row.get("school_level"),
        "reason": reason,
        "warnings": dedupe(warnings),
    }


def classify_rank_type(
    total_diff: int,
    overall_status: str,
    row: dict[str, Any],
    rules: dict[str, Any],
) -> str:
    thresholds = rules.get("score_thresholds", {}) if isinstance(rules, dict) else {}
    rush_min = int(thresholds.get("rush_avg_score_diff_min") or -10)
    rush_max = int(thresholds.get("rush_avg_score_diff_max") or 10)
    stable_min = int(thresholds.get("stable_avg_score_diff_min") or 10)
    safe_min = int(thresholds.get("safe_min_score_diff_min") or 25)
    school_level = row.get("school_level") or ""
    if total_diff >= safe_min:
        return "safe"
    if total_diff >= stable_min:
        return "stable"
    if rush_min <= total_diff <= rush_max:
        return "rush"
    if overall_status == "warning":
        return "rush"
    if any(level in school_level for level in ["985", "211", "双一流"]) and total_diff <= safe_min:
        return "rush"
    return "stable"


def is_acceptable_rush_candidate(
    total_diff: int,
    single_results: list[dict[str, Any]],
    rules: dict[str, Any],
) -> bool:
    """允许总分略低于参考线的真实候选进入冲刺档，但单科不能低于线。"""
    thresholds = rules.get("score_thresholds", {}) if isinstance(rules, dict) else {}
    rush_min = int(thresholds.get("rush_avg_score_diff_min") or -10)
    if total_diff < rush_min:
        return False
    return not any(result["diff"] < 0 for result in single_results)


def finalize_grouped_recommendations(
    grouped: dict[str, list[dict[str, Any]]],
    bucket_limit: int,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """按分差直接排序并按学校去重，不跨档位补候选。"""
    warnings: list[str] = []
    finalized: dict[str, list[dict[str, Any]]] = {}
    used_school_ids: set[int] = set()

    for bucket in BUCKET_ORDER:
        unique_items = unique_school_items(grouped.get(bucket, []), bucket)
        kept = []
        for item in unique_items:
            school_id = int(item["candidate_school_id"])
            if school_id in used_school_ids:
                continue
            kept.append(item)
            used_school_ids.add(school_id)
        finalized[bucket] = kept

    for bucket in BUCKET_ORDER:
        finalized[bucket] = finalized[bucket][:bucket_limit]
    return finalized, warnings


def unique_school_items(items: list[dict[str, Any]], rank_type: str) -> list[dict[str, Any]]:
    result = []
    seen_school_ids: set[int] = set()
    for item in sorted(items, key=lambda value: score_diff_sort_key(value, rank_type)):
        school_id = int(item["candidate_school_id"])
        if school_id in seen_school_ids:
            continue
        result.append(item)
        seen_school_ids.add(school_id)
    return result


def sort_recommendation_groups_by_score_diff(grouped: dict[str, list[dict[str, Any]]]) -> None:
    for rank_type in BUCKET_ORDER:
        grouped[rank_type] = sorted(grouped.get(rank_type, []), key=lambda item: score_diff_sort_key(item, rank_type))


def score_diff_sort_key(item: dict[str, Any], rank_type: str) -> tuple[float, int, str]:
    """用“用户总分 - 复试线”的分差排序，避免综合分影响档位展示。"""
    diff = float(item.get("score_diff") or 0)
    plan_count = parse_plan_count(item.get("plan_count"))
    school_name = str(item.get("university_name") or "")
    if rank_type == "rush":
        return (diff, -plan_count, school_name)
    return (-diff, -plan_count, school_name)


def parse_plan_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def count_unique_schools(items: list[dict[str, Any]]) -> int:
    return len({int(item["candidate_school_id"]) for item in items if item.get("candidate_school_id") is not None})


def retag_items(items: list[dict[str, Any]], rank_type: str) -> list[dict[str, Any]]:
    return [retag_item(item, rank_type) for item in items]


def retag_item(item: dict[str, Any], rank_type: str) -> dict[str, Any]:
    copied = dict(item)
    copied["rank_type"] = rank_type
    copied["reason"] = build_reason_from_item(copied, rank_type)
    return copied


def query_plan_history(major_id: int, target_year: int) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT year, plan_count
        FROM enrollment_plans
        WHERE major_id = %(major_id)s
          AND year BETWEEN %(start_year)s AND %(target_year)s
        ORDER BY year
        """,
        {
            "major_id": major_id,
            "start_year": target_year - 2,
            "target_year": target_year,
        },
    )


def query_score_line_history(major_id: int, target_year: int) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT year, total_score_line, politics_line, english_line, subject_one_line, subject_two_line
        FROM score_lines
        WHERE major_id = %(major_id)s
          AND line_type = 'major'
          AND year BETWEEN %(start_year)s AND %(target_year)s
        ORDER BY year
        """,
        {
            "major_id": major_id,
            "start_year": target_year - 2,
            "target_year": target_year,
        },
    )


def calculate_plan_stability_score(plan_history: list[dict[str, Any]]) -> float:
    counts = [int(item["plan_count"]) for item in plan_history if item.get("plan_count") is not None]
    if len(counts) < 2:
        return 60.0 if counts else 40.0
    avg = mean(counts)
    if avg <= 0:
        return 40.0
    volatility = pstdev(counts) / avg
    return max(40.0, min(100.0, 100.0 - volatility * 100.0))


def calculate_data_quality_score(
    row: dict[str, Any],
    plan_history: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    score = 100.0
    warnings = []
    if len(plan_history) < 3:
        score -= 8
        warnings.append("近三年招生计划数据不足 3 年，计划稳定性仅供参考。")
    if row.get("plan_count") is None:
        score -= 5
        warnings.append("当前年份招生计划缺失。")
    return max(0.0, score), warnings


def calculate_school_level_score(school_level: str, rules: dict[str, Any]) -> float:
    bonus = rules.get("school_level_bonus", {}) if isinstance(rules, dict) else {}
    score = 0.0
    for level, value in bonus.items():
        if level in school_level:
            score = max(score, float(value))
    return score


def calculate_recommend_score(
    *,
    total_diff: int,
    single_subject_safety: float,
    plan_stability_score: float,
    data_quality_score: float,
    school_level_score: float,
    rules: dict[str, Any],
) -> float:
    weights = rules.get("weights", {}) if isinstance(rules, dict) else {}
    total_score_component = min(max(total_diff, 0), 60) / 60 * 100
    return (
        total_score_component * float(weights.get("total_score_diff", 0.35))
        + 50.0 * float(weights.get("admission_avg_diff", 0.25))
        + single_subject_safety * 100 * float(weights.get("single_subject_safety", 0.15))
        + plan_stability_score * float(weights.get("plan_stability", 0.15))
        + school_level_score * 10 * float(weights.get("school_level", 0.10))
        + (data_quality_score - 80) * 0.1
    )


def build_reason(
    row: dict[str, Any],
    rank_type: str,
    total_diff: int,
    plan_history: list[dict[str, Any]],
    score_line_history: list[dict[str, Any]],
) -> str:
    rank_text = RANK_LABELS[rank_type]
    plan_count = row.get("plan_count")
    plan_text = f"，当前计划招生 {plan_count} 人" if plan_count is not None else ""
    history_text = (
        f"，近三年可用复试线记录 {len(score_line_history)} 年"
        if score_line_history
        else "，近三年复试线记录不足"
    )
    diff_text = (
        f"总分高出当前参考复试线 {total_diff} 分"
        if total_diff >= 0
        else f"总分低于当前参考复试线 {abs(total_diff)} 分"
    )
    return (
        f"{row['university_name']} {row['major_name']} 可作为{rank_text}目标："
        f"{diff_text}{plan_text}，"
        f"近三年可用计划记录 {len(plan_history)} 年{history_text}。"
    )


def build_reason_from_item(item: dict[str, Any], rank_type: str) -> str:
    rank_text = RANK_LABELS[rank_type]
    total_diff = int(item.get("score_diff") or 0)
    plan_count = item.get("plan_count")
    plan_text = f"，当前计划招生 {plan_count} 人" if plan_count is not None else ""
    diff_text = (
        f"总分高出当前参考复试线 {total_diff} 分"
        if total_diff >= 0
        else f"总分低于当前参考复试线 {abs(total_diff)} 分"
    )
    return (
        f"{item['university_name']} {item['major_name']} 可作为{rank_text}目标："
        f"{diff_text}{plan_text}，该档位基于当前真实候选的相对难度生成。"
    )


def build_item_warnings(
    total_diff: int,
    single_results: list[dict[str, Any]],
    plan_history: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    if total_diff < 0:
        warnings.append(f"总分低于参考线 {abs(total_diff)} 分，仅适合作为冲刺参考。")
    elif total_diff < 10:
        warnings.append("总分与参考线距离较近，建议重点关注复试比例和当年招生变化。")
    for item in single_results:
        if item["status"] == "warning":
            warnings.append(f"{item['subject_name']}单科分差较小。")
    if len(plan_history) < 3:
        warnings.append("计划趋势不足三年，稳定性判断偏保守。")
    return warnings


def build_global_warnings(
    grouped: dict[str, list[dict[str, Any]]],
    candidates: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    if candidates and not any(grouped.values()):
        warnings.append("匹配到专业但成绩未达到可推荐条件，暂不生成具体推荐。")
    if candidates:
        warnings.append("推荐结果基于第三方采集数据和当前入库分数线，仅供择校参考，不构成录取承诺。")
    return warnings


def enrich_recommendation_markdown(result: dict[str, Any], recommend_input: RecommendInput) -> None:
    """为每个推荐学校生成一份可展示的 Markdown 推荐文档。"""
    llm_error: str | None = None
    for rank_type in BUCKET_ORDER:
        for item in result.get("recommendations", {}).get(rank_type, []):
            if not isinstance(item, dict):
                continue
            if llm_error:
                apply_template_recommendation_markdown(item, recommend_input, llm_error)
                continue
            try:
                markdown = call_recommendation_markdown_llm(item, rank_type, recommend_input)
                item["recommendation_markdown"] = normalize_recommendation_markdown(markdown)
                item["recommendation_markdown_source"] = "llm"
                item.pop("recommendation_markdown_error", None)
            except LLMClientError as exc:
                llm_error = str(exc)
                apply_template_recommendation_markdown(item, recommend_input, llm_error)
            except Exception as exc:
                llm_error = str(exc)
                apply_template_recommendation_markdown(item, recommend_input, llm_error)


def call_recommendation_markdown_llm(
    item: dict[str, Any],
    rank_type: str,
    recommend_input: RecommendInput,
) -> str:
    context = build_recommendation_markdown_context(item, rank_type, recommend_input)
    system_prompt = (
        "你是考研择校推荐系统的推荐理由整理助手。"
        "只能基于用户输入、数据库指标和资料核验证据写结论，不能编造学校、分数、招生人数或来源。"
        "输出必须是中文 Markdown，不要使用代码块。"
        "必须包含以下小标题：### 推荐结论、### 分数匹配、### 招生与趋势、### 资料核验、### 风险提示。"
        "语气要客观克制，不得写保证录取、一定上岸等承诺。"
    )
    user_message = (
        "请为下面这一个学校生成一份适合前端卡片展示的 Markdown 推荐分析文档。"
        "每段尽量短，优先使用项目符号。\n\n"
        f"{json.dumps(context, ensure_ascii=False, default=str)}"
    )
    return chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
        max_tokens=900,
    )


def build_recommendation_markdown_context(
    item: dict[str, Any],
    rank_type: str,
    recommend_input: RecommendInput,
) -> dict[str, Any]:
    evidence = item.get("agent_evidence") if isinstance(item.get("agent_evidence"), dict) else {}
    return {
        "user_input": {
            "target_year": recommend_input.target_year,
            "major_category": recommend_input.major_category,
            "major_name": recommend_input.major_name,
            "major_code": recommend_input.major_code,
            "degree_type": recommend_input.degree_type,
            "study_mode": recommend_input.study_mode,
            "total_score": recommend_input.total_score,
            "politics_score": recommend_input.politics_score,
            "english_score": recommend_input.english_score,
            "subject_one_score": recommend_input.subject_one_score,
            "subject_two_score": recommend_input.subject_two_score,
        },
        "recommendation": {
            "rank_type": rank_type,
            "rank_label": RANK_LABELS.get(rank_type, rank_type),
            "university_name": item.get("university_name"),
            "school_level": item.get("school_level"),
            "department_name": item.get("department_name"),
            "major_code": item.get("major_code"),
            "major_name": item.get("major_name"),
            "research_direction": item.get("research_direction"),
            "score_line": item.get("score_line"),
            "score_diff": item.get("score_diff"),
            "plan_count": item.get("plan_count"),
            "plan_history": item.get("plan_history") or [],
            "score_line_history": item.get("score_line_history") or [],
            "single_subject_results": item.get("single_subject_results") or [],
            "plan_stability_score": item.get("plan_stability_score"),
            "data_quality_score": item.get("data_quality_score"),
            "rule_reason": item.get("reason"),
            "warnings": item.get("warnings") or [],
        },
        "evidence": {
            "source_confidence": item.get("source_confidence"),
            "evidence_summary": item.get("evidence_summary"),
            "query": evidence.get("query"),
            "local_rag": summarize_evidence_hits(evidence.get("local_rag") or []),
            "tavily": summarize_evidence_hits(evidence.get("tavily") or []),
        },
    }


def summarize_evidence_hits(hits: Any) -> list[dict[str, Any]]:
    if not isinstance(hits, list):
        return []
    result = []
    for hit in hits[:3]:
        if not isinstance(hit, dict):
            continue
        result.append(
            {
                "title": hit.get("title") or hit.get("document_title") or hit.get("source_title"),
                "url": hit.get("url") or hit.get("source_url"),
                "path": hit.get("path") or hit.get("local_path"),
                "score": hit.get("score"),
                "snippet": compact_markdown_text(hit.get("snippet") or hit.get("content") or hit.get("text"), 180),
            }
        )
    return result


def apply_template_recommendation_markdown(
    item: dict[str, Any],
    recommend_input: RecommendInput,
    error: str | None = None,
) -> None:
    item["recommendation_markdown"] = build_template_recommendation_markdown(item, recommend_input)
    item["recommendation_markdown_source"] = "template"
    if error:
        item["recommendation_markdown_error"] = compact_markdown_text(error, 180)


def build_template_recommendation_markdown(item: dict[str, Any], recommend_input: RecommendInput) -> str:
    rank_label = RANK_LABELS.get(str(item.get("rank_type") or ""), str(item.get("rank_type") or "推荐"))
    score_diff = item.get("score_diff")
    diff_text = format_score_diff(score_diff)
    plan_history = item.get("plan_history") or []
    score_history = item.get("score_line_history") or []
    evidence_summary = item.get("evidence_summary") or "当前没有匹配到明确的资料核验证据，建议以学校官网最新公告为准。"
    warnings = item.get("warnings") or []
    warning_text = "\n".join(f"- {warning}" for warning in warnings) if warnings else "- 暂无额外风险提示，但仍需核对当年官网公告。"
    return "\n".join(
        [
            "### 推荐结论",
            f"- {item.get('university_name', '该院校')} {item.get('major_name', '目标专业')} 当前归入**{rank_label}**参考。",
            f"- 规则结论：{item.get('reason') or '系统根据分数线、招生计划和数据质量综合生成。'}",
            "",
            "### 分数匹配",
            f"- 用户总分：{recommend_input.total_score} 分；当前参考复试线：{item.get('score_line', '暂无')} 分。",
            f"- 总分分差：{diff_text}。",
            f"- 单科判断：{format_single_subject_summary(item.get('single_subject_results') or [])}",
            "",
            "### 招生与趋势",
            f"- 当前招生计划：{item.get('plan_count') if item.get('plan_count') is not None else '暂无'} 人。",
            f"- 招生计划历史：{format_plan_history(plan_history)}",
            f"- 复试线历史：{format_score_line_history(score_history)}",
            "",
            "### 资料核验",
            f"- {evidence_summary}",
            f"- 资料置信度：{format_source_confidence(item.get('source_confidence'))}。",
            "",
            "### 风险提示",
            warning_text,
        ]
    )


def normalize_recommendation_markdown(markdown: str) -> str:
    text = strip_markdown_fence(markdown).strip()
    if not text:
        raise LLMClientError("LLM 未返回推荐 Markdown")
    required_headings = ["### 推荐结论", "### 分数匹配", "### 招生与趋势", "### 资料核验", "### 风险提示"]
    if not any(text.startswith(heading) for heading in required_headings):
        text = "### 推荐结论\n" + text
    for heading in required_headings:
        if heading not in text:
            text += f"\n\n{heading}\n- 暂无补充。"
    return text


def strip_markdown_fence(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


def format_score_diff(value: Any) -> str:
    try:
        diff = int(value)
    except (TypeError, ValueError):
        return "暂无"
    return f"{'+' if diff >= 0 else ''}{diff} 分"


def format_single_subject_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "暂无单科线数据。"
    parts = []
    for item in items:
        parts.append(
            f"{item.get('subject_name') or item.get('subject')} {item.get('score', '暂无')}/{item.get('line', '暂无')}，分差 {format_score_diff(item.get('diff'))}"
        )
    return "；".join(parts) + "。"


def format_plan_history(items: list[dict[str, Any]]) -> str:
    if not items:
        return "暂无近年招生计划记录。"
    return "，".join(f"{item.get('year')}年 {item.get('plan_count', '暂无')}人" for item in items) + "。"


def format_score_line_history(items: list[dict[str, Any]]) -> str:
    if not items:
        return "暂无近年复试线记录。"
    return "，".join(f"{item.get('year')}年 {item.get('total_score_line', '暂无')}分" for item in items) + "。"


def format_source_confidence(value: Any) -> str:
    return {"high": "高", "medium": "中", "low": "低", "unknown": "待核验"}.get(str(value or ""), "待核验")


def compact_markdown_text(value: Any, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def build_score_evaluation_summary(
    grouped: dict[str, list[dict[str, Any]]],
    recommend_input: RecommendInput,
) -> dict[str, Any]:
    all_items = [item for items in grouped.values() for item in items]
    if not all_items:
        return {
            "target_year": recommend_input.target_year,
            "total_score": recommend_input.total_score,
            "best_score_diff": None,
            "min_score_line": None,
            "max_score_line": None,
        }
    return {
        "target_year": recommend_input.target_year,
        "total_score": recommend_input.total_score,
        "best_score_diff": max(item["score_diff"] for item in all_items),
        "min_score_line": min(item["score_line"] for item in all_items),
        "max_score_line": max(item["score_line"] for item in all_items),
    }


def save_recommendation_log(payload: dict[str, Any], result: dict[str, Any], user_id: int | None = None) -> int:
    summary = build_recommendation_log_payload(result)
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO recommendation_logs (
                  user_id, trace_id, request_json, result_summary_json, warning_json
                )
                VALUES (
                  %(user_id)s, %(trace_id)s, %(request_json)s, %(result_summary_json)s, %(warning_json)s
                )
                """,
                {
                    "user_id": user_id,
                    "trace_id": get_trace_id(),
                    "request_json": json.dumps(payload, ensure_ascii=False),
                    "result_summary_json": json.dumps(summary, ensure_ascii=False),
                    "warning_json": json.dumps(result["warnings"], ensure_ascii=False),
                },
            )
            log_id = int(cursor.lastrowid)
        connection.commit()
    return log_id


def dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
