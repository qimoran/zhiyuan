"""S13 Spark 分析结果写回 MySQL。

读取 ``data/analysis`` 下的三个 Spark 结果 CSV，映射 MySQL 主键后写入
``major_statistics``。没有拟录取数据时，拟录取相关字段保持空值。
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.config import PROJECT_ROOT
from src.common.database import fetch_all, mysql_connection

DEFAULT_BATCH_ID = "20260616_full_v2"


@dataclass(frozen=True)
class AnalysisFiles:
    plan_trend: Path
    score_trend: Path
    major_heat: Path


def write_analysis_result(batch_id: str, input_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    files = AnalysisFiles(
        plan_trend=input_dir / f"spark_plan_trend_{batch_id}.csv",
        score_trend=input_dir / f"spark_score_trend_{batch_id}.csv",
        major_heat=input_dir / f"spark_major_heat_{batch_id}.csv",
    )
    for path in (files.plan_trend, files.score_trend, files.major_heat):
        if not path.exists():
            raise FileNotFoundError(f"S13 Spark 输出文件不存在：{path}")

    plan_rows = read_csv(files.plan_trend)
    score_by_key = {row_key(row): row for row in read_csv(files.score_trend)}
    heat_by_key = {row_key(row): row for row in read_csv(files.major_heat)}
    major_map = load_major_map()

    prepared = []
    skipped = []
    for row in plan_rows:
        key = row_key(row)
        major_ref = major_map.get(identity_key(row))
        if not major_ref:
            skipped.append({"key": "|".join(key), "reason": "未匹配到 MySQL 专业主键"})
            continue
        score_row = score_by_key.get(key, {})
        heat_row = heat_by_key.get(key, {})
        prepared.append(
            {
                "year": to_int(row.get("year")),
                "university_id": major_ref["university_id"],
                "major_id": major_ref["major_id"],
                "plan_count": to_int(row.get("plan_count")),
                "admission_count": None,
                "min_initial_score": None,
                "avg_initial_score": None,
                "max_initial_score": None,
                "score_line": to_int(score_row.get("score_line")),
                "plan_change_rate": to_float(row.get("plan_change_rate")),
                "heat_score": to_float(heat_row.get("heat_score")),
                "data_quality_level": choose_quality(score_row, heat_row),
            }
        )

    summary = {
        "batch_id": batch_id,
        "input_dir": project_relative(input_dir),
        "planned_count": len(prepared),
        "skipped_count": len(skipped),
        "dry_run": dry_run,
    }
    if dry_run:
        return summary

    run_id = create_pipeline_run(batch_id, input_dir, len(prepared))
    try:
        upsert_major_statistics(prepared)
        update_pipeline_run(run_id, "success", len(prepared), len(skipped), None)
    except Exception as exc:
        update_pipeline_run(run_id, "failed", 0, len(prepared), str(exc))
        raise
    return summary


def load_major_map() -> dict[tuple[str, str, str, str], dict[str, int]]:
    rows = fetch_all(
        """
        SELECT
          u.candidate_school_id,
          u.id AS university_id,
          d.department_name,
          m.id AS major_id,
          m.major_code,
          m.research_direction
        FROM majors m
        JOIN universities u ON u.id = m.university_id
        JOIN departments d ON d.id = m.department_id
        """
    )
    result = {}
    for row in rows:
        key = (
            str(row["candidate_school_id"]),
            clean(row["department_name"]),
            clean(row["major_code"]),
            clean(row["research_direction"]),
        )
        result[key] = {"university_id": int(row["university_id"]), "major_id": int(row["major_id"])}
    return result


def upsert_major_statistics(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO major_statistics (
                  year, university_id, major_id, plan_count, admission_count,
                  min_initial_score, avg_initial_score, max_initial_score,
                  score_line, plan_change_rate, heat_score, data_quality_level
                )
                VALUES (
                  %(year)s, %(university_id)s, %(major_id)s, %(plan_count)s, %(admission_count)s,
                  %(min_initial_score)s, %(avg_initial_score)s, %(max_initial_score)s,
                  %(score_line)s, %(plan_change_rate)s, %(heat_score)s, %(data_quality_level)s
                )
                ON DUPLICATE KEY UPDATE
                  plan_count = VALUES(plan_count),
                  admission_count = VALUES(admission_count),
                  min_initial_score = VALUES(min_initial_score),
                  avg_initial_score = VALUES(avg_initial_score),
                  max_initial_score = VALUES(max_initial_score),
                  score_line = VALUES(score_line),
                  plan_change_rate = VALUES(plan_change_rate),
                  heat_score = VALUES(heat_score),
                  data_quality_level = VALUES(data_quality_level)
                """,
                rows,
            )
        connection.commit()


def create_pipeline_run(batch_id: str, input_dir: Path, total_count: int) -> int:
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (
                  task_name, task_type, status, input_path, output_path,
                  total_count, success_count, failed_count, started_at
                )
                VALUES (
                  %(task_name)s, 'spark_analysis', 'running', %(input_path)s, 'mysql:major_statistics',
                  %(total_count)s, 0, 0, NOW()
                )
                """,
                {
                    "task_name": f"S13_write_analysis_{batch_id}",
                    "input_path": project_relative(input_dir),
                    "total_count": total_count,
                },
            )
            run_id = int(cursor.lastrowid)
        connection.commit()
    return run_id


def update_pipeline_run(
    run_id: int,
    status: str,
    success_count: int,
    failed_count: int,
    error_message: str | None,
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
                    "id": run_id,
                    "status": status,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "error_message": error_message,
                },
            )
        connection.commit()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def row_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        clean(row.get("year")),
        clean(row.get("school_id")),
        clean(row.get("department_name")),
        clean(row.get("major_code")),
        clean(row.get("research_direction")),
    )


def identity_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        clean(row.get("school_id")),
        clean(row.get("department_name")),
        clean(row.get("major_code")),
        clean(row.get("research_direction")),
    )


def choose_quality(score_row: dict[str, Any], heat_row: dict[str, Any]) -> str:
    if score_row.get("score_line") and heat_row.get("heat_score"):
        return "high"
    if score_row.get("score_line") or heat_row.get("heat_score"):
        return "medium"
    return "low"


def to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean(value: Any) -> str:
    return str(value or "").strip()


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="S13 Spark 分析结果写回 MySQL")
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--input-dir", type=Path, default=PROJECT_ROOT / "data" / "analysis")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = write_analysis_result(args.batch_id, args.input_dir, args.dry_run)
    print(summary)


if __name__ == "__main__":
    main()
