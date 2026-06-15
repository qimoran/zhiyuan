"""S04 候选库入库与来源登记。

本模块消费 S03 生成的 `university_candidates_<batch_id>.csv`，完成三件事：
1. 登记 `crawler_runs` 爬虫批次；
2. 幂等写入 `universities` 候选招生单位；
3. 为每所学校登记掌上考研候选库来源，便于后续追溯。
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.common.config import PROJECT_ROOT
from src.common.database import mysql_connection
from src.common.exceptions import FileProcessError, ValidationError
from src.common.logger import get_logger, setup_logging
from src.common.trace import set_trace_id

logger = get_logger("etl")

TARGET_URL = "https://www.kaoyan.cn/school-list/50-0-0"
API_URL = "https://api.kaoyan.cn/pc/school/schoolList"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "universities"
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "kaoyan_school_list"
SCHOOL_LIST_DOCUMENT_TYPE = "school_list"


@dataclass(frozen=True)
class UniversityCandidate:
    """掌上考研候选招生单位 CSV 中的一行标准化记录。"""

    candidate_school_id: int
    university_name: str
    province: str
    province_area: str
    school_type: str | None
    school_org_type: str | None
    school_level: str | None
    recruit_number_reference: int | None
    major_number_reference: int | None
    rk_rank: str | None


def find_latest_university_candidates_csv(directory: Path = DEFAULT_PROCESSED_DIR) -> Path:
    """查找最新的候选库 CSV。"""
    candidates = sorted(
        directory.glob("university_candidates_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileProcessError(f"未找到候选库 CSV：{directory}")
    return candidates[0]


def extract_batch_id(csv_path: Path) -> str:
    """从 `university_candidates_<batch_id>.csv` 提取批次号。"""
    stem = csv_path.stem
    prefix = "university_candidates_"
    if not stem.startswith(prefix):
        raise ValidationError(f"候选库文件名不符合规范：{csv_path.name}")
    return stem[len(prefix) :]


def parse_batch_datetime(batch_id: str) -> datetime | None:
    """把批次号解析为采集时间，无法解析时返回 None。"""
    try:
        return datetime.strptime(batch_id, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def read_university_candidates(csv_path: Path) -> list[UniversityCandidate]:
    """读取并校验候选库 CSV。"""
    if not csv_path.exists():
        raise FileProcessError(f"候选库 CSV 不存在：{csv_path}")

    candidates: list[UniversityCandidate] = []
    seen_school_ids: set[int] = set()
    seen_names: set[str] = set()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for line_no, row in enumerate(reader, start=2):
            school_id = _to_int(row.get("school_id"))
            school_name = _clean_text(row.get("school_name"))
            if school_id is None:
                raise ValidationError(f"第 {line_no} 行缺少合法 school_id")
            if not school_name:
                raise ValidationError(f"第 {line_no} 行缺少 school_name")
            if school_id in seen_school_ids:
                raise ValidationError(f"候选库 CSV 中 school_id 重复：{school_id}")
            if school_name in seen_names:
                raise ValidationError(f"候选库 CSV 中学校名称重复：{school_name}")

            seen_school_ids.add(school_id)
            seen_names.add(school_name)

            candidates.append(
                UniversityCandidate(
                    candidate_school_id=school_id,
                    university_name=school_name,
                    province=_clean_text(row.get("province_name")) or "重庆",
                    province_area=_normalize_province_area(row.get("province_area")),
                    school_type=_clean_text(row.get("type_name")),
                    school_org_type=_clean_text(row.get("type_school_name")),
                    school_level=_clean_text(row.get("school_level")),
                    recruit_number_reference=_to_int(row.get("recruit_number_int"))
                    or _to_int(row.get("recruit_number")),
                    major_number_reference=_to_int(row.get("major_number")),
                    rk_rank=_clean_text(row.get("rk_rank")),
                )
            )

    if not candidates:
        raise ValidationError(f"候选库 CSV 为空：{csv_path}")
    return candidates


def build_coverage_priority(candidate: UniversityCandidate) -> str:
    """根据学校层次给第一版覆盖优先级赋初值。"""
    level = candidate.school_level or ""
    if "985" in level or "自划线" in level:
        return "P0"
    if "211" in level or "双一流" in level:
        return "P1"
    if candidate.school_org_type and "科研" in candidate.school_org_type:
        return "P2"
    return "P2"


def save_crawler_run(
    connection,
    *,
    batch_id: str,
    raw_output_path: Path,
    parsed_output_path: Path,
    fetched_count: int,
) -> int:
    """写入 crawler_runs，并返回主键 ID。"""
    request_params = {
        "province_id": 50,
        "page": "auto",
        "limit": 20,
        "batch_id": batch_id,
    }
    started_at = parse_batch_datetime(batch_id)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO crawler_runs (
              crawler_name, target_url, api_url, request_params_json,
              raw_output_path, parsed_output_path, status, total_count,
              fetched_count, error_message, started_at, finished_at
            )
            VALUES (
              %(crawler_name)s, %(target_url)s, %(api_url)s, %(request_params_json)s,
              %(raw_output_path)s, %(parsed_output_path)s, %(status)s, %(total_count)s,
              %(fetched_count)s, NULL, COALESCE(%(started_at)s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP
            )
            """,
            {
                "crawler_name": "kaoyan_school_list",
                "target_url": TARGET_URL,
                "api_url": API_URL,
                "request_params_json": json.dumps(request_params, ensure_ascii=False),
                "raw_output_path": _project_relative(raw_output_path),
                "parsed_output_path": _project_relative(parsed_output_path),
                "status": "success",
                "total_count": fetched_count,
                "fetched_count": fetched_count,
                "started_at": started_at,
            },
        )
        return int(cursor.lastrowid)


