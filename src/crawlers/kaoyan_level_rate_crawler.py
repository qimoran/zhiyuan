"""掌上考研学科评估等级爬虫（开发步骤文档 S03b）。

数据来源
--------
- 接口 POST https://api.kaoyan.cn/pc/school/schoolLevelRate
- 请求参数 school_id，单次返回该校全部一级学科评估等级，无年份、无需分页。
- 学科评估为教育部第四/五轮评估结果，较稳定，单次采集即可。

采集范围
--------
- 重庆 21 所研招单位。

产出
----
- 原始 JSON：data/raw/kaoyan_level_rate/<batch_id>/school_<sid>.json
- 解析 CSV：data/processed/level_rates/level_rates_<batch_id>.csv
  字段对齐 subject_level_rates 表入库需求。

说明
----
评估等级是一级学科维度（如 0802 机械工程 = A-），与具体专业通过
专业代码前 4 位（一级学科代码）关联，作为推荐模块「学科实力」加分项。
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from src.crawlers.base import (
    PROCESSED_BASE_DIR,
    RAW_BASE_DIR,
    post_api,
    save_raw_json,
    sleep_briefly,
)
from src.common.logger import get_logger, setup_logging
from src.common.trace import set_trace_id

logger = get_logger("crawler")

API_PATH = "/pc/school/schoolLevelRate"
TARGET_PAGE_URL = "https://www.kaoyan.cn/school-list/50-0-0"

CHONGQING_SCHOOL_IDS: list[int] = [
    252, 925, 253, 519, 255, 258, 521, 1013, 1230, 951,
    260, 1496, 1379, 871, 524, 1016, 1015, 1645, 1643, 1580, 1529,
]

PROCESSED_DIR = PROCESSED_BASE_DIR / "level_rates"

CSV_FIELDS = [
    "school_id",
    "school_name",
    "subject_code",
    "subject_name",
    "degree_type",
    "degree_type_std",
    "level_rate",
    "rate_sort",
    "has_doctor",
]


def _degree_type_std(value) -> str | None:
    """学位类型标准化：2→academic（学硕为主），1→professional。"""
    try:
        code = int(value)
    except (TypeError, ValueError):
        return None
    if code == 2:
        return "academic"
    if code == 1:
        return "professional"
    return None


def normalize_record(raw: dict, school_id: int, school_name: str) -> dict[str, object]:
    """单条评估记录标准化为 CSV 行。"""
    has_doctor = raw.get("has_doctor")
    try:
        has_doctor_int = int(has_doctor) if has_doctor is not None else 0
    except (TypeError, ValueError):
        has_doctor_int = 0
    return {
        "school_id": school_id,
        "school_name": school_name,
        "subject_code": raw.get("code"),
        "subject_name": raw.get("code_name"),
        "degree_type": raw.get("degree_type"),
        "degree_type_std": _degree_type_std(raw.get("degree_type")),
        "level_rate": raw.get("rate"),
        "rate_sort": raw.get("rate_sort"),
        "has_doctor": has_doctor_int,
    }


def _school_name_map() -> dict[int, str]:
    """school_id→school_name 映射。"""
    body = post_api("/pc/school/schoolList", {"province_id": 50, "page": 1, "limit": 50})
    data = body.get("data", {}).get("data", [])
    return {int(item["school_id"]): item.get("school_name", "") for item in data if item.get("school_id")}


def fetch_school(school_id: int, raw_dir: Path) -> list[dict]:
    """采集单校全部学科评估等级（单次请求，无分页）。"""
    body = post_api(API_PATH, {"school_id": school_id})
    data = body.get("data") or {}
    records = data.get("data") or []
    if records:
        save_raw_json(raw_dir, f"school_{school_id}.json", body)
        logger.info("schoolLevelRate school=%s 共 %s 条", school_id, len(records))
    else:
        logger.info("schoolLevelRate school=%s 无数据", school_id)
    return records


def save_csv(batch_id: str, rows: list[dict]) -> Path:
    """写入标准化 CSV。"""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / f"level_rates_{batch_id}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})
    return path


def run_crawler(school_ids: list[int] | None = None) -> dict[str, object]:
    """运行学科评估爬虫主流程，返回采集摘要。"""
    school_ids = school_ids if school_ids is not None else CHONGQING_SCHOOL_IDS

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    set_trace_id(f"level-{batch_id}")
    raw_dir = RAW_BASE_DIR / "kaoyan_level_rate" / batch_id

    logger.info("开始采集学科评估等级，batch_id=%s，学校数=%s", batch_id, len(school_ids))
    name_map = _school_name_map()

    all_rows: list[dict] = []
    school_stats: list[dict] = []
    failed: list[dict] = []

    for school_id in school_ids:
        school_name = name_map.get(int(school_id), "")
        try:
            records = fetch_school(school_id, raw_dir)
        except RuntimeError as exc:
            logger.error("schoolLevelRate school=%s 采集失败：%s", school_id, exc)
            failed.append({"school_id": school_id, "error": str(exc)})
            sleep_briefly()
            continue

        for raw in records:
            all_rows.append(normalize_record(raw, school_id, school_name))

        school_stats.append({"school_id": school_id, "school_name": school_name, "count": len(records)})
        sleep_briefly()

    csv_path = save_csv(batch_id, all_rows) if all_rows else PROCESSED_DIR

    # 统计各等级分布，便于答辩展示。
    rate_dist: dict[str, int] = {}
    for row in all_rows:
        rate = row.get("level_rate") or "(空)"
        rate_dist[rate] = rate_dist.get(rate, 0) + 1

    summary = {
        "crawler_name": "kaoyan_level_rate",
        "target_url": TARGET_PAGE_URL,
        "api_url": f"https://api.kaoyan.cn{API_PATH}",
        "request_params": {},
        "batch_id": batch_id,
        "status": "success" if all_rows else "failed",
        "school_count": len(school_ids),
        "fetched_count": len(all_rows),
        "rate_distribution": rate_dist,
        "raw_output_path": str(raw_dir),
        "parsed_output_path": str(csv_path),
        "failed": failed,
        "school_stats": school_stats,
    }
    logger.info("学科评估采集完成：%s 条，CSV：%s", len(all_rows), csv_path)
    return summary


def main() -> None:
    """爬虫命令行入口。"""
    setup_logging()
    summary = run_crawler()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
