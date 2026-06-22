"""元数据查询服务。

提供专业门类、学位类型、学习方式等枚举数据的查询接口。
"""

from __future__ import annotations

import re
from typing import Any

from src.common.database import fetch_all
from src.common.exceptions import ValidationError

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
MAX_PLAN_MAJOR_OPTIONS = 1000
MAX_SCORE_LINE_MAJOR_OPTIONS = 1000


def _parse_positive_int(value: Any, field_name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} 必须是正整数") from exc
    if result <= 0:
        raise ValidationError(f"{field_name} 必须是正整数")
    return result


def _parse_school_id(value: Any) -> int:
    return _parse_positive_int(value, "school_id")


def _parse_university_id(value: Any) -> int:
    return _parse_positive_int(value, "university_id")


def _is_readable_major_category(value: str | None) -> bool:
    """过滤数据库里混入的乱码专业门类。"""
    if not value:
        return False

    text = value.strip()
    if not text or not _CJK_PATTERN.search(text):
        return False

    # 常见的 UTF-8 被按 latin1/GBK 误解码后会出现这些字符区间。
    if "\ufffd" in text or any("\u00a0" <= char <= "\u00ff" for char in text):
        return False

    return True


def _clean_major_categories(rows: list[dict[str, str]]) -> list[str]:
    categories = {
        row["major_category"].strip()
        for row in rows
        if _is_readable_major_category(row.get("major_category"))
    }
    return sorted(categories)