def upsert_university_candidates(
    connection,
    candidates: list[UniversityCandidate],
    *,
    crawler_run_id: int,
    candidate_source_url: str = TARGET_URL,
    candidate_crawled_at: datetime | None,
) -> int:
    """把候选库写入 universities，重复执行时更新已有记录。"""
    sql = """
        INSERT INTO universities (
          candidate_school_id, university_name, province, city, province_area,
          school_type, school_org_type, school_level, coverage_priority,
          candidate_source_url, recruit_number_reference, major_number_reference,
          crawler_run_id, candidate_crawled_at, official_verified_status, remark
        )
        VALUES (
          %(candidate_school_id)s, %(university_name)s, %(province)s, %(city)s, %(province_area)s,
          %(school_type)s, %(school_org_type)s, %(school_level)s, %(coverage_priority)s,
          %(candidate_source_url)s, %(recruit_number_reference)s, %(major_number_reference)s,
          %(crawler_run_id)s, %(candidate_crawled_at)s, 'pending', %(remark)s
        )
        ON DUPLICATE KEY UPDATE
          province = VALUES(province),
          city = VALUES(city),
          province_area = VALUES(province_area),
          school_type = VALUES(school_type),
          school_org_type = VALUES(school_org_type),
          school_level = VALUES(school_level),
          coverage_priority = VALUES(coverage_priority),
          candidate_source_url = VALUES(candidate_source_url),
          recruit_number_reference = VALUES(recruit_number_reference),
          major_number_reference = VALUES(major_number_reference),
          crawler_run_id = VALUES(crawler_run_id),
          candidate_crawled_at = VALUES(candidate_crawled_at),
          remark = VALUES(remark)
    """
    affected = 0
    with connection.cursor() as cursor:
        for candidate in candidates:
            affected += cursor.execute(
                sql,
                {
                    "candidate_school_id": candidate.candidate_school_id,
                    "university_name": candidate.university_name,
                    "province": candidate.province,
                    "city": "重庆市",
                    "province_area": candidate.province_area,
                    "school_type": candidate.school_type,
                    "school_org_type": candidate.school_org_type,
                    "school_level": candidate.school_level,
                    "coverage_priority": build_coverage_priority(candidate),
                    "candidate_source_url": candidate_source_url,
                    "recruit_number_reference": candidate.recruit_number_reference,
                    "major_number_reference": candidate.major_number_reference,
                    "crawler_run_id": crawler_run_id,
                    "candidate_crawled_at": candidate_crawled_at,
                    "remark": _build_university_remark(candidate),
                },
            )
    return affected


def register_source_document(
    connection,
    *,
    university_id: int,
    document_type: str,
    document_title: str,
    source_url: str,
    local_path: str,
    collector: str,
    remark: str,
) -> int:
    """登记来源资料，按同一学校、类型、标题、URL、路径去重。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM source_documents
            WHERE university_id = %(university_id)s
              AND document_type = %(document_type)s
              AND document_title = %(document_title)s
              AND COALESCE(source_url, '') = COALESCE(%(source_url)s, '')
              AND COALESCE(local_path, '') = COALESCE(%(local_path)s, '')
            LIMIT 1
            """,
            {
                "university_id": university_id,
                "document_type": document_type,
                "document_title": document_title,
                "source_url": source_url,
                "local_path": local_path,
            },
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE source_documents
                SET collector = %(collector)s,
                    process_status = 'loaded',
                    official_verified = 0,
                    remark = %(remark)s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %(id)s
                """,
                {
                    "id": existing["id"],
                    "collector": collector,
                    "remark": remark,
                },
            )
            return int(existing["id"])

        cursor.execute(
            """
            INSERT INTO source_documents (
              university_id, year, document_type, document_title, source_url,
              local_path, published_date, collector, process_status,
              official_verified, remark
            )
            VALUES (
              %(university_id)s, NULL, %(document_type)s, %(document_title)s, %(source_url)s,
              %(local_path)s, NULL, %(collector)s, 'loaded',
              0, %(remark)s
            )
            """,
            {
                "university_id": university_id,
                "document_type": document_type,
                "document_title": document_title,
                "source_url": source_url,
                "local_path": local_path,
                "collector": collector,
                "remark": remark,
            },
        )
        return int(cursor.lastrowid)


def update_source_status(connection, source_id: int, status: str, remark: str | None = None) -> int:
    """更新来源资料处理状态。"""
    with connection.cursor() as cursor:
        return cursor.execute(
            """
            UPDATE source_documents
            SET process_status = %(status)s,
                remark = COALESCE(%(remark)s, remark),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(source_id)s
            """,
            {"source_id": source_id, "status": status, "remark": remark},
        )


def register_candidate_sources(
    connection,
    candidates: list[UniversityCandidate],
    *,
    parsed_output_path: Path,
    collector: str,
) -> int:
    """为每所学校登记一条掌上考研候选库来源记录。"""
    registered = 0
    local_path = _project_relative(parsed_output_path)
    school_ids = [candidate.candidate_school_id for candidate in candidates]
    placeholders = ", ".join(["%s"] * len(school_ids))
    sql = f"""
        SELECT id, candidate_school_id
        FROM universities
        WHERE candidate_school_id IN ({placeholders})
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, school_ids)
        university_id_by_school_id = {
            int(row["candidate_school_id"]): int(row["id"])
            for row in cursor.fetchall()
        }

    for candidate in candidates:
        university_id = university_id_by_school_id.get(candidate.candidate_school_id)
        if not university_id:
            raise ValidationError(f"未找到已入库学校：{candidate.university_name}")

        register_source_document(
            connection,
            university_id=university_id,
            document_type=SCHOOL_LIST_DOCUMENT_TYPE,
            document_title="掌上考研重庆院校库候选来源",
            source_url=TARGET_URL,
            local_path=local_path,
            collector=collector,
            remark="第三方公开候选库来源，非官网核验资料；用于初始化重庆研招单位范围。",
        )
        registered += 1
    return registered


