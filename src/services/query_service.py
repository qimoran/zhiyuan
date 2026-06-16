"""S08 基础查询服务。

面向 Flask API 提供学校、专业和来源资料的只读查询能力。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.common.database import fetch_all, fetch_one
from src.common.exceptions import ValidationError

MAX_LIMIT = 200
DEFAULT_LIMIT = 50


def list_universities(filters: dict[str, Any]) -> dict[str, Any]:
    """查询招生单位列表。"""
    limit, offset = parse_pagination(filters)
    where_sql, params = build_university_where(filters)
    items = fetch_all(
        f"""
        SELECT
          id,
          candidate_school_id,
          university_name,
          province,
          city,
          province_area,
          school_type,
          school_org_type,
          school_level,
          coverage_priority,
          official_verified_status,
          recruit_number_reference,
          major_number_reference,
          candidate_source_url,
          candidate_crawled_at,
          remark
        FROM universities
        {where_sql}
        ORDER BY
          FIELD(coverage_priority, 'P0', 'P1', 'P2', 'P3'),
          candidate_school_id,
          id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params | {"limit": limit, "offset": offset},
    )
    total = fetch_total("universities", where_sql, params)
    return paged_response(items, total, limit, offset)


def list_majors(filters: dict[str, Any]) -> dict[str, Any]:
    """查询专业列表，支持学校、年份、专业门类、学习方式等基础筛选。"""
    limit, offset = parse_pagination(filters)
    where_sql, params, join_plan = build_major_where(filters)
    plan_join_sql = "JOIN enrollment_plans ep ON ep.major_id = m.id" if join_plan else ""
    items = fetch_all(
        f"""
        SELECT
          m.id,
          u.id AS university_id,
          u.candidate_school_id,
          u.university_name,
          d.id AS department_id,
          d.department_name,
          m.major_code,
          m.major_name,
          m.major_category,
          m.degree_type,
          m.study_mode,
          m.research_direction,
          m.exam_subjects,
          m.updated_at
        FROM majors m
        JOIN universities u ON u.id = m.university_id
        JOIN departments d ON d.id = m.department_id
        {plan_join_sql}
        {where_sql}
        ORDER BY u.candidate_school_id, d.department_name, m.major_code, m.id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params | {"limit": limit, "offset": offset},
    )
    total_row = fetch_one(
        f"""
        SELECT COUNT(DISTINCT m.id) AS total
        FROM majors m
        JOIN universities u ON u.id = m.university_id
        JOIN departments d ON d.id = m.department_id
        {plan_join_sql}
        {where_sql}
        """,
        params,
    )
    return paged_response(items, int(total_row["total"] if total_row else 0), limit, offset)


def list_sources(filters: dict[str, Any]) -> dict[str, Any]:
    """查询来源资料列表。"""
    limit, offset = parse_pagination(filters)
    where_sql, params = build_source_where(filters)
    items = fetch_all(
        f"""
        SELECT
          s.id,
          u.id AS university_id,
          u.candidate_school_id,
          u.university_name,
          s.year,
          s.document_type,
          s.document_title,
          s.source_url,
          s.local_path,
          s.published_date,
          s.collector,
          s.collected_at,
          s.process_status,
          s.official_verified,
          s.remark
        FROM source_documents s
        JOIN universities u ON u.id = s.university_id
        {where_sql}
        ORDER BY s.collected_at DESC, s.id DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params | {"limit": limit, "offset": offset},
    )
    total_row = fetch_one(
        f"""
        SELECT COUNT(*) AS total
        FROM source_documents s
        JOIN universities u ON u.id = s.university_id
        {where_sql}
        """,
        params,
    )
    return paged_response(items, int(total_row["total"] if total_row else 0), limit, offset)


def get_health_detail() -> dict[str, Any]:
    """返回 S08 健康检查附加统计。"""
    row = fetch_one(
        """
        SELECT
          (SELECT COUNT(*) FROM universities) AS universities,
          (SELECT COUNT(*) FROM majors) AS majors,
          (SELECT COUNT(*) FROM enrollment_plans) AS enrollment_plans,
          (SELECT COUNT(*) FROM score_lines) AS score_lines,
          (SELECT COUNT(*) FROM source_documents) AS source_documents
        """
    )
    return serialize_row(row or {})