def list_major_categories(filters: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """查询所有专业门类列表。

    Returns:
        {
            "from_majors": [...],      # 从 majors 表提取的专业门类
            "from_score_lines": [...], # 从 score_lines 表提取的专业门类
            "from_national_lines": [...] # 从国家线提取的专业门类
        }
    """
    filters = filters or {}
    if filters.get("school_id"):
        school_id = _parse_school_id(filters["school_id"])
        majors_categories = fetch_all(
            """
            SELECT DISTINCT m.major_category
            FROM majors m
            JOIN universities u ON u.id = m.university_id
            WHERE m.major_category IS NOT NULL
              AND u.candidate_school_id = %(school_id)s
            ORDER BY m.major_category
            """,
            {"school_id": school_id},
        )
        from_majors = _clean_major_categories(majors_categories)
        return {
            "from_majors": from_majors,
            "from_score_lines": [],
            "from_national_lines": [],
            "combined": from_majors,
        }

    # 从 majors 表获取专业门类
    majors_categories = fetch_all(
        """
        SELECT DISTINCT major_category
        FROM majors
        WHERE major_category IS NOT NULL
        ORDER BY major_category
        """
    )

    # 从 score_lines (专业线) 获取专业门类
    score_categories = fetch_all(
        """
        SELECT DISTINCT major_category
        FROM score_lines
        WHERE line_type = 'major'
          AND major_category IS NOT NULL
        ORDER BY major_category
        """
    )

    # 从 score_lines (国家线) 获取专业门类
    national_categories = fetch_all(
        """
        SELECT DISTINCT major_category
        FROM score_lines
        WHERE line_type = 'national'
          AND major_category IS NOT NULL
        ORDER BY major_category
        """
    )

    from_majors = _clean_major_categories(majors_categories)
    from_score_lines = _clean_major_categories(score_categories)
    from_national_lines = _clean_major_categories(national_categories)

    return {
        "from_majors": from_majors,
        "from_score_lines": from_score_lines,
        "from_national_lines": from_national_lines,
        "combined": sorted(set(from_majors + from_score_lines + from_national_lines)),
    }


def list_plan_major_options(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """查询有招生计划数据的专业选项，供图表筛选使用。"""
    filters = filters or {}
    limit = min(_parse_positive_int(filters.get("limit") or MAX_PLAN_MAJOR_OPTIONS, "limit"), MAX_PLAN_MAJOR_OPTIONS)
    clauses = [
        "ep.plan_count IS NOT NULL",
        "m.major_code IS NOT NULL",
        "m.major_code <> ''",
        "m.major_name IS NOT NULL",
        "m.major_name <> ''",
    ]
    params: dict[str, Any] = {"limit": limit}

    if filters.get("major_category"):
        clauses.append("m.major_category = %(major_category)s")
        params["major_category"] = filters["major_category"]
    if filters.get("school_id"):
        clauses.append("u.candidate_school_id = %(school_id)s")
        params["school_id"] = _parse_school_id(filters["school_id"])

    rows = fetch_all(
        f"""
        SELECT
          m.major_code,
          m.major_name,
          COALESCE(NULLIF(m.major_category, ''), '未分类') AS major_category,
          SUM(ep.plan_count) AS total_plan,
          COUNT(DISTINCT ep.year) AS year_count,
          COUNT(DISTINCT ep.major_id) AS major_count
        FROM enrollment_plans ep
        JOIN majors m ON m.id = ep.major_id
        JOIN universities u ON u.id = ep.university_id
        WHERE {" AND ".join(clauses)}
        GROUP BY m.major_code, m.major_name, major_category
        ORDER BY total_plan DESC, major_count DESC, m.major_code, m.major_name
        LIMIT %(limit)s
        """,
        params,
    )

    items = [
        {
            "major_code": row["major_code"],
            "major_name": row["major_name"],
            "major_category": row["major_category"],
            "total_plan": int(row["total_plan"] or 0),
            "year_count": int(row["year_count"] or 0),
            "major_count": int(row["major_count"] or 0),
        }
        for row in rows
    ]
    return {"items": items, "total": len(items), "limit": limit}


def list_score_line_major_options(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """查询有复试总分线数据的学校专业选项。

    复试线图表以 score_lines 表中的专业名称为准，不使用专业目录表中的
    方向级专业记录，避免专业选项缺失或口径不一致。
    """
    filters = filters or {}
    university_id = _parse_university_id(filters.get("university_id"))
    limit = min(
        _parse_positive_int(filters.get("limit") or MAX_SCORE_LINE_MAJOR_OPTIONS, "limit"),
        MAX_SCORE_LINE_MAJOR_OPTIONS,
    )
    rows = fetch_all(
        """
        SELECT
          sl.major_category AS score_line_major_name,
          COUNT(DISTINCT sl.year) AS year_count,
          MIN(sl.year) AS min_year,
          MAX(sl.year) AS max_year,
          COUNT(*) AS score_line_count
        FROM score_lines sl
        WHERE sl.university_id = %(university_id)s
          AND sl.line_type = 'major'
          AND sl.total_score_line > 0
          AND sl.major_category IS NOT NULL
          AND sl.major_category <> ''
        GROUP BY sl.major_category
        ORDER BY sl.major_category
        LIMIT %(limit)s
        """,
        {"university_id": university_id, "limit": limit},
    )

    items = [
        {
            "score_line_major_name": row["score_line_major_name"],
            "year_count": int(row["year_count"] or 0),
            "min_year": row["min_year"],
            "max_year": row["max_year"],
            "score_line_count": int(row["score_line_count"] or 0),
        }
        for row in rows
    ]
    return {"items": items, "total": len(items), "limit": limit}


def list_degree_types() -> list[dict[str, str]]:
    """查询学位类型枚举。

    Returns:
        [
            {"value": "academic", "label": "学术学位（学硕）"},
            {"value": "professional", "label": "专业学位（专硕）"}
        ]
    """
    return [
        {"value": "academic", "label": "学术学位（学硕）"},
        {"value": "professional", "label": "专业学位（专硕）"}
    ]


def list_study_modes() -> list[dict[str, str]]:
    """查询学习方式枚举。

    Returns:
        [
            {"value": "full_time", "label": "全日制"},
            {"value": "part_time", "label": "非全日制"}
        ]
    """
    return [
        {"value": "full_time", "label": "全日制"},
        {"value": "part_time", "label": "非全日制"}
    ]


def list_school_levels() -> list[dict[str, str]]:
    """查询学校层次枚举。

    Returns:
        [
            {"value": "985", "label": "985工程"},
            {"value": "211", "label": "211工程"},
            ...
        ]
    """
    # 从数据库实际数据中提取
    rows = fetch_all(
        """
        SELECT DISTINCT school_level
        FROM universities
        WHERE school_level IS NOT NULL
        ORDER BY school_level
        """
    )

    return [
        {"value": row['school_level'], "label": row['school_level']}
        for row in rows
    ]


def search_major_categories(keyword: str, limit: int = 12) -> list[str]:
    """模糊搜索专业门类。

    Args:
        keyword: 搜索关键词（至少 1 个字符）
        limit: 返回条数，默认 12

    Returns:
        匹配的专业门类列表，按字符串长度排序（短的在前）

    Examples:
        search_major_categories("计算") -> ["计算机技术", "计算机科学与技术"]
        search_major_categories("工") -> ["工学", "工商管理", "工程管理"]
    """
    if not keyword or not keyword.strip():
        return []

    keyword = keyword.strip()
    limit = max(1, min(limit, 50))

    # 从三个来源查询：majors 表、专业线、国家线
    rows = fetch_all(
        """
        SELECT DISTINCT major_category
        FROM (
            SELECT major_category FROM majors WHERE major_category LIKE %(pattern)s
            UNION
            SELECT major_category FROM score_lines
            WHERE line_type = 'major' AND major_category LIKE %(pattern)s
            UNION
            SELECT major_category FROM score_lines
            WHERE line_type = 'national' AND major_category LIKE %(pattern)s
        ) AS combined
        WHERE major_category IS NOT NULL AND major_category <> ''
        ORDER BY LENGTH(major_category), major_category
        LIMIT %(limit)s
        """,
        {"pattern": f"%{keyword}%", "limit": limit}
    )

    categories = [
        row["major_category"].strip()
        for row in rows
        if _is_readable_major_category(row.get("major_category"))
    ]

    return categories


def search_major_names(
    keyword: str,
    limit: int = 12,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """模糊搜索专业名称。

    Args:
        keyword: 搜索关键词（至少 1 个字符）
        limit: 返回条数，默认 12

    Returns:
        [
            {
                "major_name": "计算机技术",
                "major_code": "085404",
                "major_category": "电子信息",
                "match_count": 15  # 该专业在多少个学校出现
            }
        ]

    Examples:
        search_major_names("计算机") -> [
            {"major_name": "计算机技术", "major_code": "085404", ...},
            {"major_name": "计算机科学与技术", "major_code": "081200", ...}
        ]
    """
    if not keyword or not keyword.strip():
        return []

    filters = filters or {}
    keyword = keyword.strip()
    limit = max(1, min(limit, 50))
    clauses = [
        "m.major_name LIKE %(pattern)s",
        "m.major_name IS NOT NULL",
        "m.major_name <> ''",
    ]
    params: dict[str, Any] = {"pattern": f"%{keyword}%", "limit": limit}

    if filters.get("major_category"):
        clauses.append("(m.major_category LIKE %(major_category)s OR m.major_name LIKE %(major_category)s)")
        params["major_category"] = f"%{str(filters['major_category']).strip()}%"
    if filters.get("degree_type"):
        clauses.append("m.degree_type = %(degree_type)s")
        params["degree_type"] = str(filters["degree_type"]).strip()
    if filters.get("study_mode"):
        clauses.append("m.study_mode = %(study_mode)s")
        params["study_mode"] = str(filters["study_mode"]).strip()
    if filters.get("target_year"):
        clauses.append("ep.year = %(target_year)s")
        params["target_year"] = _parse_positive_int(filters["target_year"], "target_year")

    rows = fetch_all(
        f"""
        SELECT
            m.major_name,
            m.major_code,
            COALESCE(NULLIF(m.major_category, ''), '未分类') AS major_category,
            COUNT(DISTINCT m.university_id) AS match_count,
            SUM(COALESCE(ep.plan_count, 0)) AS total_plan
        FROM majors m
        LEFT JOIN enrollment_plans ep ON ep.major_id = m.id
        WHERE {" AND ".join(clauses)}
        GROUP BY m.major_name, m.major_code, major_category
        ORDER BY total_plan DESC, match_count DESC, LENGTH(m.major_name), m.major_name
        LIMIT %(limit)s
        """,
        params,
    )

    return [
        {
            "major_name": row["major_name"],
            "major_code": row["major_code"] or "",
            "major_category": row["major_category"],
            "match_count": int(row["match_count"] or 0),
            "total_plan": int(row["total_plan"] or 0),
        }
        for row in rows
    ]
