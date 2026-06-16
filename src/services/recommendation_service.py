"""S10 考研择校推荐服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any

from src.common.config import get_recommend_rules
from src.common.database import fetch_all, mysql_connection
from src.common.exceptions import ValidationError
from src.common.trace import get_trace_id
from src.services.score_service import (
    SUBJECT_SCORE_FIELDS,
    build_overall_status,
    build_single_subject_results,
    get_score_thresholds,
    parse_score_input,
)

DEFAULT_BUCKET_LIMIT = 5
MAX_CANDIDATES = 300


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


def recommend(payload: dict[str, Any]) -> dict[str, Any]:
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

    for key in grouped:
        grouped[key] = sorted(grouped[key], key=lambda item: item["recommend_score"], reverse=True)[
            : recommend_input.bucket_limit
        ]

    warnings.extend(build_global_warnings(grouped, candidates))
    score_evaluation = build_score_evaluation_summary(grouped, recommend_input)
    result = {
        "trace_id": get_trace_id(),
        "score_evaluation": score_evaluation,
        "recommendations": grouped,
        "warnings": dedupe(warnings),
        "candidate_count": len(candidates),
        "returned_count": sum(len(items) for items in grouped.values()),
    }
    log_id = save_recommendation_log(recommend_input.payload, result)
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
    if overall_status == "unsafe":
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
    reason = build_reason(row, rank_type, total_diff, plan_history)
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
        "score_diff": total_diff,
        "single_subject_results": single_results,
        "plan_count": row.get("plan_count"),
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
    warnings = ["当前没有拟录取名单数据，录取均分和最低分暂不能作为依据。"]
    score -= 10
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


def build_reason(row: dict[str, Any], rank_type: str, total_diff: int, plan_history: list[dict[str, Any]]) -> str:
    rank_text = {"rush": "冲刺", "stable": "稳妥", "safe": "保底"}[rank_type]
    plan_count = row.get("plan_count")
    plan_text = f"，当前计划招生 {plan_count} 人" if plan_count is not None else ""
    return (
        f"{row['university_name']} {row['major_name']} 可作为{rank_text}目标："
        f"总分高出当前参考复试线 {total_diff} 分{plan_text}，"
        f"近三年可用计划记录 {len(plan_history)} 年。"
    )


def build_item_warnings(
    total_diff: int,
    single_results: list[dict[str, Any]],
    plan_history: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    if total_diff < 10:
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
        warnings.append("当前没有拟录取名单数据，推荐未使用录取均分和最低分。")
    return warnings


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


def save_recommendation_log(payload: dict[str, Any], result: dict[str, Any]) -> int:
    summary = {
        "candidate_count": result["candidate_count"],
        "returned_count": result["returned_count"],
        "rush": len(result["recommendations"]["rush"]),
        "stable": len(result["recommendations"]["stable"]),
        "safe": len(result["recommendations"]["safe"]),
    }
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO recommendation_logs (
                  trace_id, request_json, result_summary_json, warning_json
                )
                VALUES (
                  %(trace_id)s, %(request_json)s, %(result_summary_json)s, %(warning_json)s
                )
                """,
                {
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
