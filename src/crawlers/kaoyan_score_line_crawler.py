"""掌上考研历年分数线爬虫（开发步骤文档 S03b）。

数据来源
--------
- 接口 POST https://api.kaoyan.cn/pc/school/schoolScore
- 请求参数 school_id / year，单次返回该校该年全部分数线，无需分页。
- 必须传 year，否则接口返回 0 条。

采集范围
--------
- 重庆 21 所研招单位。
- 默认采集年份 2020—2026（近 7 年）。

数据分类
--------
接口返回两类数据，由 data_type 区分：
- score_level：学校按学科门类划的校线 → 入库 line_type = university
- school_score：具体院系专业的复试线 → 入库 line_type = major
两类数据均自带 diff_total 等字段（超出国家线分差），对推荐算法有价值。

产出
----
- 原始 JSON：data/raw/kaoyan_score_line/<batch_id>/school_<sid>_year_<y>.json
- 解析 CSV：data/processed/score_lines/score_lines_<batch_id>.csv
  字段对齐 score_lines 表入库需求，含 score_diff_to_national。
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from src.crawlers.base import (
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

API_PATH = "/pc/school/schoolScore"
TARGET_PAGE_URL = "https://www.kaoyan.cn/school-list/50-0-0"

CHONGQING_SCHOOL_IDS: list[int] = [
    252, 925, 253, 519, 255, 258, 521, 1013, 1230, 951,
    260, 1496, 1379, 871, 524, 1016, 1015, 1645, 1643, 1580, 1529,
]

# 分数线采集年份：近 7 年（schoolScore 必须传 year，2020—2026 均有数据）。
YEARS: list[int] = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

PROCESSED_DIR = PROCESSED_BASE_DIR / "score_lines"

CSV_FIELDS = [
    "school_id",
    "school_name",
    "year",
    "data_type",
    "line_type_std",
    "depart_id",
    "depart_name",
    "code",
    "major_category_code",
    "name",
    "degree_type",
    "total",
    "politics",
    "english",
    "special_one",
    "special_two",
    "score_diff_to_national",
    "diff_politics",
    "diff_english",
    "note",
    "special_remark",
]


def _line_type_std(data_type: str | None) -> str | None:
    """分数线类型标准化：score_level→university，school_score→major。"""
    if data_type == "score_level":
        return "university"
    if data_type == "school_score":
        return "major"
    return None


def normalize_record(raw: dict) -> dict[str, object]:
    """单条 schoolScore 记录标准化为 CSV 行。"""
    code = raw.get("code")
    return {
        "school_id": raw.get("school_id"),
        "school_name": raw.get("school_name"),
        "year": raw.get("year"),
        "data_type": raw.get("data_type"),
        "line_type_std": _line_type_std(raw.get("data_type")),
        "depart_id": raw.get("depart_id"),
        "depart_name": raw.get("depart_name"),
        "code": code,
        "major_category_code": major_category_code(code),
        "name": raw.get("name"),
        "degree_type": raw.get("degree_type"),
        "total": raw.get("total"),
        "politics": raw.get("politics"),
        "english": raw.get("english"),
        "special_one": raw.get("special_one"),
        "special_two": raw.get("special_two"),
        "score_diff_to_national": raw.get("diff_total"),
        "diff_politics": raw.get("diff_politics"),
        "diff_english": raw.get("diff_english"),
        "note": raw.get("note"),
        "special_remark": raw.get("special_remark"),
    }


def _school_name_map() -> dict[int, str]:
    """school_id→school_name 映射。"""
    body = post_api("/pc/school/schoolList", {"province_id": 50, "page": 1, "limit": 50})
    data = body.get("data", {}).get("data", [])
    return {int(item["school_id"]): item.get("school_name", "") for item in data if item.get("school_id")}


def fetch_school_year(school_id: int, year: int, raw_dir: Path) -> list[dict]:
    """采集单校单年全部 schoolScore（单次请求，无分页）。"""
    body = post_api(API_PATH, {"school_id": school_id, "year": year})
    data = body.get("data") or []
    if data:
        save_raw_json(raw_dir, f"school_{school_id}_year_{year}.json", body)
        logger.info("schoolScore school=%s year=%s 共 %s 条", school_id, year, len(data))
    else:
        logger.info("schoolScore school=%s year=%s 无数据", school_id, year)
    return data


def save_csv(batch_id: str, rows: list[dict]) -> Path:
    """写入标准化 CSV。"""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / f"score_lines_{batch_id}.csv"
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
    """运行分数线爬虫主流程，返回采集摘要。"""
    school_ids = school_ids if school_ids is not None else CHONGQING_SCHOOL_IDS
    years = years if years is not None else YEARS

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    set_trace_id(f"score-{batch_id}")
    raw_dir = RAW_BASE_DIR / "kaoyan_score_line" / batch_id

    logger.info("开始采集历年分数线，batch_id=%s，学校数=%s，年份=%s", batch_id, len(school_ids), years)
    name_map = _school_name_map()

    all_rows: list[dict] = []
    school_stats: list[dict] = []
    failed: list[dict] = []

    for school_id in school_ids:
        school_name = name_map.get(int(school_id), "")
        for year in years:
            try:
                records = fetch_school_year(school_id, year, raw_dir)
            except RuntimeError as exc:
                logger.error("schoolScore school=%s year=%s 采集失败：%s", school_id, year, exc)
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

    # 统计两类分数线占比，便于答辩展示数据构成。
    university_count = sum(1 for r in all_rows if r.get("line_type_std") == "university")
    major_count = sum(1 for r in all_rows if r.get("line_type_std") == "major")

    summary = {
        "crawler_name": "kaoyan_score_line",
        "target_url": TARGET_PAGE_URL,
        "api_url": f"https://api.kaoyan.cn{API_PATH}",
        "request_params": {"years": years},
        "batch_id": batch_id,
        "status": "success" if all_rows else "failed",
        "school_count": len(school_ids),
        "year_count": len(years),
        "fetched_count": len(all_rows),
        "university_line_count": university_count,
        "major_line_count": major_count,
        "raw_output_path": str(raw_dir),
        "parsed_output_path": str(csv_path),
        "failed": failed,
        "school_stats": school_stats,
    }
    logger.info(
        "历年分数线采集完成：%s 条（校线 %s / 专业线 %s），CSV：%s",
        len(all_rows), university_count, major_count, csv_path,
    )
    return summary


def main() -> None:
    """爬虫命令行入口。"""
    setup_logging()
    summary = run_crawler()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