def build_university_where(filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if filters.get("coverage_priority"):
        clauses.append("coverage_priority = %(coverage_priority)s")
        params["coverage_priority"] = filters["coverage_priority"]
    if filters.get("official_verified_status"):
        clauses.append("official_verified_status = %(official_verified_status)s")
        params["official_verified_status"] = filters["official_verified_status"]
    if filters.get("school_type"):
        clauses.append("school_type = %(school_type)s")
        params["school_type"] = filters["school_type"]
    if filters.get("school_org_type"):
        clauses.append("school_org_type = %(school_org_type)s")
        params["school_org_type"] = filters["school_org_type"]
    if filters.get("keyword"):
        clauses.append("university_name LIKE %(keyword)s")
        params["keyword"] = f"%{filters['keyword']}%"
    return where_clause(clauses), params


def build_major_where(filters: dict[str, Any]) -> tuple[str, dict[str, Any], bool]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    join_plan = False
    if filters.get("university_id"):
        clauses.append("u.id = %(university_id)s")
        params["university_id"] = parse_positive_int(filters["university_id"], "university_id")
    if filters.get("school_id"):
        clauses.append("u.candidate_school_id = %(school_id)s")
        params["school_id"] = parse_positive_int(filters["school_id"], "school_id")
    if filters.get("year"):
        join_plan = True
        clauses.append("ep.year = %(year)s")
        params["year"] = parse_positive_int(filters["year"], "year")
    if filters.get("major_category"):
        clauses.append("m.major_category = %(major_category)s")
        params["major_category"] = filters["major_category"]
    if filters.get("degree_type"):
        clauses.append("m.degree_type = %(degree_type)s")
        params["degree_type"] = filters["degree_type"]
    if filters.get("study_mode"):
        clauses.append("m.study_mode = %(study_mode)s")
        params["study_mode"] = filters["study_mode"]
    if filters.get("major_code"):
        clauses.append("m.major_code = %(major_code)s")
        params["major_code"] = filters["major_code"]
    if filters.get("keyword"):
        clauses.append("(m.major_name LIKE %(keyword)s OR m.research_direction LIKE %(keyword)s)")
        params["keyword"] = f"%{filters['keyword']}%"
    return where_clause(clauses), params, join_plan


def build_source_where(filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if filters.get("university_id"):
        clauses.append("u.id = %(university_id)s")
        params["university_id"] = parse_positive_int(filters["university_id"], "university_id")
    if filters.get("school_id"):
        clauses.append("u.candidate_school_id = %(school_id)s")
        params["school_id"] = parse_positive_int(filters["school_id"], "school_id")
    if filters.get("year"):
        clauses.append("s.year = %(year)s")
        params["year"] = parse_positive_int(filters["year"], "year")
    if filters.get("document_type"):
        clauses.append("s.document_type = %(document_type)s")
        params["document_type"] = filters["document_type"]
    if filters.get("process_status"):
        clauses.append("s.process_status = %(process_status)s")
        params["process_status"] = filters["process_status"]
    return where_clause(clauses), params


def fetch_total(table_name: str, where_sql: str, params: dict[str, Any]) -> int:
    row = fetch_one(f"SELECT COUNT(*) AS total FROM {table_name} {where_sql}", params)
    return int(row["total"] if row else 0)


def where_clause(clauses: list[str]) -> str:
    return "WHERE " + " AND ".join(clauses) if clauses else ""


def parse_pagination(filters: dict[str, Any]) -> tuple[int, int]:
    limit = parse_positive_int(filters.get("limit") or DEFAULT_LIMIT, "limit")
    offset = parse_non_negative_int(filters.get("offset") or 0, "offset")
    return min(limit, MAX_LIMIT), offset


def parse_positive_int(value: Any, field_name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} 必须是正整数") from exc
    if result <= 0:
        raise ValidationError(f"{field_name} 必须是正整数")
    return result


def parse_non_negative_int(value: Any, field_name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} 必须是非负整数") from exc
    if result < 0:
        raise ValidationError(f"{field_name} 必须是非负整数")
    return result


def paged_response(items: list[dict[str, Any]], total: int, limit: int, offset: int) -> dict[str, Any]:
    return {
        "items": [serialize_row(item) for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }


def serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: serialize_value(value) for key, value in row.items()}


def serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value