def run_registry(
    csv_path: Path | None = None,
    *,
    raw_dir: Path | None = None,
    collector: str = "S04",
    dry_run: bool = False,
) -> dict[str, Any]:
    """执行 S04 候选库入库与来源登记。"""
    selected_csv = csv_path or find_latest_university_candidates_csv()
    selected_csv = selected_csv.resolve()
    batch_id = extract_batch_id(selected_csv)
    selected_raw_dir = (raw_dir or DEFAULT_RAW_ROOT / batch_id).resolve()
    candidates = read_university_candidates(selected_csv)
    candidate_crawled_at = parse_batch_datetime(batch_id)

    summary: dict[str, Any] = {
        "batch_id": batch_id,
        "csv_path": _project_relative(selected_csv),
        "raw_output_path": _project_relative(selected_raw_dir),
        "candidate_count": len(candidates),
        "dry_run": dry_run,
    }

    if dry_run:
        summary.update(
            {
                "crawler_run_id": None,
                "universities_affected_rows": 0,
                "source_documents_registered": 0,
                "status": "dry_run",
            }
        )
        return summary

    with mysql_connection() as connection:
        try:
            crawler_run_id = save_crawler_run(
                connection,
                batch_id=batch_id,
                raw_output_path=selected_raw_dir,
                parsed_output_path=selected_csv,
                fetched_count=len(candidates),
            )
            affected_rows = upsert_university_candidates(
                connection,
                candidates,
                crawler_run_id=crawler_run_id,
                candidate_crawled_at=candidate_crawled_at,
            )
            source_count = register_candidate_sources(
                connection,
                candidates,
                parsed_output_path=selected_csv,
                collector=collector,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            logger.exception("S04 候选库入库失败，已回滚当前事务")
            raise

    summary.update(
        {
            "crawler_run_id": crawler_run_id,
            "universities_affected_rows": affected_rows,
            "source_documents_registered": source_count,
            "status": "success",
        }
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="S04 候选库入库与来源登记")
    parser.add_argument(
        "--csv",
        dest="csv_path",
        type=Path,
        default=None,
        help="候选库 CSV 路径；默认读取 data/processed/universities 下最新文件",
    )
    parser.add_argument(
        "--raw-dir",
        dest="raw_dir",
        type=Path,
        default=None,
        help="原始 JSON 批次目录；默认按 CSV 批次号推导",
    )
    parser.add_argument(
        "--collector",
        default="S04",
        help="来源登记采集人或阶段标识，默认 S04",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只读取和校验 CSV，不写入数据库",
    )
    return parser


def main() -> None:
    setup_logging()
    args = build_arg_parser().parse_args()
    set_trace_id("s04-source-registry")
    summary = run_registry(
        args.csv_path,
        raw_dir=args.raw_dir,
        collector=args.collector,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Any) -> int | None:
    text = _clean_text(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _normalize_province_area(value: Any) -> str:
    text = _clean_text(value)
    if text in {"A", "A区"}:
        return "A区"
    if text in {"B", "B区"}:
        return "B区"
    return text or "A区"


def _project_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _build_university_remark(candidate: UniversityCandidate) -> str:
    parts: list[str] = ["掌上考研候选库初始化"]
    if candidate.rk_rank:
        parts.append(f"软科/第三方排名参考：{candidate.rk_rank}")
    return "；".join(parts)


if __name__ == "__main__":
    main()
