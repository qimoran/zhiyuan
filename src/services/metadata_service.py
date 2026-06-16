"""元数据查询服务。

提供专业门类、学位类型、学习方式等枚举数据的查询接口。
"""

from __future__ import annotations

from src.common.database import fetch_all


def list_major_categories() -> dict[str, list[str]]:
    """查询所有专业门类列表。

    Returns:
        {
            "from_majors": [...],      # 从 majors 表提取的专业门类
            "from_score_lines": [...], # 从 score_lines 表提取的专业门类
            "from_national_lines": [...] # 从国家线提取的专业门类
        }
    """
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

    return {
        "from_majors": [row['major_category'] for row in majors_categories],
        "from_score_lines": [row['major_category'] for row in score_categories],
        "from_national_lines": [row['major_category'] for row in national_categories],
        "combined": sorted(set(
            [row['major_category'] for row in majors_categories] +
            [row['major_category'] for row in score_categories] +
            [row['major_category'] for row in national_categories]
        ))
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
