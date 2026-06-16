"""S07 清洗数据入库闭环。

读取 S06 标准化 CSV，按当前 MySQL 业务表结构幂等写入核心表。
本模块不清空旧数据；重复执行时通过各表唯一键 upsert，避免重复入库。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from src.common.config import PROJECT_ROOT
from src.common.database import mysql_connection
from src.common.exceptions import FileProcessError, ValidationError
from src.common.logger import get_logger, setup_logging
from src.common.trace import set_trace_id

logger = get_logger("etl")

DEFAULT_BATCH_ID = "20260616_full_v2"
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "processed" / "kaoyan_v2_cleaned"
DEFAULT_QUALITY_DIR = PROJECT_ROOT / "data" / "quality"
CHUNK_SIZE = 500


@dataclass(frozen=True)
class LoadFiles:
    departments: Path
    majors: Path
    enrollment_plans: Path
    score_lines: Path
    subject_level_rates: Path
    admission_records: Path
    quality_issues: Path


@dataclass
class LoadContext:
    university_id_by_school_id: dict[str, int]
    source_id_by_school_id: dict[str, int]
    department_id_by_key: dict[tuple[str, str], int]
    major_id_by_key: dict[tuple[str, str, str, str, str], int]


def run_load(
    batch_id: str,
    input_dir: Path = DEFAULT_INPUT_DIR,
    quality_dir: Path = DEFAULT_QUALITY_DIR,
    dry_run: bool = False,
    skip_quality: bool = False,
) -> dict[str, Any]:
    """执行 S07 入库，返回可打印摘要。"""
    files = build_load_files(batch_id, input_dir, quality_dir)
    records = read_all_records(files, skip_quality=skip_quality)
    school_ids = collect_school_ids(records)

    with mysql_connection() as connection:
        context = build_initial_context(connection, school_ids)
        validate_context(context, school_ids)
        preview_context = build_preview_context(records, context)
        prepared = prepare_load_records(records, preview_context)
        summary = build_summary(batch_id, files, records, prepared, context, dry_run, skip_quality)

        if dry_run:
            logger.info("S07 dry-run 完成：%s", json.dumps(summary["planned_counts"], ensure_ascii=False))
            return summary

    pipeline_run_id = create_pipeline_run(batch_id, files, summary)
    try:
        with mysql_connection() as connection:
            context = build_initial_context(connection, school_ids)
            with connection.cursor() as cursor:
                department_rows = prepare_departments(records["departments"], context)
                load_departments(cursor, department_rows)
                context.department_id_by_key = fetch_department_ids(cursor, school_ids)

                major_rows, _ = prepare_majors(records["majors"], context)
                load_majors(cursor, major_rows)
                context.major_id_by_key = fetch_major_ids(cursor, school_ids)

                enrollment_rows, _ = prepare_enrollment_plans(records["enrollment_plans"], context)
                score_rows, _ = prepare_score_lines(records["score_lines"], context)
                subject_rows = prepare_subject_level_rates(records["subject_level_rates"], context)
                load_enrollment_plans(cursor, enrollment_rows)
                load_score_lines(cursor, score_rows)
                load_subject_level_rates(cursor, subject_rows)
                if not skip_quality:
                    quality_rows = prepare_quality_issues(records["quality_issues"], context)
                    load_quality_issues(cursor, quality_rows)
            connection.commit()

        update_pipeline_run(pipeline_run_id, "success", summary)
        logger.info("S07 入库完成：pipeline_run_id=%s", pipeline_run_id)
        return summary | {"pipeline_run_id": pipeline_run_id, "status": "success"}
    except Exception as exc:
        update_pipeline_run(pipeline_run_id, "failed", summary, error_message=str(exc))
        logger.exception("S07 入库失败：pipeline_run_id=%s", pipeline_run_id)
        raise


def build_load_files(batch_id: str, input_dir: Path, quality_dir: Path) -> LoadFiles:
    files = LoadFiles(
        departments=input_dir / f"departments_{batch_id}.csv",
        majors=input_dir / f"majors_{batch_id}.csv",
        enrollment_plans=input_dir / f"enrollment_plans_{batch_id}.csv",
        score_lines=input_dir / f"score_lines_{batch_id}.csv",
        subject_level_rates=input_dir / f"subject_level_rates_{batch_id}.csv",
        admission_records=input_dir / f"admission_records_{batch_id}.csv",
        quality_issues=quality_dir / f"data_quality_issues_{batch_id}.csv",
    )
    for path in files.__dict__.values():
        if not path.exists():
            raise FileProcessError(f"S07 输入文件不存在：{path}")
    return files


def read_all_records(files: LoadFiles, *, skip_quality: bool) -> dict[str, list[dict[str, str]]]:
    return {
        "departments": read_csv(files.departments),
        "majors": read_csv(files.majors),
        "enrollment_plans": read_csv(files.enrollment_plans),
        "score_lines": read_csv(files.score_lines),
        "subject_level_rates": read_csv(files.subject_level_rates),
        "admission_records": read_csv(files.admission_records),
        "quality_issues": [] if skip_quality else read_csv(files.quality_issues),
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [{key: clean_text(value) for key, value in row.items()} for row in csv.DictReader(file)]


def collect_school_ids(records: dict[str, list[dict[str, str]]]) -> set[str]:
    school_ids: set[str] = set()
    for rows in records.values():
        for row in rows:
            school_id = row.get("school_id", "")
            if school_id:
                school_ids.add(school_id)
    for row in records.get("quality_issues", []):
        school_id = parse_school_id_from_quality(row)
        if school_id:
            school_ids.add(school_id)
    return school_ids


def build_initial_context(connection, school_ids: set[str]) -> LoadContext:
    with connection.cursor() as cursor:
        return LoadContext(
            university_id_by_school_id=fetch_university_ids(cursor, school_ids),
            source_id_by_school_id=fetch_school_list_source_ids(cursor, school_ids),
            department_id_by_key=fetch_department_ids(cursor, school_ids),
            major_id_by_key=fetch_major_ids(cursor, school_ids),
        )


def build_preview_context(records: dict[str, list[dict[str, str]]], base_context: LoadContext) -> LoadContext:
    """构造 dry-run 统计用虚拟 ID 映射，不写入数据库。"""
    department_id_by_key = dict(base_context.department_id_by_key)
    next_department_id = -1
    for row in records["departments"]:
        key = (row["school_id"], row["department_name"])
        if key not in department_id_by_key:
            department_id_by_key[key] = next_department_id
            next_department_id -= 1

    preview_context = LoadContext(
        university_id_by_school_id=dict(base_context.university_id_by_school_id),
        source_id_by_school_id=dict(base_context.source_id_by_school_id),
        department_id_by_key=department_id_by_key,
        major_id_by_key=dict(base_context.major_id_by_key),
    )

    major_rows, _ = prepare_majors(records["majors"], preview_context)
    next_major_id = -1
    for row in major_rows:
        school_id = school_id_for_university_id(row["university_id"], preview_context)
        department_name = department_name_for_department_id(row["department_id"], preview_context)
        key = (
            school_id,
            department_name,
            row["major_code"],
            row["study_mode"] or "",
            row["research_direction"] or "",
        )
        if key not in preview_context.major_id_by_key:
            preview_context.major_id_by_key[key] = next_major_id
            next_major_id -= 1
    return preview_context


def validate_context(context: LoadContext, school_ids: set[str]) -> None:
    missing_universities = sorted(school_ids - set(context.university_id_by_school_id))
    if missing_universities:
        raise ValidationError(f"以下 school_id 未在 universities 中找到，请先完成 S04：{missing_universities}")


def prepare_load_records(
    records: dict[str, list[dict[str, str]]],
    context: LoadContext,
) -> dict[str, list[dict[str, Any]]]:
    departments = prepare_departments(records["departments"], context)
    majors, major_collapsed = prepare_majors(records["majors"], context)
    enrollment_plans, enrollment_collapsed = prepare_enrollment_plans(records["enrollment_plans"], context)
    score_lines, score_collapsed = prepare_score_lines(records["score_lines"], context)
    subject_rates = prepare_subject_level_rates(records["subject_level_rates"], context)
    quality_issues = prepare_quality_issues(records["quality_issues"], context)
    return {
        "departments": departments,
        "majors": majors,
        "major_collapsed_count": major_collapsed,
        "enrollment_plans": enrollment_plans,
        "enrollment_collapsed_count": enrollment_collapsed,
        "score_lines": score_lines,
        "score_collapsed_count": score_collapsed,
        "subject_level_rates": subject_rates,
        "quality_issues": quality_issues,
    }


def school_id_for_university_id(university_id: int, context: LoadContext) -> str:
    for school_id, current_university_id in context.university_id_by_school_id.items():
        if current_university_id == university_id:
            return school_id
    raise ValidationError(f"未找到 university_id 对应的 school_id：{university_id}")


def department_name_for_department_id(department_id: int, context: LoadContext) -> str:
    for (_, department_name), current_department_id in context.department_id_by_key.items():
        if current_department_id == department_id:
            return department_name
    raise ValidationError(f"未找到 department_id 对应的 department_name：{department_id}")


def prepare_departments(rows: list[dict[str, str]], context: LoadContext) -> list[dict[str, Any]]:
    prepared: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        school_id = row["school_id"]
        university_id = context.university_id_by_school_id[school_id]
        key = (university_id, row["department_name"])
        prepared[key] = {
            "university_id": university_id,
            "department_name": row["department_name"],
            "standard_name": row.get("standard_name") or row["department_name"],
            "source_id": context.source_id_by_school_id.get(school_id),
        }
    return list(prepared.values())


def prepare_majors(
    rows: list[dict[str, str]],
    context: LoadContext,
) -> tuple[list[dict[str, Any]], int]:
    prepared: dict[tuple[int, int, str, str, str], dict[str, Any]] = {}
    collapsed = 0
    for row in rows:
        school_id = row["school_id"]
        university_id = context.university_id_by_school_id[school_id]
        department_id = department_id_for_row(row, context)
        key = (
            university_id,
            department_id,
            row["major_code"],
            row["study_mode"],
            row["research_direction"],
        )
        item = {
            "university_id": university_id,
            "department_id": department_id,
            "major_code": row["major_code"],
            "major_name": row["major_name"],
            "major_category": row.get("major_category") or row.get("level1_name"),
            "degree_type": row.get("degree_type"),
            "study_mode": row.get("study_mode"),
            "research_direction": row.get("research_direction"),
            "exam_subjects": row.get("exam_subjects"),
            "source_id": context.source_id_by_school_id.get(school_id),
            "_rank": major_load_rank(row),
        }
        if key in prepared:
            collapsed += 1
            if prepared[key]["_rank"] <= item["_rank"]:
                continue
        prepared[key] = item
    for item in prepared.values():
        item.pop("_rank", None)
    return list(prepared.values()), collapsed


def prepare_enrollment_plans(
    rows: list[dict[str, str]],
    context: LoadContext,
) -> tuple[list[dict[str, Any]], int]:
    grouped: dict[tuple[int, int, int], dict[str, Any]] = {}
    source_rows: defaultdict[tuple[int, int, int], list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        school_id = row["school_id"]
        university_id = context.university_id_by_school_id[school_id]
        department_id = department_id_for_row(row, context)
        major_id = major_id_for_row(row, context)
        year = to_int_required(row["year"])
        key = (year, university_id, major_id)
        source_rows[key].append(row)
        plan_count = to_int(row.get("plan_count"))
        if key not in grouped:
            grouped[key] = {
                "year": year,
                "university_id": university_id,
                "department_id": department_id,
                "major_id": major_id,
                "plan_count": plan_count,
                "recommended_exemption_count": to_int(row.get("recommended_exemption_count")),
                "unified_exam_count": to_int(row.get("unified_exam_count")),
                "source_id": context.source_id_by_school_id.get(school_id),
            }
        else:
            grouped[key]["plan_count"] = sum_nullable_int(grouped[key]["plan_count"], plan_count)
    collapsed = sum(len(items) - 1 for items in source_rows.values() if len(items) > 1)
    return list(grouped.values()), collapsed


def prepare_score_lines(
    rows: list[dict[str, str]],
    context: LoadContext,
) -> tuple[list[dict[str, Any]], int]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    source_rows: defaultdict[tuple[Any, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        school_id = row["school_id"]
        university_id = context.university_id_by_school_id[school_id]
        department_id = department_id_for_row(row, context)
        major_id = major_id_for_row(row, context)
        year = to_int_required(row["year"])
        line_type = row.get("line_type") or "major"
        major_category = row.get("score_name") or row.get("major_name")
        key = (year, line_type, university_id, major_id, major_category)
        source_rows[key].append(row)
        item = {
            "year": year,
            "line_type": line_type,
            "university_id": university_id,
            "department_id": department_id,
            "major_id": major_id,
            "major_category": major_category,
            "total_score_line": to_int_required(row["total_score_line"]),
            "politics_line": to_int(row.get("politics_line")),
            "english_line": to_int(row.get("english_line")),
            "subject_one_line": to_int(row.get("subject_one_line")),
            "subject_two_line": to_int(row.get("subject_two_line")),
            "score_diff_to_national": to_int(row.get("score_diff_to_national")),
            "source_id": context.source_id_by_school_id.get(school_id),
        }
        if key in grouped and score_line_rank(grouped[key]) >= score_line_rank(item):
            continue
        grouped[key] = item
    collapsed = sum(len(items) - 1 for items in source_rows.values() if len(items) > 1)
    return list(grouped.values()), collapsed


def prepare_subject_level_rates(
    rows: list[dict[str, str]],
    context: LoadContext,
) -> list[dict[str, Any]]:
    prepared: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        school_id = row["school_id"]
        university_id = context.university_id_by_school_id[school_id]
        key = (university_id, row["subject_code"])
        item = {
            "university_id": university_id,
            "subject_code": row["subject_code"],
            "subject_name": row.get("subject_name"),
            "degree_type": row.get("degree_type"),
            "level_rate": row.get("level_rate") or None,
            "rate_sort": to_int(row.get("rate_sort")),
            "has_doctor": to_int(row.get("has_doctor")) or 0,
            "candidate_school_id": to_int(school_id),
        }
        if key in prepared and subject_rate_rank(prepared[key]) <= subject_rate_rank(item):
            continue
        prepared[key] = item
    return list(prepared.values())


def prepare_quality_issues(
    rows: list[dict[str, str]],
    context: LoadContext,
) -> list[dict[str, Any]]:
    prepared: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        school_id = parse_school_id_from_quality(row)
        source_id = context.source_id_by_school_id.get(school_id) if school_id else None
        raw_value = combine_quality_raw_value(row)
        key = (
            source_id,
            row.get("table_name"),
            row.get("field_name"),
            row.get("issue_type"),
            raw_value,
            row.get("suggestion"),
            row.get("status") or "open",
        )
        prepared[key] = {
            "source_id": source_id,
            "table_name": row.get("table_name") or None,
            "field_name": row.get("field_name") or None,
            "issue_type": normalize_issue_type(row.get("issue_type")),
            "raw_value": raw_value[:1000] if raw_value else None,
            "suggestion": (row.get("suggestion") or "")[:1000] or None,
            "status": row.get("status") or "open",
        }
    return list(prepared.values())


def department_id_for_row(row: dict[str, str], context: LoadContext) -> int:
    school_id = row["school_id"]
    department_name = row.get("department_name") or row.get("depart_name")
    key = (school_id, department_name)
    department_id = context.department_id_by_key.get(key)
    if department_id is None:
        raise ValidationError(f"未找到学院映射：school_id={school_id}, department={department_name}")
    return department_id


def major_id_for_row(row: dict[str, str], context: LoadContext) -> int:
    school_id = row["school_id"]
    department_name = row.get("department_name") or row.get("depart_name")
    key = (
        school_id,
        department_name,
        row["major_code"],
        row["study_mode"],
        row["research_direction"],
    )
    major_id = context.major_id_by_key.get(key)
    if major_id is None:
        raise ValidationError(f"未找到专业映射：{key}")
    return major_id


def fetch_university_ids(cursor, school_ids: set[str]) -> dict[str, int]:
    if not school_ids:
        return {}
    cursor.execute(
        f"""
        SELECT id, candidate_school_id
        FROM universities
        WHERE candidate_school_id IN ({placeholders(school_ids)})
        """,
        tuple(to_int_required(school_id) for school_id in school_ids),
    )
    return {str(row["candidate_school_id"]): int(row["id"]) for row in cursor.fetchall()}


def fetch_school_list_source_ids(cursor, school_ids: set[str]) -> dict[str, int]:
    if not school_ids:
        return {}
    cursor.execute(
        f"""
        SELECT u.candidate_school_id, MAX(s.id) AS source_id
        FROM source_documents s
        JOIN universities u ON u.id = s.university_id
        WHERE s.document_type = 'school_list'
          AND u.candidate_school_id IN ({placeholders(school_ids)})
        GROUP BY u.candidate_school_id
        """,
        tuple(to_int_required(school_id) for school_id in school_ids),
    )
    return {str(row["candidate_school_id"]): int(row["source_id"]) for row in cursor.fetchall() if row["source_id"]}


def fetch_department_ids(cursor, school_ids: set[str]) -> dict[tuple[str, str], int]:
    if not school_ids:
        return {}
    cursor.execute(
        f"""
        SELECT u.candidate_school_id, d.department_name, d.id
        FROM departments d
        JOIN universities u ON u.id = d.university_id
        WHERE u.candidate_school_id IN ({placeholders(school_ids)})
        """,
        tuple(to_int_required(school_id) for school_id in school_ids),
    )
    return {
        (str(row["candidate_school_id"]), row["department_name"]): int(row["id"])
        for row in cursor.fetchall()
    }


def fetch_major_ids(cursor, school_ids: set[str]) -> dict[tuple[str, str, str, str, str], int]:
    if not school_ids:
        return {}
    cursor.execute(
        f"""
        SELECT
          u.candidate_school_id,
          d.department_name,
          m.major_code,
          m.study_mode,
          m.research_direction,
          m.id
        FROM majors m
        JOIN universities u ON u.id = m.university_id
        JOIN departments d ON d.id = m.department_id
        WHERE u.candidate_school_id IN ({placeholders(school_ids)})
        """,
        tuple(to_int_required(school_id) for school_id in school_ids),
    )
    return {
        (
            str(row["candidate_school_id"]),
            row["department_name"],
            row["major_code"],
            row["study_mode"] or "",
            row["research_direction"] or "",
        ): int(row["id"])
        for row in cursor.fetchall()
    }


def load_departments(cursor, rows: list[dict[str, Any]]) -> None:
    execute_many(
        cursor,
        """
        INSERT INTO departments (university_id, department_name, standard_name, source_id)
        VALUES (%(university_id)s, %(department_name)s, %(standard_name)s, %(source_id)s)
        ON DUPLICATE KEY UPDATE
          standard_name = VALUES(standard_name),
          source_id = VALUES(source_id)
        """,
        rows,
    )


def load_majors(cursor, rows: list[dict[str, Any]]) -> None:
    execute_many(
        cursor,
        """
        INSERT INTO majors (
          university_id, department_id, major_code, major_name, major_category,
          degree_type, study_mode, research_direction, exam_subjects, source_id
        )
        VALUES (
          %(university_id)s, %(department_id)s, %(major_code)s, %(major_name)s, %(major_category)s,
          %(degree_type)s, %(study_mode)s, %(research_direction)s, %(exam_subjects)s, %(source_id)s
        )
        ON DUPLICATE KEY UPDATE
          major_name = VALUES(major_name),
          major_category = VALUES(major_category),
          degree_type = VALUES(degree_type),
          exam_subjects = VALUES(exam_subjects),
          source_id = VALUES(source_id)
        """,
        rows,
    )


def load_enrollment_plans(cursor, rows: list[dict[str, Any]]) -> None:
    execute_many(
        cursor,
        """
        INSERT INTO enrollment_plans (
          year, university_id, department_id, major_id, plan_count,
          recommended_exemption_count, unified_exam_count, source_id
        )
        VALUES (
          %(year)s, %(university_id)s, %(department_id)s, %(major_id)s, %(plan_count)s,
          %(recommended_exemption_count)s, %(unified_exam_count)s, %(source_id)s
        )
        ON DUPLICATE KEY UPDATE
          department_id = VALUES(department_id),
          plan_count = VALUES(plan_count),
          recommended_exemption_count = VALUES(recommended_exemption_count),
          unified_exam_count = VALUES(unified_exam_count),
          source_id = VALUES(source_id)
        """,
        rows,
    )


def load_score_lines(cursor, rows: list[dict[str, Any]]) -> None:
    execute_many(
        cursor,
        """
        INSERT INTO score_lines (
          year, line_type, university_id, department_id, major_id, major_category,
          total_score_line, politics_line, english_line, subject_one_line, subject_two_line,
          score_diff_to_national, source_id
        )
        VALUES (
          %(year)s, %(line_type)s, %(university_id)s, %(department_id)s, %(major_id)s, %(major_category)s,
          %(total_score_line)s, %(politics_line)s, %(english_line)s, %(subject_one_line)s, %(subject_two_line)s,
          %(score_diff_to_national)s, %(source_id)s
        )
        ON DUPLICATE KEY UPDATE
          department_id = VALUES(department_id),
          total_score_line = VALUES(total_score_line),
          politics_line = VALUES(politics_line),
          english_line = VALUES(english_line),
          subject_one_line = VALUES(subject_one_line),
          subject_two_line = VALUES(subject_two_line),
          score_diff_to_national = VALUES(score_diff_to_national),
          source_id = VALUES(source_id)
        """,
        rows,
    )


def load_subject_level_rates(cursor, rows: list[dict[str, Any]]) -> None:
    execute_many(
        cursor,
        """
        INSERT INTO subject_level_rates (
          university_id, subject_code, subject_name, degree_type, level_rate,
          rate_sort, has_doctor, candidate_school_id
        )
        VALUES (
          %(university_id)s, %(subject_code)s, %(subject_name)s, %(degree_type)s, %(level_rate)s,
          %(rate_sort)s, %(has_doctor)s, %(candidate_school_id)s
        )
        ON DUPLICATE KEY UPDATE
          subject_name = VALUES(subject_name),
          degree_type = VALUES(degree_type),
          level_rate = VALUES(level_rate),
          rate_sort = VALUES(rate_sort),
          has_doctor = VALUES(has_doctor),
          candidate_school_id = VALUES(candidate_school_id)
        """,
        rows,
    )


def load_quality_issues(cursor, rows: list[dict[str, Any]]) -> None:
    existing = fetch_existing_quality_issue_keys(cursor)
    pending = []
    for row in rows:
        key = quality_issue_key(row)
        if key in existing:
            continue
        existing.add(key)
        pending.append(row)
    execute_many(
        cursor,
        """
        INSERT INTO data_quality_issues (
          source_id, table_name, field_name, issue_type, raw_value, suggestion, status
        )
        VALUES (
          %(source_id)s, %(table_name)s, %(field_name)s, %(issue_type)s,
          %(raw_value)s, %(suggestion)s, %(status)s
        )
        """,
        pending,
    )


def fetch_existing_quality_issue_keys(cursor) -> set[tuple[Any, ...]]:
    cursor.execute(
        """
        SELECT source_id, table_name, field_name, issue_type, raw_value, suggestion, status
        FROM data_quality_issues
        """
    )
    return {quality_issue_key(row) for row in cursor.fetchall()}


def quality_issue_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("source_id"),
        row.get("table_name"),
        row.get("field_name"),
        row.get("issue_type"),
        row.get("raw_value"),
        row.get("suggestion"),
        row.get("status"),
    )


def execute_many(cursor, sql: str, rows: list[dict[str, Any]]) -> None:
    for chunk in chunks(rows, CHUNK_SIZE):
        cursor.executemany(sql, chunk)


def create_pipeline_run(batch_id: str, files: LoadFiles, summary: dict[str, Any]) -> int:
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (
                  task_name, task_type, status, input_path, output_path,
                  total_count, success_count, failed_count, started_at
                )
                VALUES (
                  %(task_name)s, 'load', 'running', %(input_path)s, %(output_path)s,
                  %(total_count)s, 0, 0, NOW()
                )
                """,
                {
                    "task_name": f"S07_load_mysql_{batch_id}",
                    "input_path": project_relative(files.departments.parent),
                    "output_path": "mysql:zhiyuan",
                    "total_count": summary["planned_total_count"],
                },
            )
            pipeline_run_id = int(cursor.lastrowid)
        connection.commit()
    return pipeline_run_id


