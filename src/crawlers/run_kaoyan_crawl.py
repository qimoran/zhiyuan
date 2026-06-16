"""掌上考研 V2 总入口：调用分块爬虫并生成统一最大 CSV。"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.common.logger import get_logger, setup_logging
from src.common.trace import set_trace_id
from src.crawlers.kaoyan_v2_common import (
    DEFAULT_YEARS,
    DETAIL_BACKOFF_ROUNDS,
    DETAIL_DELAY,
    PROCESSED_DIR,
    acquire_batch_lock,
    clean_html,
    clean_text,
    degree_type_std,
    json_compact,
    make_batch_id,
    project_relative,
    province_area,
    raw_batch_dir,
    save_json,
    school_level,
    study_mode_std,
    to_int,
)
from src.crawlers.level_rate_crawler import fetch_level_rates
from src.crawlers.plan_detail_v2_crawler import fetch_plan_detail_v2
from src.crawlers.plan_list_v2_crawler import fetch_plan_list_v2
from src.crawlers.school_list_crawler import fetch_school_list
from src.crawlers.score_line_crawler import fetch_score_lines

logger = get_logger("crawler")

CSV_FIELDS = [
    "batch_id",
    "source_api",
    "source_status",
    "error_message",
    "school_id",
    "school_name",
    "province_name",
    "city",
    "province_area",
    "type_name",
    "type_school_name",
    "is_985",
    "is_211",
    "syl",
    "is_zihuaxian",
    "school_level",
    "school_recruit_number_reference",
    "school_major_number_reference",
    "rk_rank",
    "year",
    "plan_id",
    "spe_id",
    "depart_id",
    "depart_name",
    "special_code",
    "special_name",
    "major_category_code",
    "level1_code",
    "level1_name",
    "level2_code",
    "level2_name",
    "degree_type",
    "degree_type_std",
    "degree_type_name",
    "recruit_type",
    "recruit_type_name",
    "study_mode_std",
    "exam_class",
    "exam_class_name",
    "research_area",
    "exam_subject",
    "exam_subject_clean",
    "research_area_note",
    "is_statistic_direction",
    "exam_book",
    "exam_book_clean",
    "exam_book_year",
    "intro_id",
    "plan_recruit_number",
    "plan_remark",
    "min_score",
    "score_years_json",
    "major_rate",
    "doctoral_point",
    "score_data_type",
    "score_line_type",
    "score_depart_id",
    "score_depart_name",
    "score_code",
    "score_name",
    "score_degree_type",
    "score_total",
    "score_politics",
    "score_english",
    "score_special_one",
    "score_special_two",
    "score_diff_to_national",
    "score_diff_politics",
    "score_diff_english",
    "score_note",
    "score_special_remark",
    "subject_code",
    "subject_name",
    "subject_degree_type",
    "subject_degree_type_std",
    "level_rate",
    "rate_sort",
    "has_doctor",
]


def run_crawl(
    *,
    batch_id: str | None = None,
    years: list[int] | None = None,
    sample_schools: int | None = 2,
    full: bool = False,
    resume: bool = False,
    detail_delay: float = DETAIL_DELAY,
    detail_backoff_rounds: int = DETAIL_BACKOFF_ROUNDS,
) -> dict[str, Any]:
    """运行 V2 采集总流程。"""
    batch_id = batch_id or make_batch_id()
    years = years or DEFAULT_YEARS
    with acquire_batch_lock(batch_id):
        return _run_crawl_unlocked(
            batch_id=batch_id,
            years=years,
            sample_schools=sample_schools,
            full=full,
            resume=resume,
            detail_delay=detail_delay,
            detail_backoff_rounds=detail_backoff_rounds,
        )


def _run_crawl_unlocked(
    *,
    batch_id: str,
    years: list[int],
    sample_schools: int | None,
    full: bool,
    resume: bool,
    detail_delay: float,
    detail_backoff_rounds: int,
) -> dict[str, Any]:
    set_trace_id(f"kaoyan-v2-{batch_id}")

    logger.info("开始掌上考研 V2 采集 batch_id=%s years=%s full=%s sample_schools=%s", batch_id, years, full, sample_schools)
    schools_all, school_stats = fetch_school_list(batch_id, resume=resume)
    schools = schools_all if full else schools_all[: sample_schools or 2]

    plan_items, plan_stats = fetch_plan_list_v2(batch_id, schools, years, resume=resume)
    detail_items, detail_stats = fetch_plan_detail_v2(
        batch_id,
        plan_items,
        detail_delay=detail_delay,
        backoff_rounds=detail_backoff_rounds,
        resume=resume,
    )
    score_items, score_stats = fetch_score_lines(batch_id, schools, years, resume=resume)
    level_items, level_stats = fetch_level_rates(batch_id, schools, resume=resume)

    rows, csv_stats = build_integrated_rows(
        batch_id=batch_id,
        schools=schools,
        plans=plan_items,
        details=detail_items,
        scores=score_items,
        levels=level_items,
    )
    csv_path = save_integrated_csv(batch_id, rows)

    summary = build_summary(
        batch_id=batch_id,
        years=years,
        full=full,
        schools=schools,
        csv_path=csv_path,
        block_stats={
            "school_list": school_stats,
            "plan_list_v2": plan_stats,
            "plan_detail_v2": detail_stats,
            "score_line": score_stats,
            "level_rate": level_stats,
            "integrated_csv": csv_stats,
        },
        rows=rows,
    )
    save_json(raw_batch_dir(batch_id) / "crawl_summary.json", summary)
    logger.info("掌上考研 V2 采集完成：%s", summary)
    return summary


def build_integrated_rows(
    *,
    batch_id: str,
    schools: list[dict[str, Any]],
    plans: list[dict[str, Any]],
    details: dict[str, dict[str, Any]],
    scores: list[dict[str, Any]],
    levels: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """把各分块数据整理为一行一个招生计划研究方向的大合集 CSV。"""
    rows: list[dict[str, Any]] = []
    school_by_id = {school.get("school_id"): school for school in schools}
    level_map = _build_level_map(levels)
    score_map = _build_score_map(scores)
    seen_plan_rows: set[tuple[Any, Any, Any, str, str]] = set()
    duplicate_plan_rows = 0
    score_matched_count = 0
    level_rate_matched_count = 0
    unique_plan_ids: set[Any] = set()
    detail_success_count = 0
    detail_error_count = 0
    detail_missing_count = 0

    for plan in plans:
        school = school_by_id.get(plan.get("school_id"), {})
        detail_entry = details.get(str(plan.get("plan_id"))) or {}
        detail = detail_entry.get("data") or {}
        detail_status = detail_entry.get("source_status") or "missing"
        detail_error = detail_entry.get("error_message") or ""
        expanded = _research_area_rows(plan, detail)
        unique_plan_ids.add(plan.get("plan_id"))
        if detail_status == "success":
            detail_success_count += 1
        elif detail_status == "error":
            detail_error_count += 1
        else:
            detail_missing_count += 1

        for area in expanded:
            exam_subject_clean = clean_html(area.get("exam_subject"))
            key = (
                plan.get("school_id"),
                plan.get("year"),
                plan.get("plan_id"),
                clean_text(area.get("research_area")),
                exam_subject_clean,
            )
            if key in seen_plan_rows:
                duplicate_plan_rows += 1
                continue
            seen_plan_rows.add(key)
            score_key = _score_key_from_plan(plan)
            score = score_map.get(score_key)
            level_code = clean_text(detail.get("level2_code") or plan.get("level2_code") or detail.get("level1_code") or plan.get("level1_code"))
            level_key = (plan.get("school_id"), level_code)
            if score:
                score_matched_count += 1
            if level_key in level_map:
                level_rate_matched_count += 1
            rows.append(_build_plan_row(batch_id, school, plan, detail, area, detail_status, detail_error, level_map, score))

    stats = {
        "count": len(rows),
        "plan_rows": len(rows),
        "unique_plan_count": len(unique_plan_ids),
        "success_count": sum(1 for row in rows if row.get("source_status") == "success"),
        "error_count": sum(1 for row in rows if row.get("source_status") == "error"),
        "duplicate_count": duplicate_plan_rows,
        "detail_success_count": detail_success_count,
        "detail_error_count": detail_error_count,
        "detail_missing_count": detail_missing_count,
        "score_matched_count": score_matched_count,
        "level_rate_matched_count": level_rate_matched_count,
    }
    return rows, stats


def save_integrated_csv(batch_id: str, rows: list[dict[str, Any]]) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / f"kaoyan_v2_integrated_{batch_id}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    return path


def build_summary(
    *,
    batch_id: str,
    years: list[int],
    full: bool,
    schools: list[dict[str, Any]],
    csv_path: Path,
    block_stats: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    school_years: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"plan_rows": 0}))
    for row in rows:
        school_id = clean_text(row.get("school_id"))
        year = clean_text(row.get("year"))
        if not school_id or not year:
            continue
        school_years[school_id][year]["plan_rows"] += 1

    integrated_stats = block_stats.get("integrated_csv") or {}

    return {
        "crawler_name": "kaoyan_v2",
        "batch_id": batch_id,
        "years": years,
        "mode": "full" if full else "sample",
        "school_count": len(schools),
        "schools": [{"school_id": school.get("school_id"), "school_name": school.get("school_name")} for school in schools],
        "raw_output_path": project_relative(raw_batch_dir(batch_id)),
        "parsed_output_path": project_relative(csv_path),
        "row_count": len(rows),
        "plan_rows": integrated_stats.get("plan_rows", len(rows)),
        "unique_plan_count": integrated_stats.get("unique_plan_count"),
        "detail_success_count": integrated_stats.get("detail_success_count"),
        "detail_error_count": integrated_stats.get("detail_error_count"),
        "detail_missing_count": integrated_stats.get("detail_missing_count"),
        "score_matched_count": integrated_stats.get("score_matched_count"),
        "level_rate_matched_count": integrated_stats.get("level_rate_matched_count"),
        "block_stats": block_stats,
        "school_year_summary": school_years,
    }


def _base_row(batch_id: str, source_api: str, status: str = "success", error: str = "") -> dict[str, Any]:
    row = {field: "" for field in CSV_FIELDS}
    row.update({"batch_id": batch_id, "source_api": source_api, "source_status": status, "error_message": error})
    return row


def _fill_school(row: dict[str, Any], school: dict[str, Any]) -> None:
    row.update(
        {
            "school_id": school.get("school_id"),
            "school_name": school.get("school_name"),
            "province_name": school.get("province_name") or "重庆",
            "city": "重庆市",
            "province_area": province_area(school.get("province_area")),
            "type_name": school.get("type_name"),
            "type_school_name": school.get("type_school_name"),
            "is_985": school.get("is_985"),
            "is_211": school.get("is_211"),
            "syl": school.get("syl"),
            "is_zihuaxian": school.get("is_zihuaxian"),
            "school_level": school_level(school),
            "school_recruit_number_reference": school.get("recruit_number"),
            "school_major_number_reference": school.get("major_number"),
            "rk_rank": school.get("rk_rank"),
        }
    )


def _build_school_row(batch_id: str, school: dict[str, Any]) -> dict[str, Any]:
    row = _base_row(batch_id, "/pc/school/schoolList")
    _fill_school(row, school)
    return row


def _build_plan_row(
    batch_id: str,
    school: dict[str, Any],
    plan: dict[str, Any],
    detail: dict[str, Any],
    area: dict[str, Any],
    detail_status: str,
    detail_error: str,
    level_map: dict[tuple[Any, str], dict[str, Any]],
    score: dict[str, Any] | None,
) -> dict[str, Any]:
    row = _base_row(batch_id, "/pc/school/planListV2+/pc/school/planDetailV2", detail_status, detail_error)
    _fill_school(row, school)
    level1_code = clean_text(detail.get("level1_code") or plan.get("level1_code"))
    level2_code = clean_text(detail.get("level2_code") or plan.get("level2_code"))
    special_code = clean_text(detail.get("special_code") or plan.get("special_code"))
    recruit_type_name = detail.get("recruit_type_name") or plan.get("recruit_type_name")
    degree_type = plan.get("degree_type")
    row.update(
        {
            "year": plan.get("year"),
            "plan_id": plan.get("plan_id"),
            "spe_id": plan.get("spe_id") or detail.get("spe_id"),
            "depart_id": detail.get("depart_id") if detail.get("depart_id") not in (None, "") else plan.get("depart_id"),
            "depart_name": detail.get("depart_name") or plan.get("depart_name"),
            "special_code": special_code,
            "special_name": detail.get("special_name") or plan.get("special_name"),
            "major_category_code": special_code[:2] if special_code else "",
            "level1_code": level1_code,
            "level1_name": detail.get("level1_name") or plan.get("level1_name"),
            "level2_code": level2_code,
            "level2_name": detail.get("level2_name") or plan.get("level2_name"),
            "degree_type": degree_type,
            "degree_type_std": degree_type_std(degree_type or detail.get("degree_type_name") or plan.get("degree_type_name")),
            "degree_type_name": detail.get("degree_type_name") or plan.get("degree_type_name"),
            "recruit_type": detail.get("recruit_type"),
            "recruit_type_name": recruit_type_name,
            "study_mode_std": study_mode_std(recruit_type_name),
            "exam_class": detail.get("exam_class"),
            "exam_class_name": detail.get("exam_class_name") or plan.get("exam_class_name"),
            "research_area": area.get("research_area"),
            "exam_subject": area.get("exam_subject"),
            "exam_subject_clean": clean_html(area.get("exam_subject")),
            "research_area_note": area.get("note"),
            "is_statistic_direction": area.get("is_statistic_direction"),
            "exam_book": detail.get("exam_book"),
            "exam_book_clean": clean_html(detail.get("exam_book")),
            "exam_book_year": detail.get("exam_book_year"),
            "intro_id": detail.get("intro_id"),
            "plan_recruit_number": area.get("recruit_number") or detail.get("recruit_number") or plan.get("recruit_number"),
            "plan_remark": plan.get("remark"),
            "min_score": detail.get("min_score"),
            "score_years_json": json_compact(detail.get("score_years")),
            "major_rate": detail.get("major_rate"),
            "doctoral_point": detail.get("doctoral_point"),
        }
    )
    level = level_map.get((plan.get("school_id"), level2_code)) or level_map.get((plan.get("school_id"), level1_code))
    if level:
        _fill_level(row, level)
    if score:
        _fill_score(row, score)
    return row


def _fill_score(row: dict[str, Any], score: dict[str, Any]) -> None:
    row.update(
        {
            "score_data_type": score.get("data_type"),
            "score_line_type": _score_line_type(score.get("data_type")),
            "score_depart_id": score.get("depart_id"),
            "score_depart_name": score.get("depart_name"),
            "score_code": score.get("code"),
            "score_name": score.get("name"),
            "score_degree_type": score.get("degree_type"),
            "score_total": score.get("total"),
            "score_politics": score.get("politics"),
            "score_english": score.get("english"),
            "score_special_one": score.get("special_one"),
            "score_special_two": score.get("special_two"),
            "score_diff_to_national": score.get("diff_total"),
            "score_diff_politics": score.get("diff_politics"),
            "score_diff_english": score.get("diff_english"),
            "score_note": score.get("note"),
            "score_special_remark": score.get("special_remark"),
        }
    )


def _fill_level(row: dict[str, Any], level: dict[str, Any]) -> None:
    row.update(
        {
            "subject_code": level.get("code"),
            "subject_name": level.get("code_name"),
            "subject_degree_type": level.get("degree_type"),
            "subject_degree_type_std": degree_type_std(level.get("degree_type")),
            "level_rate": level.get("rate"),
            "rate_sort": level.get("rate_sort"),
            "has_doctor": level.get("has_doctor"),
        }
    )


def _build_level_map(levels: list[dict[str, Any]]) -> dict[tuple[Any, str], dict[str, Any]]:
    result: dict[tuple[Any, str], dict[str, Any]] = {}
    for level in levels:
        code = clean_text(level.get("code"))
        if code:
            result[(level.get("school_id"), code)] = level
    return result


def _build_score_map(scores: list[dict[str, Any]]) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    """只保留唯一专业分数线精确匹配，重复键不合并。"""
    result: dict[tuple[str, str, str, str, str], dict[str, Any] | None] = {}
    for score in scores:
        if score.get("data_type") != "school_score":
            continue
        key = _score_key_from_score(score)
        if key in result:
            result[key] = None
            continue
        result[key] = score
    return {key: score for key, score in result.items() if score is not None}


def _score_key_from_plan(plan: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        clean_text(plan.get("school_id")),
        clean_text(plan.get("year")),
        clean_text(plan.get("depart_id")),
        clean_text(plan.get("special_code")),
        clean_text(plan.get("degree_type")),
    )


def _score_key_from_score(score: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        clean_text(score.get("school_id")),
        clean_text(score.get("year")),
        clean_text(score.get("depart_id")),
        clean_text(score.get("code")),
        clean_text(score.get("degree_type")),
    )


def _research_area_rows(plan: dict[str, Any], detail: dict[str, Any]) -> list[dict[str, Any]]:
    research_area_data = detail.get("research_area_data") or {}
    year = clean_text(plan.get("year"))
    default_year = clean_text(detail.get("default_year"))
    rows: list[dict[str, Any]] = []

    for key in (year, default_year):
        if key and isinstance(research_area_data.get(key), list):
            rows = research_area_data[key]
            break
    if not rows and isinstance(research_area_data, dict):
        for value in research_area_data.values():
            if isinstance(value, list):
                rows.extend(value)

    if rows:
        return [dict(row) for row in rows]
    return [
        {
            "research_area": "",
            "exam_subject": "",
            "recruit_number": plan.get("recruit_number") or detail.get("recruit_number"),
            "note": "",
            "is_statistic_direction": "",
        }
    ]


def _score_line_type(value: Any) -> str:
    if value == "score_level":
        return "university"
    if value == "school_score":
        return "major"
    return ""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="掌上考研 V2 分块采集与整合入口")
    parser.add_argument("--batch-id", default=None, help="批次号；不传则按当前时间生成")
    parser.add_argument("--years", type=int, nargs="+", default=DEFAULT_YEARS, help="采集年份，默认 2024 2025 2026")
    parser.add_argument("--sample-schools", type=int, default=2, help="试跑学校数量，默认前 2 所")
    parser.add_argument("--full", action="store_true", help="全量采集重庆 21 所学校")
    parser.add_argument("--resume", action="store_true", help="读取同批次聚合 JSON，跳过已完成数据")
    parser.add_argument("--detail-delay", type=float, default=DETAIL_DELAY, help="未缓存 planDetailV2 请求间隔秒数，默认 2")
    parser.add_argument("--detail-backoff-rounds", type=int, default=DETAIL_BACKOFF_ROUNDS, help="详情限流 30 秒冷却轮数，默认 1")
    return parser


def main() -> None:
    setup_logging()
    args = build_arg_parser().parse_args()
    summary = run_crawl(
        batch_id=args.batch_id,
        years=args.years,
        sample_schools=args.sample_schools,
        full=args.full,
        resume=args.resume,
        detail_delay=args.detail_delay,
        detail_backoff_rounds=args.detail_backoff_rounds,
    )
    print(summary)


if __name__ == "__main__":
    main()
