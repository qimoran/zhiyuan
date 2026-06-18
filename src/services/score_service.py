"""S09 分数线评估服务。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.common.config import get_recommend_rules
from src.common.database import fetch_all
from src.common.exceptions import ValidationError
from src.services.query_service import serialize_row

DEFAULT_TOTAL_WARNING_DIFF = 10
DEFAULT_SINGLE_WARNING_DIFF = 5

SUBJECT_SCORE_FIELDS = {
    "politics": ("politics_score", "politics_line", "政治"),
    "english": ("english_score", "english_line", "英语"),
    "subject_one": ("subject_one_score", "subject_one_line", "业务课一"),
    "subject_two": ("subject_two_score", "subject_two_line", "业务课二"),
}


@dataclass(frozen=True)
class ScoreInput:
    target_year: int
    total_score: int
    major_category: str | None = None
    major_name: str | None = None
    university_id: int | None = None
    school_id: int | None = None
    major_id: int | None = None
    major_code: str | None = None
    degree_type: str | None = None
    study_mode: str | None = None
    politics_score: int | None = None
    english_score: int | None = None
    subject_one_score: int | None = None
    subject_two_score: int | None = None


def evaluate_score(payload: dict[str, Any]) -> dict[str, Any]:
    """评估用户初试成绩相对复试线的风险。"""
    score_input = parse_score_input(payload)
    thresholds = get_score_thresholds()
    warnings: list[str] = []

    line_result = find_reference_line(score_input, warnings)
    if line_result is None:
        return {
            "overall_status": "warning",
            "data_available": False,
            "line_type": None,
            "reference_year": score_input.target_year,
            "total_score_line": None,
            "total_score_diff": None,
            "single_subject_results": [],
            "matched_line_count": 0,
            "reference_line": None,
            "candidate_lines": [],
            "warnings": warnings
            or ["未查询到可用复试线，无法判断过线情况；请更换学校、专业或年份后重试。"],
        }

    reference_line = line_result["reference_line"]
    total_line = int(reference_line["total_score_line"])
    total_diff = score_input.total_score - total_line
    single_results = build_single_subject_results(score_input, reference_line, thresholds)
    overall_status = build_overall_status(total_diff, single_results, thresholds)
    warnings.extend(build_score_warnings(total_diff, single_results, thresholds))

    return {
        "overall_status": overall_status,
        "data_available": True,
        "line_type": reference_line["line_type"],
        "reference_year": reference_line["year"],
        "total_score_line": total_line,
        "total_score_diff": total_diff,
        "single_subject_results": single_results,
        "matched_line_count": line_result["matched_line_count"],
        "reference_strategy": line_result["reference_strategy"],
        "reference_line": serialize_row(reference_line),
        "candidate_lines": [serialize_row(row) for row in line_result["candidate_lines"][:10]],
        "warnings": warnings,
    }


def parse_score_input(payload: dict[str, Any]) -> ScoreInput:
    target_year = parse_int(payload.get("target_year"), "target_year", minimum=2000, maximum=2100)
    major_category = clean_optional_text(payload.get("major_category"))
    major_name = clean_optional_text(payload.get("major_name"))
    university_id = parse_optional_int(payload.get("university_id"), "university_id", minimum=1)
    school_id = parse_optional_int(payload.get("school_id"), "school_id", minimum=1)
    major_id = parse_optional_int(payload.get("major_id"), "major_id", minimum=1)
    major_code = clean_optional_text(payload.get("major_code"))
    degree_type = clean_optional_text(payload.get("degree_type"))
    study_mode = clean_optional_text(payload.get("study_mode"))
    politics_score = parse_optional_score(payload.get("politics_score"), "politics_score")
    english_score = parse_optional_score(payload.get("english_score"), "english_score")
    subject_one_score = parse_optional_score(payload.get("subject_one_score"), "subject_one_score")
    subject_two_score = parse_optional_score(payload.get("subject_two_score"), "subject_two_score")
    total_score = parse_optional_int(payload.get("total_score"), "total_score", minimum=0, maximum=500)

    if not any([major_category, major_name, major_id, major_code]):
        raise ValidationError("major_category、major_name、major_id、major_code 至少填写一个")
    if total_score is None:
        subject_scores = [politics_score, english_score, subject_one_score, subject_two_score]
        if any(score is None for score in subject_scores):
            raise ValidationError("total_score 缺失时必须填写四门单科成绩")
        total_score = sum(score for score in subject_scores if score is not None)
        if total_score > 500:
            raise ValidationError("四门单科成绩合计不能大于 500")

    return ScoreInput(
        target_year=target_year,
        total_score=total_score,
        major_category=major_category,
        major_name=major_name,
        university_id=university_id,
        school_id=school_id,
        major_id=major_id,
        major_code=major_code,
        degree_type=degree_type,
        study_mode=study_mode,
        politics_score=politics_score,
        english_score=english_score,
        subject_one_score=subject_one_score,
        subject_two_score=subject_two_score,
    )


def find_reference_line(score_input: ScoreInput, warnings: list[str]) -> dict[str, Any] | None:
    for line_type in ["major", "university", "national"]:
        candidates = query_score_lines(score_input, line_type)
        if candidates:
            reference = choose_reference_line(candidates)
            strategy = "single_match" if len(candidates) == 1 else "conservative_highest_total_line"
            if len(candidates) > 1:
                warnings.append(
                    f"匹配到 {len(candidates)} 条{line_type}分数线，已按总分线最高值保守评估。"
                )
            return {
                "reference_line": reference,
                "candidate_lines": candidates,
                "matched_line_count": len(candidates),
                "reference_strategy": strategy,
            }
        if line_type == "major":
            warnings.append("未匹配到专业线，尝试回退到院校线。")
        elif line_type == "university":
            warnings.append("未匹配到院校线，尝试回退到国家线。")

    warnings.append("数据库暂无可用国家线，无法继续回退。")
    return None


def query_score_lines(score_input: ScoreInput, line_type: str) -> list[dict[str, Any]]:
    clauses = ["sl.year = %(target_year)s", "sl.line_type = %(line_type)s"]
    params: dict[str, Any] = {
        "target_year": score_input.target_year,
        "line_type": line_type,
    }

    if score_input.university_id:
        clauses.append("u.id = %(university_id)s")
        params["university_id"] = score_input.university_id
    if score_input.school_id:
        clauses.append("u.candidate_school_id = %(school_id)s")
        params["school_id"] = score_input.school_id
    if score_input.major_id:
        clauses.append("m.id = %(major_id)s")
        params["major_id"] = score_input.major_id
    if score_input.major_code:
        clauses.append("m.major_code = %(major_code)s")
        params["major_code"] = score_input.major_code
    if score_input.major_name:
        clauses.append("m.major_name LIKE %(major_name)s")
        params["major_name"] = f"%{score_input.major_name}%"
    has_strong_major_filter = bool(score_input.major_id or score_input.major_code or score_input.major_name)
    if score_input.major_category and not has_strong_major_filter:
        clauses.append("(m.major_category = %(major_category)s OR sl.major_category = %(major_category)s)")
        params["major_category"] = score_input.major_category
    if score_input.degree_type:
        clauses.append("m.degree_type = %(degree_type)s")
        params["degree_type"] = score_input.degree_type
    if score_input.study_mode:
        clauses.append("m.study_mode = %(study_mode)s")
        params["study_mode"] = score_input.study_mode

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
          sl.major_category AS score_major_category,
          u.id AS university_id,
          u.candidate_school_id,
          u.university_name,
          d.id AS department_id,
          d.department_name,
          m.id AS major_id,
          m.major_code,
          m.major_name,
          m.major_category,
          m.degree_type,
          m.study_mode,
          m.research_direction,
          m.exam_subjects
        FROM score_lines sl
        LEFT JOIN universities u ON u.id = sl.university_id
        LEFT JOIN departments d ON d.id = sl.department_id
        LEFT JOIN majors m ON m.id = sl.major_id
        WHERE {where_sql}
        ORDER BY
          sl.total_score_line DESC,
          sl.score_diff_to_national DESC,
          u.candidate_school_id,
          m.major_code,
          sl.id
        LIMIT 50
        """,
        params,
    )


