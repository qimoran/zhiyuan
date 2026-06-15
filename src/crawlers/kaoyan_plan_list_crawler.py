"""掌上考研招生计划爬虫：采集专业目录与招生计划（开发步骤文档 S03b）。

数据来源
--------
- 接口 POST https://api.kaoyan.cn/pc/school/planList
- 请求参数 school_id / year / page / limit，按年逐年分页采集。

采集范围
--------
- 遍历掌上考研重庆 21 所研招单位（province_id=50 的 school_id 清单）。
- 默认采集年份 2022—2026（可由 YEARS 配置）。

产出
----
- 原始 JSON：data/raw/kaoyan_plan_list/<batch_id>/school_<sid>_year_<y>_page_<n>.json
- 解析 CSV：data/processed/plans/plan_list_<batch_id>.csv
  字段对齐 departments / majors / enrollment_plans 三表入库需求。

说明
----
planList 的 recruit_number 是「专业招生总数」，不含推免人数拆分；
故 enrollment_plans 的 recommended_exemption_count、unified_exam_count
本爬虫无法提供，入库时置空，由官网 PDF（S05）补充。
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from src.crawlers.base import (
    PAGE_DELAY,
    PROCESSED_BASE_DIR,
    RAW_BASE_DIR,
    major_category_code,
    post_api,
    save_raw_json,
    sleep_briefly,
)
from src.common.logger import get_logger, setup_logging
from src.common.trace import set_trace_id

logger = get_logger("crawler")

API_PATH = "/pc/school/planList"
TARGET_PAGE_URL = "https://www.kaoyan.cn/school-list/50-0-0"

# 重庆 21 所研招单位 school_id（与 schoolList province_id=50 一致）。
CHONGQING_SCHOOL_IDS: list[int] = [
    252, 925, 253, 519, 255, 258, 521, 1013, 1230, 951,
    260, 1496, 1379, 871, 524, 1016, 1015, 1645, 1643, 1580, 1529,
]

# 采集年份：近 5 年。
YEARS: list[int] = [2022, 2023, 2024, 2025, 2026]

PAGE_SIZE = 50
MAX_PAGES = 60  # 单校单年分页保护上限。

PROCESSED_DIR = PROCESSED_BASE_DIR / "plans"

# 解析 CSV 字段：尽量保留接口原值 + 派生标准化字段，供入库映射使用。
CSV_FIELDS = [
    "school_id",
    "school_name",
    "year",
    "plan_id",
    "spe_id",
    "depart_id",
    "depart_name",
    "special_code",
    "special_name",
    "major_category",
    "major_category_code",
    "level1_code",
    "level1_name",
    "level2_code",
    "level2_name",
    "degree_type",
    "degree_type_std",
    "degree_type_name",
    "recruit_type_name",
    "study_mode_std",
    "exam_class",
    "exam_class_name",
    "research_area",
    "exam_subject",
    "exam_subject_clean",
    "recruit_number",
    "remark",
]


def _clean_html(text: str | None) -> str | None:
    """把接口中的 <br/> 替换为换行，去掉首尾空白。"""
    if not text:
        return None
    return text.replace("<br/>", "\n").replace("<br />", "\n").strip()


def _degree_type_std(value) -> str | None:
    """学位类型标准化：1→professional（专硕），2→academic（学硕）。"""
    try:
        code = int(value)
    except (TypeError, ValueError):
        return None
    if code == 1:
        return "professional"
    if code == 2:
        return "academic"
    return None


def _study_mode_std(name: str | None) -> str | None:
    """学习方式标准化：全日制→full_time，非全日制→part_time。"""
    if not name:
        return None
    if "非全" in name:
        return "part_time"
    if "全日" in name:
        return "full_time"
    return None


def normalize_record(raw: dict) -> dict[str, object]:
    """单条 planList 记录标准化为 CSV 行。"""
    code = raw.get("special_code")
    return {
        "school_id": raw.get("school_id"),
        "school_name": raw.get("school_name"),
        "year": raw.get("year"),
        "plan_id": raw.get("plan_id"),
        "spe_id": raw.get("spe_id"),
        "depart_id": raw.get("depart_id"),
        "depart_name": raw.get("depart_name"),
        "special_code": code,
        "special_name": raw.get("special_name"),
        "major_category_code": major_category_code(code),
        "major_category": None,  # 由 load 阶段查 major_category_dict 推导
        "level1_code": raw.get("level1_code"),
        "level1_name": raw.get("level1_name"),
        "level2_code": raw.get("level2_code"),
        "level2_name": raw.get("level2_name"),
        "degree_type": raw.get("degree_type"),
        "degree_type_std": _degree_type_std(raw.get("degree_type")),
        "degree_type_name": raw.get("degree_type_name"),
        "recruit_type_name": raw.get("recruit_type_name"),
        "study_mode_std": _study_mode_std(raw.get("recruit_type_name")),
        "exam_class": raw.get("exam_class"),
        "exam_class_name": raw.get("exam_class_name"),
        "research_area": raw.get("research_area"),
        "exam_subject": raw.get("exam_subject"),
        "exam_subject_clean": _clean_html(raw.get("exam_subject")),
        "recruit_number": raw.get("recruit_number"),
        "remark": raw.get("remark"),
    }


def _school_name_map() -> dict[int, str]:
    """调用 schoolList 取 school_id→school_name 映射，便于 CSV 内嵌学校名。"""
    body = post_api("/pc/school/schoolList", {"province_id": 50, "page": 1, "limit": 50})
    data = body.get("data", {}).get("data", [])
    return {int(item["school_id"]): item.get("school_name", "") for item in data if item.get("school_id")}


def fetch_school_year(school_id: int, year: int, batch_id: str, raw_dir: Path) -> list[dict]:
    """采集单校单年全部 planList，返回原始记录列表。"""
    collected: list[dict] = []
    page = 1
    total: int | None = None
    while page <= MAX_PAGES:
        body = post_api(
            API_PATH,
            {"school_id": school_id, "year": year, "page": page, "limit": PAGE_SIZE},
        )
        data = body.get("data") or {}
        records = data.get("data") or []
        if total is None:
            total = data.get("total")
        if records:
            save_raw_json(
                raw_dir, f"school_{school_id}_year_{year}_page_{page}.json", body
            )
            collected.extend(records)
            logger.info(
                "planList school=%s year=%s 第 %s 页 %s 条，累计 %s/%s",
                school_id, year, page, len(records), len(collected), total,
            )
        else:
            logger.info("planList school=%s year=%s 第 %s 页无数据", school_id, year, page)

        if total and len(collected) >= int(total):
            break
        if not records:
            break
        page += 1
        sleep_briefly()
    return collected


def save_csv(batch_id: str, rows: list[dict]) -> Path:
    """写入标准化 CSV（UTF-8-SIG，便于 Excel 打开）。"""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / f"plan_list_{batch_id}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})
    return path


def run_crawler(
    school_ids: list[int] | None = None,
    years: list[int] | None = None,
) -> dict[str, object]:
    """运行招生计划爬虫主流程，返回采集摘要。"""
    school_ids = school_ids if school_ids is not None else CHONGQING_SCHOOL_IDS
    years = years if years is not None else YEARS

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    set_trace_id(f"plan-{batch_id}")
    raw_dir = RAW_BASE_DIR / "kaoyan_plan_list" / batch_id

    logger.info("开始采集招生计划，batch_id=%s，学校数=%s，年份=%s", batch_id, len(school_ids), years)
    name_map = _school_name_map()

    all_rows: list[dict] = []
    school_stats: list[dict] = []
    failed: list[dict] = []

    for school_id in school_ids:
        school_name = name_map.get(int(school_id), "")
        for year in years:
            try:
                records = fetch_school_year(school_id, year, batch_id, raw_dir)
            except RuntimeError as exc:
                logger.error("planList school=%s year=%s 采集失败：%s", school_id, year, exc)
                failed.append({"school_id": school_id, "year": year, "error": str(exc)})
                sleep_briefly()
                continue

            for raw in records:
                normalized = normalize_record(raw)
                normalized["school_id"] = school_id
                normalized["school_name"] = school_name
                all_rows.append(normalized)

            school_stats.append(
                {"school_id": school_id, "school_name": school_name, "year": year, "count": len(records)}
            )
            sleep_briefly()

    csv_path = save_csv(batch_id, all_rows) if all_rows else PROCESSED_DIR

    summary = {
        "crawler_name": "kaoyan_plan_list",
        "target_url": TARGET_PAGE_URL,
        "api_url": f"https://api.kaoyan.cn{API_PATH}",
        "request_params": {"years": years, "limit": PAGE_SIZE},
        "batch_id": batch_id,
        "status": "success" if all_rows else "failed",
        "school_count": len(school_ids),
        "year_count": len(years),
        "fetched_count": len(all_rows),
        "raw_output_path": str(raw_dir),
        "parsed_output_path": str(csv_path),
        "failed": failed,
        "school_stats": school_stats,
    }
    logger.info(
        "招生计划采集完成：%s 条，CSV：%s，失败批次：%s",
        len(all_rows), csv_path, len(failed),
    )
    return summary


def main() -> None:
    """爬虫命令行入口。"""
    setup_logging()
    summary = run_crawler()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
