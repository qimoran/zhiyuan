"""S12 图表查询服务。

面向 Flask 图表接口提供可视化所需的统计数据，统一输出 ECharts 友好的
结构：``{x_axis, series, warnings, year_range, source_note}``。

设计要点：
- 所有查询均为只读，使用参数化 SQL，避免 SQL 注入。
- 数据为空时返回空数组并附带 ``warnings`` 提示，不抛 500。
- 第三方掌上考研数据仅供参考，每个图表都附 ``source_note`` 数据来源说明。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.common.database import fetch_all
from src.services.query_service import parse_positive_int

# 掌上考研第三方数据来源统一说明，前端可直接展示在图表下方。
SOURCE_NOTE = "数据来源：掌上考研 V2 公开接口，仅供参考，最终以高校官方公布为准。"


def _to_number(value: Any) -> Any:
    """把 Decimal 转成 float，None 保持 None，便于 JSON 序列化。"""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _chart_payload(
    x_axis: list[Any],
    series: list[dict[str, Any]],
    warnings: list[str],
    year_range: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装统一图表结构。"""
    return {
        "x_axis": x_axis,
        "series": series,
        "warnings": warnings,
        "year_range": year_range or {},
        "source_note": SOURCE_NOTE,
    }


def get_line_trend(filters: dict[str, Any]) -> dict[str, Any]:
    """复试线趋势：MySQL 中学校专业历年复试总分走势。

    Query Parameters:
        university_id (int): 学校 ID（数据库主键，必填）
        score_line_major_name (str): score_lines 表中的分数线专业名称

    Returns:
        统一图表结构。``x_axis`` 为年份列表，``series`` 只包含总分线。
    """
    warnings: list[str] = []
    university_id = filters.get("university_id")
    score_line_major_name = str(
        filters.get("score_line_major_name") or filters.get("major_name") or ""
    ).strip()
    if not university_id or not score_line_major_name:
        return _chart_payload([], [], ["缺少学校或专业参数，无法查询复试线趋势。"])

    params: dict[str, Any] = {
        "university_id": parse_positive_int(university_id, "university_id"),
        "score_line_major_name": score_line_major_name,
    }
    rows = fetch_all(
        """
        SELECT
          year,
          MAX(total_score_line) AS total_score_line,
          COUNT(DISTINCT total_score_line) AS distinct_score_count
        FROM score_lines
        WHERE university_id = %(university_id)s
          AND major_category = %(score_line_major_name)s
          AND line_type = 'major'
          AND total_score_line > 0
        GROUP BY year
        ORDER BY year
        """,
        params,
    )
    if not rows:
        warnings.append("暂无该专业历年复试总分线数据，建议结合学校官网公布信息核验。")
        return _chart_payload([], [], warnings)

    years = [row["year"] for row in rows]
    series = [{"name": "总分线", "data": [_to_number(row["total_score_line"]) for row in rows]}]
    if any(int(row.get("distinct_score_count") or 0) > 1 for row in rows):
        warnings.append("同一专业同一年存在多个总分线，图表按最高总分线展示。")
    if len(years) < 2:
        warnings.append("仅有 1 个年份的数据，趋势参考意义有限。")
    return _chart_payload(years, series, warnings, _year_range(years))


def get_admission_score_trend(filters: dict[str, Any]) -> dict[str, Any]:
    """拟录取分数趋势：某学校某专业历年拟录取初试分（最低/平均/最高）。

    Query Parameters:
        university_id (int): 学校 ID（数据库主键，必填）
        major_id (int): 专业 ID（数据库主键，必填）

    Returns:
        统一图表结构。``series`` 含最低分、平均分、最高分三条折线。
        当前项目暂无拟录取明细样例数据时返回空数组并提示。
    """
    warnings: list[str] = []
    university_id = filters.get("university_id")
    major_id = filters.get("major_id")
    if not university_id or not major_id:
        return _chart_payload([], [], ["缺少 university_id 或 major_id 参数，无法查询拟录取分数趋势。"])

    params = {
        "university_id": parse_positive_int(university_id, "university_id"),
        "major_id": parse_positive_int(major_id, "major_id"),
    }
    rows = fetch_all(
        """
        SELECT
          year,
          MIN(initial_total_score) AS min_score,
          AVG(initial_total_score) AS avg_score,
          MAX(initial_total_score) AS max_score,
          COUNT(*) AS record_count
        FROM admission_records
        WHERE university_id = %(university_id)s
          AND major_id = %(major_id)s
          AND initial_total_score IS NOT NULL
        GROUP BY year
        ORDER BY year
        """,
        params,
    )
    if not rows:
        warnings.append("暂无拟录取明细数据，待官网拟录取名单录入后展示。")
        return _chart_payload([], [], warnings)

    years = [row["year"] for row in rows]
    series = [
        {"name": "最低分", "data": [round(_to_number(row["min_score"]), 1) for row in rows]},
        {"name": "平均分", "data": [round(_to_number(row["avg_score"]), 1) for row in rows]},
        {"name": "最高分", "data": [round(_to_number(row["max_score"]), 1) for row in rows]},
    ]
    return _chart_payload(years, series, warnings, _year_range(years))