def choose_reference_line(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        candidates,
        key=lambda row: (
            int(row.get("total_score_line") or 0),
            int(row.get("score_diff_to_national") or 0),
            int(row.get("score_line_id") or 0),
        ),
    )


def build_single_subject_results(
    score_input: ScoreInput,
    reference_line: dict[str, Any],
    thresholds: dict[str, int],
) -> list[dict[str, Any]]:
    results = []
    for subject_key, (score_field, line_field, label) in SUBJECT_SCORE_FIELDS.items():
        score = getattr(score_input, score_field)
        line = reference_line.get(line_field)
        if score is None or line is None:
            continue
        line_value = int(line)
        diff = score - line_value
        results.append(
            {
                "subject": subject_key,
                "subject_name": label,
                "score": score,
                "line": line_value,
                "diff": diff,
                "status": score_status(diff, thresholds["single_subject_warning_diff"]),
            }
        )
    return results


def build_overall_status(
    total_diff: int,
    single_results: list[dict[str, Any]],
    thresholds: dict[str, int],
) -> str:
    if total_diff < 0 or any(result["diff"] < 0 for result in single_results):
        return "unsafe"
    if total_diff < thresholds["total_score_warning_diff"]:
        return "warning"
    if any(0 <= result["diff"] < thresholds["single_subject_warning_diff"] for result in single_results):
        return "warning"
    return "safe"