def update_pipeline_run(
    pipeline_run_id: int,
    status: str,
    summary: dict[str, Any],
    error_message: str | None = None,
) -> None:
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_runs
                SET status = %(status)s,
                    success_count = %(success_count)s,
                    failed_count = %(failed_count)s,
                    error_message = %(error_message)s,
                    finished_at = NOW()
                WHERE id = %(id)s
                """,
                {
                    "id": pipeline_run_id,
                    "status": status,
                    "success_count": summary["planned_total_count"] if status == "success" else 0,
                    "failed_count": 0 if status == "success" else summary["planned_total_count"],
                    "error_message": error_message,
                },
            )
        connection.commit()


def build_summary(
    batch_id: str,
    files: LoadFiles,
    records: dict[str, list[dict[str, str]]],
    prepared: dict[str, Any],
    context: LoadContext,
    dry_run: bool,
    skip_quality: bool,
) -> dict[str, Any]:
    planned_counts = {
        "departments": len(prepared["departments"]),
        "majors": len(prepared["majors"]),
        "enrollment_plans": len(prepared["enrollment_plans"]),
        "score_lines": len(prepared["score_lines"]),
        "subject_level_rates": len(prepared["subject_level_rates"]),
        "data_quality_issues": len(prepared["quality_issues"]),
    }
    planned_total_count = sum(planned_counts.values())
    return {
        "task_name": f"S07_load_mysql_{batch_id}",
        "batch_id": batch_id,
        "dry_run": dry_run,
        "skip_quality": skip_quality,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_dir": project_relative(files.departments.parent),
        "quality_file": project_relative(files.quality_issues),
        "input_counts": {name: len(rows) for name, rows in records.items()},
        "planned_counts": planned_counts,
        "planned_total_count": planned_total_count,
        "collapsed_counts_due_to_db_grain": {
            "majors": prepared["major_collapsed_count"],
            "enrollment_plans": prepared["enrollment_collapsed_count"],
            "score_lines": prepared["score_collapsed_count"],
        },
        "mapping_counts": {
            "universities": len(context.university_id_by_school_id),
            "school_list_sources": len(context.source_id_by_school_id),
            "existing_departments": len(context.department_id_by_key),
            "existing_majors": len(context.major_id_by_key),
        },
    }


def placeholders(values: Iterable[Any]) -> str:
    return ", ".join(["%s"] * len(list(values)))


def chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def to_int(value: Any) -> int | None:
    text = clean_text(value)
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def to_int_required(value: Any) -> int:
    result = to_int(value)
    if result is None:
        raise ValidationError(f"需要整数值，实际为空或非法：{value!r}")
    return result


def sum_nullable_int(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


def major_load_rank(row: dict[str, str]) -> tuple[int, int, int, int]:
    return (
        0 if row.get("exam_book_clean") else 1,
        -len(row.get("exam_subjects", "")),
        0 if row.get("research_area_note") else 1,
        -to_int_required(row.get("year")),
    )


def score_line_rank(row: dict[str, Any]) -> tuple[int, int]:
    return (
        int(row.get("total_score_line") or 0),
        int(row.get("score_diff_to_national") or 0),
    )


def subject_rate_rank(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        0 if row.get("level_rate") else 1,
        0 if row.get("rate_sort") is not None else 1,
        0 if int(row.get("has_doctor") or 0) == 1 else 1,
    )


def parse_school_id_from_quality(row: dict[str, str]) -> str | None:
    record_key = row.get("record_key", "")
    for part in record_key.split("|"):
        if part.startswith("school_id="):
            school_id = part.split("=", 1)[1].strip()
            return school_id or None
    raw_value = row.get("raw_value", "")
    first_token = raw_value.split(" ", 1)[0].strip()
    return first_token if first_token.isdigit() else None


def combine_quality_raw_value(row: dict[str, str]) -> str:
    raw_value = row.get("raw_value", "")
    record_key = row.get("record_key", "")
    if record_key:
        combined = f"{raw_value} | {record_key}" if raw_value else record_key
    else:
        combined = raw_value
    return combined[:1000]


def normalize_issue_type(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return "missing"
    if text.startswith("missing"):
        return text[:50]
    if text in {"duplicate", "inconsistent", "invalid_format"}:
        return text
    return text[:50]


def project_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="S07 核心数据入库闭环")
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID, help="S06 清洗批次号")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help="S06 标准 CSV 目录")
    parser.add_argument("--quality-dir", type=Path, default=DEFAULT_QUALITY_DIR, help="S06 质量文件目录")
    parser.add_argument("--dry-run", action="store_true", help="只读取、映射和统计，不写入 MySQL")
    parser.add_argument("--skip-quality", action="store_true", help="不写入 data_quality_issues 表")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging()
    set_trace_id(f"s07-load-{args.batch_id}")
    summary = run_load(
        batch_id=args.batch_id,
        input_dir=args.input_dir,
        quality_dir=args.quality_dir,
        dry_run=args.dry_run,
        skip_quality=args.skip_quality,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