def get_plan_trend(filters: dict[str, Any]) -> dict[str, Any]:
    """招生计划变化：历年招生计划总量走势。

    Query Parameters:
        university_id (int): 学校 ID（可选，指定后只看该校）
        major_category (str): 专业门类（可选，指定后只看该门类）
        major_code (str): 专业代码（可选，指定后按专业代码聚合）
        major_name (str): 专业名称（可选，指定后按专业名称聚合）

    Returns:
        统一图表结构。``series`` 含招生计划总数和专业记录数量两条数据。
    """
    warnings: list[str] = []
    clauses = ["ep.plan_count IS NOT NULL"]
    params: dict[str, Any] = {}
    if filters.get("university_id"):
        clauses.append("ep.university_id = %(university_id)s")
        params["university_id"] = parse_positive_int(filters["university_id"], "university_id")
    if filters.get("major_category"):
        clauses.append("m.major_category = %(major_category)s")
        params["major_category"] = filters["major_category"]
    if filters.get("major_code"):
        clauses.append("m.major_code = %(major_code)s")
        params["major_code"] = filters["major_code"]
    if filters.get("major_name"):
        clauses.append("m.major_name = %(major_name)s")
        params["major_name"] = filters["major_name"]

    where_sql = "WHERE " + " AND ".join(clauses)
    rows = fetch_all(
        f"""
        SELECT
          ep.year AS year,
          SUM(ep.plan_count) AS total_plan,
          COUNT(DISTINCT ep.major_id) AS major_count
        FROM enrollment_plans ep
        JOIN majors m ON m.id = ep.major_id
        {where_sql}
        GROUP BY ep.year
        ORDER BY ep.year
        """,
        params,
    )
    if not rows:
        warnings.append("暂无符合条件的招生计划数据，请调整筛选条件。")
        return _chart_payload([], [], warnings)

    years = [row["year"] for row in rows]
    series = [
        {"name": "招生计划总数", "data": [int(_to_number(row["total_plan"]) or 0) for row in rows]},
        {"name": "招生专业数", "data": [int(row["major_count"]) for row in rows]},
    ]
    return _chart_payload(years, series, warnings, _year_range(years))


def get_major_heat(filters: dict[str, Any]) -> dict[str, Any]:
    """专业热度：按专业门类统计专业方向数量和招生计划规模。

    Query Parameters:
        year (int): 招生年份（可选，默认取最新有数据的年份）
        top (int): 返回前 N 个门类，默认 10，最大 30

    Returns:
        统一图表结构。``x_axis`` 为专业门类，``series`` 含招生计划总数和
        专业方向数量两组柱状数据，按招生计划总数降序排列。
    """
    warnings: list[str] = []
    top = min(parse_positive_int(filters.get("top") or 10, "top"), 30)
    params: dict[str, Any] = {"top": top}

    year = filters.get("year")
    if year:
        params["year"] = parse_positive_int(year, "year")
    else:
        latest = fetch_one("SELECT MAX(year) AS year FROM enrollment_plans")
        params["year"] = int(latest["year"]) if latest and latest["year"] else None
    if not params["year"]:
        warnings.append("暂无招生计划数据，无法统计专业热度。")
        return _chart_payload([], [], warnings)

    rows = fetch_all(
        """
        SELECT
          m.major_category AS category,
          SUM(ep.plan_count) AS total_plan,
          COUNT(*) AS major_count
        FROM enrollment_plans ep
        JOIN majors m ON m.id = ep.major_id
        WHERE ep.year = %(year)s
          AND m.major_category IS NOT NULL
          AND m.major_category <> ''
        GROUP BY m.major_category
        ORDER BY total_plan DESC, major_count DESC
        LIMIT %(top)s
        """,
        params,
    )
    if not rows:
        warnings.append("该年份暂无专业热度数据。")
        return _chart_payload([], [], warnings)

    categories = [row["category"] for row in rows]
    series = [
        {"name": "招生计划总数", "data": [int(_to_number(row["total_plan"]) or 0) for row in rows]},
        {"name": "专业方向数", "data": [int(row["major_count"]) for row in rows]},
    ]
    return _chart_payload(
        categories,
        series,
        warnings,
        {"min_year": params["year"], "max_year": params["year"]},
    )


def get_university_type(filters: dict[str, Any]) -> dict[str, Any]:
    """学校类型分布：按学校类型和覆盖优先级统计研招单位数量。

    Query Parameters:
        dimension (str): 统计维度，``type``（学校类型，默认）/``priority``
            （覆盖优先级）/``level``（学校层次）。

    Returns:
        统一图表结构。``x_axis`` 为各分类标签，``series`` 含单条数量数据，
        适合渲染为饼图或柱状图。
    """
    warnings: list[str] = []
    dimension = (filters.get("dimension") or "type").strip()
    column_map = {
        "type": ("school_type", "学校类型"),
        "priority": ("coverage_priority", "覆盖优先级"),
        "level": ("school_level", "学校层次"),
    }
    if dimension not in column_map:
        dimension = "type"
    column, series_name = column_map[dimension]

    rows = fetch_all(
        f"""
        SELECT
          COALESCE(NULLIF({column}, ''), '未分类') AS label,
          COUNT(*) AS cnt
        FROM universities
        GROUP BY label
        ORDER BY cnt DESC
        """
    )
    if not rows:
        warnings.append("暂无学校数据。")
        return _chart_payload([], [], warnings)

    labels = [row["label"] for row in rows]
    # 饼图常用 {name, value} 结构，这里同时给出便于前端直接使用。
    pie_data = [{"name": row["label"], "value": int(row["cnt"])} for row in rows]
    series = [
        {
            "name": series_name,
            "data": [int(row["cnt"]) for row in rows],
            "pie_data": pie_data,
        }
    ]
    return _chart_payload(labels, series, warnings)


def _year_range(years: list[Any]) -> dict[str, Any]:
    """根据年份列表生成 year_range 元信息。"""
    if not years:
        return {}
    return {"min_year": min(years), "max_year": max(years)}