def build_score_warnings(
    total_diff: int,
    single_results: list[dict[str, Any]],
    thresholds: dict[str, int],
) -> list[str]:
    warnings = []
    if total_diff < 0:
        warnings.append(f"总分低于参考线 {abs(total_diff)} 分，风险较高。")
    elif total_diff < thresholds["total_score_warning_diff"]:
        warnings.append(f"总分仅高出参考线 {total_diff} 分，建议谨慎评估。")
    for result in single_results:
        if result["diff"] < 0:
            warnings.append(f"{result['subject_name']}低于参考线 {abs(result['diff'])} 分。")
        elif result["diff"] < thresholds["single_subject_warning_diff"]:
            warnings.append(f"{result['subject_name']}仅高出参考线 {result['diff']} 分。")
    return warnings


def score_status(diff: int, warning_diff: int) -> str:
    if diff < 0:
        return "unsafe"
    if diff < warning_diff:
        return "warning"
    return "safe"


def get_score_thresholds() -> dict[str, int]:
    rules = get_recommend_rules()
    raw = rules.get("score_thresholds", {}) if isinstance(rules, dict) else {}
    return {
        "total_score_warning_diff": int(raw.get("total_score_warning_diff") or DEFAULT_TOTAL_WARNING_DIFF),
        "single_subject_warning_diff": int(
            raw.get("single_subject_warning_diff") or DEFAULT_SINGLE_WARNING_DIFF
        ),
    }


def parse_optional_score(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    return parse_int(value, field_name, minimum=0, maximum=150)


def parse_optional_int(
    value: Any,
    field_name: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    if value is None or value == "":
        return None
    return parse_int(value, field_name, minimum=minimum, maximum=maximum)


def parse_int(
    value: Any,
    field_name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} 必须是整数") from exc
    if minimum is not None and result < minimum:
        raise ValidationError(f"{field_name} 不能小于 {minimum}")
    if maximum is not None and result > maximum:
        raise ValidationError(f"{field_name} 不能大于 {maximum}")
    return result


def clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
