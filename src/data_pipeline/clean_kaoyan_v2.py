"""S06 掌上考研 V2 大合集清洗与质量检查。

输入 S03 生成的方向级大合集 CSV，输出 S07 入库前使用的标准化 CSV。
本模块只做清洗、拆分、去重和质量问题登记，不写入 MySQL。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.common.config import PROJECT_ROOT
from src.common.exceptions import FileProcessError, ValidationError
from src.common.logger import get_logger, setup_logging
from src.common.trace import set_trace_id

logger = get_logger("etl")

DEFAULT_BATCH_ID = "20260616_full_v2"
INTEGRATED_DIR = PROJECT_ROOT / "data" / "processed" / "kaoyan_v2_integrated"
RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "kaoyan_v2"
CLEANED_DIR = PROJECT_ROOT / "data" / "processed" / "kaoyan_v2_cleaned"
QUALITY_DIR = PROJECT_ROOT / "data" / "quality"
EXPECTED_YEARS = {"2024", "2025", "2026"}

FULLWIDTH_TRANSLATION = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺabcdefghijklmnopqrstuvwxyz",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
)

DEPARTMENT_FIELDS = [
    "batch_id",
    "school_id",
    "school_name",
    "depart_id",
    "department_name",
    "standard_name",
    "source_file",
]

MAJOR_FIELDS = [
    "batch_id",
    "school_id",
    "school_name",
    "depart_id",
    "department_name",
    "year",
    "plan_id",
    "spe_id",
    "major_code",
    "major_name",
    "major_category_code",
    "major_category",
    "level1_code",
    "level1_name",
    "level2_code",
    "level2_name",
    "degree_type",
    "degree_type_name",
    "study_mode",
    "recruit_type",
    "recruit_type_name",
    "exam_class",
    "exam_class_name",
    "research_direction",
    "research_area_note",
    "exam_subjects",
    "exam_book_clean",
    "exam_book_year",
    "intro_id",
    "source_file",
]

ENROLLMENT_FIELDS = [
    "batch_id",
    "year",
    "school_id",
    "school_name",
    "depart_id",
    "department_name",
    "plan_id",
    "major_code",
    "major_name",
    "degree_type",
    "study_mode",
    "research_direction",
    "exam_subjects",
    "plan_count",
    "recommended_exemption_count",
    "unified_exam_count",
    "min_score",
    "score_years_json",
    "plan_remark",
    "source_file",
]

SCORE_LINE_FIELDS = [
    "batch_id",
    "year",
    "school_id",
    "school_name",
    "depart_id",
    "department_name",
    "plan_id",
    "major_code",
    "major_name",
    "degree_type",
    "study_mode",
    "research_direction",
    "exam_subjects",
    "line_type",
    "score_data_type",
    "score_depart_id",
    "score_depart_name",
    "score_code",
    "score_name",
    "score_degree_type",
    "total_score_line",
    "politics_line",
    "english_line",
    "subject_one_line",
    "subject_two_line",
    "score_diff_to_national",
    "score_diff_politics",
    "score_diff_english",
    "score_note",
    "score_special_remark",
    "source_file",
]

SUBJECT_RATE_FIELDS = [
    "batch_id",
    "school_id",
    "school_name",
    "subject_code",
    "subject_name",
    "degree_type",
    "level_rate",
    "rate_sort",
    "has_doctor",
    "major_rate",
    "doctoral_point",
    "source_file",
]

ADMISSION_RECORD_FIELDS = [
    "batch_id",
    "year",
    "school_id",
    "school_name",
    "depart_id",
    "department_name",
    "major_code",
    "major_name",
    "research_direction",
    "candidate_no_hash",
    "initial_total_score",
    "politics_score",
    "english_score",
    "subject_one_score",
    "subject_two_score",
    "reexam_score",
    "final_score",
    "admission_status",
    "source_file",
]

QUALITY_FIELDS = [
    "issue_id",
    "batch_id",
    "source_file",
    "line_no",
    "table_name",
    "field_name",
    "issue_type",
    "raw_value",
    "record_key",
    "suggestion",
    "status",
]

REQUIRED_FIELDS = [
    "school_id",
    "school_name",
    "year",
    "plan_id",
    "depart_id",
    "depart_name",
    "special_code",
    "special_name",
    "degree_type_std",
    "study_mode_std",
    "research_area",
    "exam_subject_clean",
]


@dataclass(frozen=True)
class CleanOutputs:
    departments: Path
    majors: Path
    enrollment_plans: Path
    score_lines: Path
    subject_level_rates: Path
    admission_records: Path
    quality_issues: Path
    clean_summary: Path


def run_cleaning(
    batch_id: str,
    csv_path: Path | None = None,
    output_dir: Path = CLEANED_DIR,
    quality_dir: Path = QUALITY_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    """执行 S06 清洗流程并返回统计摘要。"""
    source_csv = (csv_path or integrated_csv_path(batch_id)).resolve()
    if not source_csv.exists():
        raise FileProcessError(f"S03 V2 大合集 CSV 不存在：{source_csv}")

    rows = read_integrated_rows(source_csv)
    validate_required_columns(rows.fieldnames, source_csv)

    output_paths = build_output_paths(batch_id, output_dir, quality_dir)
    quality: list[dict[str, Any]] = []

    cleaned_rows = prepare_rows(batch_id, source_csv, rows.records, quality)
    departments = build_departments(cleaned_rows)
    majors = build_majors(cleaned_rows)
    enrollment_plans = build_enrollment_plans(cleaned_rows, quality)
    score_lines = build_score_lines(cleaned_rows, quality)
    subject_rates = build_subject_level_rates(cleaned_rows, quality)
    admission_records: list[dict[str, Any]] = []

    add_school_without_plan_issues(batch_id, source_csv, cleaned_rows, quality)
    duplicate_count = count_duplicate_direction_keys(cleaned_rows)

    summary = {
        "crawler_name": "kaoyan_v2_cleaner",
        "batch_id": batch_id,
        "dry_run": dry_run,
        "source_csv": project_relative(source_csv),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_row_count": len(cleaned_rows),
        "input_field_count": len(rows.fieldnames),
        "school_count_in_csv": len({row["school_id"] for row in cleaned_rows}),
        "school_count_in_school_list": count_school_list(batch_id),
        "missing_school_without_plan_count": count_schools_without_plan(batch_id, cleaned_rows),
        "years": dict(sorted(Counter(row["year"] for row in cleaned_rows).items())),
        "duplicate_direction_key_count": duplicate_count,
        "output_counts": {
            "departments": len(departments),
            "majors": len(majors),
            "enrollment_plans": len(enrollment_plans),
            "score_lines": len(score_lines),
            "subject_level_rates": len(subject_rates),
            "admission_records": len(admission_records),
            "quality_issues": len(quality),
        },
        "quality_issue_type_counts": dict(sorted(Counter(issue["issue_type"] for issue in quality).items())),
        "output_paths": {
            "departments": project_relative(output_paths.departments),
            "majors": project_relative(output_paths.majors),
            "enrollment_plans": project_relative(output_paths.enrollment_plans),
            "score_lines": project_relative(output_paths.score_lines),
            "subject_level_rates": project_relative(output_paths.subject_level_rates),
            "admission_records": project_relative(output_paths.admission_records),
            "quality_issues": project_relative(output_paths.quality_issues),
            "clean_summary": project_relative(output_paths.clean_summary),
        },
    }

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        quality_dir.mkdir(parents=True, exist_ok=True)
        write_csv(output_paths.departments, DEPARTMENT_FIELDS, departments)
        write_csv(output_paths.majors, MAJOR_FIELDS, majors)
        write_csv(output_paths.enrollment_plans, ENROLLMENT_FIELDS, enrollment_plans)
        write_csv(output_paths.score_lines, SCORE_LINE_FIELDS, score_lines)
        write_csv(output_paths.subject_level_rates, SUBJECT_RATE_FIELDS, subject_rates)
        write_csv(output_paths.admission_records, ADMISSION_RECORD_FIELDS, admission_records)
        write_csv(output_paths.quality_issues, QUALITY_FIELDS, assign_issue_ids(quality))
        output_paths.clean_summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    logger.info(
        "S06 清洗完成：输入 %s 行，专业方向 %s 行，质量问题 %s 条，dry_run=%s",
        len(cleaned_rows),
        len(majors),
        len(quality),
        dry_run,
    )
    return summary


@dataclass(frozen=True)
class IntegratedRows:
    fieldnames: list[str]
    records: list[dict[str, str]]


def read_integrated_rows(path: Path) -> IntegratedRows:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        records = [dict(row) for row in reader]
    if not records:
        raise ValidationError(f"S03 V2 大合集 CSV 为空：{path}")
    return IntegratedRows(fieldnames=fieldnames, records=records)


def validate_required_columns(fieldnames: list[str], path: Path) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in fieldnames]
    if missing:
        raise ValidationError(f"{path} 缺少 S06 必需字段：{', '.join(missing)}")


def prepare_rows(
    batch_id: str,
    source_csv: Path,
    raw_rows: list[dict[str, str]],
    quality: list[dict[str, Any]],
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    source_ref = project_relative(source_csv)

    for line_no, raw in enumerate(raw_rows, start=2):
        row = {key: clean_text(value) for key, value in raw.items()}
        row["batch_id"] = batch_id
        row["source_file"] = source_ref
        row["_line_no"] = str(line_no)

        for field in REQUIRED_FIELDS:
            if not row.get(field):
                add_issue(
                    quality,
                    batch_id=batch_id,
                    source_file=source_ref,
                    line_no=line_no,
                    table_name="integrated_csv",
                    field_name=field,
                    issue_type="missing_required",
                    raw_value=raw.get(field),
                    record_key=direction_key(row),
                    suggestion="关键字段缺失，该行不应进入 S07 正式入库。",
                )

        if row.get("year") not in EXPECTED_YEARS:
            add_issue(
                quality,
                batch_id=batch_id,
                source_file=source_ref,
                line_no=line_no,
                table_name="integrated_csv",
                field_name="year",
                issue_type="invalid_year",
                raw_value=row.get("year"),
                record_key=direction_key(row),
                suggestion="S03 V2 当前只接受 2024/2025/2026 三年数据。",
            )

        row["plan_recruit_number_int"] = stringify_int(row.get("plan_recruit_number"))
        row["min_score_int"] = stringify_int(row.get("min_score"))
        row["score_total_int"] = stringify_int(row.get("score_total"))
        row["score_politics_int"] = stringify_int(row.get("score_politics"))
        row["score_english_int"] = stringify_int(row.get("score_english"))
        row["score_special_one_int"] = stringify_int(row.get("score_special_one"))
        row["score_special_two_int"] = stringify_int(row.get("score_special_two"))
        row["score_diff_to_national_int"] = stringify_int(row.get("score_diff_to_national"))
        row["score_diff_politics_int"] = stringify_int(row.get("score_diff_politics"))
        row["score_diff_english_int"] = stringify_int(row.get("score_diff_english"))
        row["rate_sort_int"] = stringify_int(row.get("rate_sort"))
        row["has_doctor_int"] = normalize_bool_int(row.get("has_doctor"))

        if not row.get("exam_book_clean"):
            add_optional_missing_issue(
                quality,
                batch_id,
                source_ref,
                line_no,
                "majors",
                "exam_book_clean",
                row,
                "接口未返回参考书，保留为空，后续可人工核验补充。",
            )
        if not row.get("score_total"):
            add_optional_missing_issue(
                quality,
                batch_id,
                source_ref,
                line_no,
                "score_lines",
                "score_total",
                row,
                "未精确匹配到专业复试线，保留为空，不使用门类线兜底。",
            )
        if row.get("subject_code") and not row.get("level_rate"):
            add_optional_missing_issue(
                quality,
                batch_id,
                source_ref,
                line_no,
                "subject_level_rates",
                "level_rate",
                row,
                "匹配到学科代码但无评估等级，保留为空。",
            )
        if not row.get("plan_recruit_number_int"):
            add_optional_missing_issue(
                quality,
                batch_id,
                source_ref,
                line_no,
                "enrollment_plans",
                "plan_count",
                row,
                "接口未返回可解析招生人数，保留为空，不能按 0 处理。",
            )

        cleaned.append(row)

    return cleaned


def build_departments(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["school_id"], row["depart_name"])
        if key in result:
            continue
        result[key] = {
            "batch_id": row["batch_id"],
            "school_id": row["school_id"],
            "school_name": row["school_name"],
            "depart_id": row["depart_id"],
            "department_name": row["depart_name"],
            "standard_name": row["depart_name"],
            "source_file": row["source_file"],
        }
    return sorted(result.values(), key=lambda item: (to_int_sort(item["school_id"]), item["department_name"]))


def build_majors(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: dict[tuple[str, str, str, str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            row["school_id"],
            row["depart_id"],
            row["special_code"],
            row["study_mode_std"],
            row["research_area"],
            row["exam_subject_clean"],
        )
        current = {
            "batch_id": row["batch_id"],
            "school_id": row["school_id"],
            "school_name": row["school_name"],
            "depart_id": row["depart_id"],
            "department_name": row["depart_name"],
            "year": row["year"],
            "plan_id": row["plan_id"],
            "spe_id": row.get("spe_id", ""),
            "major_code": row["special_code"],
            "major_name": row["special_name"],
            "major_category_code": row.get("major_category_code", ""),
            "major_category": row.get("level1_name", "") or row.get("major_category_code", ""),
            "level1_code": row.get("level1_code", ""),
            "level1_name": row.get("level1_name", ""),
            "level2_code": row.get("level2_code", ""),
            "level2_name": row.get("level2_name", ""),
            "degree_type": row["degree_type_std"],
            "degree_type_name": row.get("degree_type_name", ""),
            "study_mode": row["study_mode_std"],
            "recruit_type": row.get("recruit_type", ""),
            "recruit_type_name": row.get("recruit_type_name", ""),
            "exam_class": row.get("exam_class", ""),
            "exam_class_name": row.get("exam_class_name", ""),
            "research_direction": row["research_area"],
            "research_area_note": row.get("research_area_note", ""),
            "exam_subjects": row["exam_subject_clean"],
            "exam_book_clean": row.get("exam_book_clean", ""),
            "exam_book_year": row.get("exam_book_year", ""),
            "intro_id": row.get("intro_id", ""),
            "source_file": row["source_file"],
        }
        if key in result and major_rank(result[key]) <= major_rank(current):
            continue
        result[key] = current
    return sorted(
        result.values(),
        key=lambda item: (
            to_int_sort(item["school_id"]),
            to_int_sort(item["year"]),
            item["department_name"],
            item["major_code"],
            item["research_direction"],
            item["exam_subjects"],
        ),
    )


def build_enrollment_plans(
    rows: list[dict[str, str]],
    quality: list[dict[str, Any]],
) -> list[dict[str, str]]:
    result: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            row["school_id"],
            row["year"],
            row["plan_id"],
            row["research_area"],
            row["exam_subject_clean"],
        )
        if key in result:
            add_issue(
                quality,
                batch_id=row["batch_id"],
                source_file=row["source_file"],
                line_no=to_int(row["_line_no"]),
                table_name="enrollment_plans",
                field_name="direction_key",
                issue_type="duplicate",
                raw_value=direction_key(row),
                record_key=direction_key(row),
                suggestion="方向级招生计划重复，S06 仅保留第一条。",
            )
            continue
        result[key] = {
            "batch_id": row["batch_id"],
            "year": row["year"],
            "school_id": row["school_id"],
            "school_name": row["school_name"],
            "depart_id": row["depart_id"],
            "department_name": row["depart_name"],
            "plan_id": row["plan_id"],
            "major_code": row["special_code"],
            "major_name": row["special_name"],
            "degree_type": row["degree_type_std"],
            "study_mode": row["study_mode_std"],
            "research_direction": row["research_area"],
            "exam_subjects": row["exam_subject_clean"],
            "plan_count": row["plan_recruit_number_int"],
            "recommended_exemption_count": "",
            "unified_exam_count": "",
            "min_score": row["min_score_int"],
            "score_years_json": row.get("score_years_json", ""),
            "plan_remark": row.get("plan_remark", ""),
            "source_file": row["source_file"],
        }
    return sorted(result.values(), key=enrollment_sort_key)


def build_score_lines(
    rows: list[dict[str, str]],
    quality: list[dict[str, Any]],
) -> list[dict[str, str]]:
    result: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        if not row.get("score_total_int"):
            continue
        key = (
            row["school_id"],
            row["year"],
            row["plan_id"],
            row["research_area"],
            row["exam_subject_clean"],
            row.get("score_line_type", ""),
            row.get("score_depart_id", ""),
            row.get("score_code", ""),
            row.get("score_degree_type", ""),
            row["score_total_int"],
        )
        if key in result:
            add_issue(
                quality,
                batch_id=row["batch_id"],
                source_file=row["source_file"],
                line_no=to_int(row["_line_no"]),
                table_name="score_lines",
                field_name="score_line_key",
                issue_type="duplicate",
                raw_value="|".join(key),
                record_key=direction_key(row),
                suggestion="复试线匹配结果重复，S06 仅保留第一条。",
            )
            continue
        result[key] = {
            "batch_id": row["batch_id"],
            "year": row["year"],
            "school_id": row["school_id"],
            "school_name": row["school_name"],
            "depart_id": row["depart_id"],
            "department_name": row["depart_name"],
            "plan_id": row["plan_id"],
            "major_code": row["special_code"],
            "major_name": row["special_name"],
            "degree_type": row["degree_type_std"],
            "study_mode": row["study_mode_std"],
            "research_direction": row["research_area"],
            "exam_subjects": row["exam_subject_clean"],
            "line_type": normalize_score_line_type(row.get("score_line_type")),
            "score_data_type": row.get("score_data_type", ""),
            "score_depart_id": row.get("score_depart_id", ""),
            "score_depart_name": row.get("score_depart_name", ""),
            "score_code": row.get("score_code", ""),
            "score_name": row.get("score_name", ""),
            "score_degree_type": row.get("score_degree_type", ""),
            "total_score_line": row["score_total_int"],
            "politics_line": row["score_politics_int"],
            "english_line": row["score_english_int"],
            "subject_one_line": row["score_special_one_int"],
            "subject_two_line": row["score_special_two_int"],
            "score_diff_to_national": row["score_diff_to_national_int"],
            "score_diff_politics": row["score_diff_politics_int"],
            "score_diff_english": row["score_diff_english_int"],
            "score_note": row.get("score_note", ""),
            "score_special_remark": row.get("score_special_remark", ""),
            "source_file": row["source_file"],
        }
    return sorted(result.values(), key=score_sort_key)


def build_subject_level_rates(
    rows: list[dict[str, str]],
    quality: list[dict[str, Any]],
) -> list[dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    conflicts: dict[tuple[str, str], set[str]] = {}

    for row in rows:
        subject_code = row.get("subject_code", "")
        if not subject_code:
            continue
        key = (row["school_id"], subject_code)
        current = {
            "batch_id": row["batch_id"],
            "school_id": row["school_id"],
            "school_name": row["school_name"],
            "subject_code": subject_code,
            "subject_name": row.get("subject_name", ""),
            "degree_type": row.get("subject_degree_type_std") or row["degree_type_std"],
            "level_rate": row.get("level_rate", ""),
            "rate_sort": row["rate_sort_int"],
            "has_doctor": row["has_doctor_int"],
            "major_rate": row.get("major_rate", ""),
            "doctoral_point": row.get("doctoral_point", ""),
            "source_file": row["source_file"],
        }

        if key not in result:
            result[key] = current
            continue

        existing = result[key]
        if current["level_rate"]:
            conflicts.setdefault(key, set()).update(
                value for value in [existing.get("level_rate", ""), current["level_rate"]] if value
            )
        if subject_rate_rank(current) < subject_rate_rank(existing):
            result[key] = current

    for key, rates in conflicts.items():
        if len(rates) > 1:
            row = result[key]
            add_issue(
                quality,
                batch_id=row["batch_id"],
                source_file=row["source_file"],
                line_no=None,
                table_name="subject_level_rates",
                field_name="level_rate",
                issue_type="inconsistent",
                raw_value="/".join(sorted(rates)),
                record_key=f"school_id={key[0]}|subject_code={key[1]}",
                suggestion="同一学校同一学科存在多个评估等级，已优先保留有 rate_sort 的记录。",
            )

    return sorted(result.values(), key=lambda item: (to_int_sort(item["school_id"]), item["subject_code"]))


def add_school_without_plan_issues(
    batch_id: str,
    source_csv: Path,
    rows: list[dict[str, str]],
    quality: list[dict[str, Any]],
) -> None:
    school_list = read_school_list(batch_id)
    if not school_list:
        return
    csv_school_ids = {row["school_id"] for row in rows}
    source_ref = project_relative(source_csv)
    for school in school_list:
        school_id = str(school.get("school_id", "")).strip()
        school_name = clean_text(school.get("school_name"))
        if school_id and school_id not in csv_school_ids:
            add_issue(
                quality,
                batch_id=batch_id,
                source_file=source_ref,
                line_no=None,
                table_name="enrollment_plans",
                field_name="school_id",
                issue_type="missing_plan_rows",
                raw_value=f"{school_id} {school_name}",
                record_key=f"school_id={school_id}",
                suggestion="schoolList 有候选学校，但 planListV2 未返回近三年招生计划明细；S04 保留候选学校，S07 不生成计划行。",
            )


def read_school_list(batch_id: str) -> list[dict[str, Any]]:
    path = RAW_ROOT / batch_id / "school_list" / "school_list.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def count_school_list(batch_id: str) -> int | None:
    items = read_school_list(batch_id)
    return len({str(item.get("school_id")) for item in items if item.get("school_id")}) if items else None


def count_schools_without_plan(batch_id: str, rows: list[dict[str, str]]) -> int:
    school_items = read_school_list(batch_id)
    if not school_items:
        return 0
    csv_school_ids = {row["school_id"] for row in rows}
    return sum(1 for item in school_items if str(item.get("school_id", "")).strip() not in csv_school_ids)


def count_duplicate_direction_keys(rows: list[dict[str, str]]) -> int:
    counter = Counter(
        (
            row["school_id"],
            row["year"],
            row["plan_id"],
            row["research_area"],
            row["exam_subject_clean"],
        )
        for row in rows
    )
    return sum(count - 1 for count in counter.values() if count > 1)


def assign_issue_ids(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, issue in enumerate(issues, start=1):
        item = dict(issue)
        item["issue_id"] = index
        rows.append(item)
    return rows


def add_optional_missing_issue(
    quality: list[dict[str, Any]],
    batch_id: str,
    source_file: str,
    line_no: int,
    table_name: str,
    field_name: str,
    row: dict[str, str],
    suggestion: str,
) -> None:
    add_issue(
        quality,
        batch_id=batch_id,
        source_file=source_file,
        line_no=line_no,
        table_name=table_name,
        field_name=field_name,
        issue_type="missing_optional",
        raw_value="",
        record_key=direction_key(row),
        suggestion=suggestion,
    )


def add_issue(
    quality: list[dict[str, Any]],
    *,
    batch_id: str,
    source_file: str,
    line_no: int | None,
    table_name: str,
    field_name: str,
    issue_type: str,
    raw_value: Any,
    record_key: str,
    suggestion: str,
) -> None:
    quality.append(
        {
            "issue_id": "",
            "batch_id": batch_id,
            "source_file": source_file,
            "line_no": "" if line_no is None else str(line_no),
            "table_name": table_name,
            "field_name": field_name,
            "issue_type": issue_type,
            "raw_value": "" if raw_value is None else str(raw_value),
            "record_key": record_key,
            "suggestion": suggestion,
            "status": "open",
        }
    )


def integrated_csv_path(batch_id: str) -> Path:
    return INTEGRATED_DIR / f"kaoyan_v2_integrated_{batch_id}.csv"


def build_output_paths(batch_id: str, output_dir: Path, quality_dir: Path) -> CleanOutputs:
    return CleanOutputs(
        departments=output_dir / f"departments_{batch_id}.csv",
        majors=output_dir / f"majors_{batch_id}.csv",
        enrollment_plans=output_dir / f"enrollment_plans_{batch_id}.csv",
        score_lines=output_dir / f"score_lines_{batch_id}.csv",
        subject_level_rates=output_dir / f"subject_level_rates_{batch_id}.csv",
        admission_records=output_dir / f"admission_records_{batch_id}.csv",
        quality_issues=quality_dir / f"data_quality_issues_{batch_id}.csv",
        clean_summary=quality_dir / f"clean_summary_{batch_id}.json",
    )


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).translate(FULLWIDTH_TRANSLATION)
    text = re.sub(r"[\t\r\n]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def to_int(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def stringify_int(value: Any) -> str:
    number = to_int(value)
    return "" if number is None else str(number)


def to_int_sort(value: Any) -> int:
    number = to_int(value)
    return number if number is not None else 999999999


def normalize_bool_int(value: Any) -> str:
    text = clean_text(value)
    if text in {"1", "true", "True", "TRUE", "是", "有", "Y", "yes"}:
        return "1"
    return "0"


def normalize_score_line_type(value: Any) -> str:
    text = clean_text(value)
    if text in {"major", "school_major", "专业线"}:
        return "major"
    if text in {"university", "school", "院校线"}:
        return "university"
    if text in {"national", "国家线"}:
        return "national"
    return text or "major"


def direction_key(row: dict[str, str]) -> str:
    return (
        f"school_id={row.get('school_id', '')}|year={row.get('year', '')}|"
        f"plan_id={row.get('plan_id', '')}|research_area={row.get('research_area', '')}|"
        f"exam_subject={row.get('exam_subject_clean', '')}"
    )


def subject_rate_rank(row: dict[str, str]) -> tuple[int, int, int]:
    return (
        0 if row.get("level_rate") else 1,
        0 if row.get("rate_sort") else 1,
        0 if row.get("has_doctor") == "1" else 1,
    )


def major_rank(row: dict[str, str]) -> tuple[int, int, int, int]:
    """专业方向跨年去重时保留信息更完整、年份更新的记录。"""
    return (
        0 if row.get("exam_book_clean") else 1,
        0 if row.get("research_area_note") else 1,
        0 if row.get("intro_id") else 1,
        -to_int_sort(row.get("year")),
    )


def enrollment_sort_key(item: dict[str, str]) -> tuple[Any, ...]:
    return (
        to_int_sort(item["school_id"]),
        to_int_sort(item["year"]),
        to_int_sort(item["plan_id"]),
        item["research_direction"],
        item["exam_subjects"],
    )


def score_sort_key(item: dict[str, str]) -> tuple[Any, ...]:
    return (
        to_int_sort(item["school_id"]),
        to_int_sort(item["year"]),
        to_int_sort(item["plan_id"]),
        item["research_direction"],
        item["exam_subjects"],
    )


def project_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="S06 掌上考研 V2 大合集清洗与质量检查")
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID, help="S03 V2 批次号")
    parser.add_argument("--csv", type=Path, default=None, help="手动指定 S03 V2 大合集 CSV")
    parser.add_argument("--output-dir", type=Path, default=CLEANED_DIR, help="清洗后标准 CSV 输出目录")
    parser.add_argument("--quality-dir", type=Path, default=QUALITY_DIR, help="质量问题和清洗报告输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging()
    set_trace_id(f"s06-clean-{args.batch_id}")
    summary = run_cleaning(
        batch_id=args.batch_id,
        csv_path=args.csv,
        output_dir=args.output_dir,
        quality_dir=args.quality_dir,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
