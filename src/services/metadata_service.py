"""元数据查询服务。

提供专业门类、学位类型、学习方式等枚举数据的查询接口。
"""

from __future__ import annotations

import re
from typing import Any

from src.common.database import fetch_all
from src.common.exceptions import ValidationError

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def _parse_school_id(value: Any) -> int:
    try:
        school_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("school_id 必须是正整数") from exc
    if school_id <= 0:
        raise ValidationError("school_id 必须是正整数")
    return school_id


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
