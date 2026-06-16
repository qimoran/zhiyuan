"""S04 候选库入库与来源登记。

本模块优先消费 S03 V2 统一爬虫生成的 `school_list.json`，并按学校去重。
如果原始 JSON 不存在，则兜底读取 `kaoyan_v2_integrated_<batch_id>.csv` 大合集。
完成三件事：
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
UNIFIED_API_URL = "https://api.kaoyan.cn/pc/school/schoolList,/pc/school/planListV2,/pc/school/planDetailV2,/pc/school/schoolScore,/pc/school/schoolLevelRate"
DEFAULT_INTEGRATED_DIR = PROJECT_ROOT / "data" / "processed" / "kaoyan_v2_integrated"
DEFAULT_RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "kaoyan_v2"
SCHOOL_LIST_DOCUMENT_TYPE = "school_list"


@dataclass(frozen=True)
class UniversityCandidate:
    """掌上考研候选招生单位标准化记录。"""

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


@dataclass(frozen=True)
class SourceSelection:
    """S04 本次使用的数据源。"""

    input_type: str
    batch_id: str
    candidates_path: Path
    raw_batch_dir: Path
    csv_path: Path | None


def school_list_json_path(batch_id: str) -> Path:
    """返回指定批次 schoolList 聚合 JSON 路径。"""
    return DEFAULT_RAW_ROOT / batch_id / "school_list" / "school_list.json"


def find_latest_source_csv(
    integrated_dir: Path = DEFAULT_INTEGRATED_DIR,
) -> Path:
    """查找最新 V2 统一整合 CSV。"""
    integrated_candidates = sorted(
        integrated_dir.glob("kaoyan_v2_integrated_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if integrated_candidates:
        return integrated_candidates[0]

    raise FileProcessError(f"未找到 V2 统一整合 CSV：{integrated_dir}")


def find_latest_school_list_json(raw_root: Path = DEFAULT_RAW_ROOT) -> Path:
    """查找最新的 schoolList 聚合 JSON。"""
    candidates = sorted(
        raw_root.glob("*/school_list/school_list.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise FileProcessError(f"未找到 V2 school_list.json：{raw_root}")


def extract_batch_id(csv_path: Path) -> str:
    """从 V2 统一整合 CSV 提取批次号。"""
    stem = csv_path.stem
    prefix = "kaoyan_v2_integrated_"
    if stem.startswith(prefix):
        return stem[len(prefix) :]
    raise ValidationError(f"候选库文件名不符合规范：{csv_path.name}")


def extract_batch_id_from_school_list_json(json_path: Path) -> str:
    """从 data/raw/kaoyan_v2/<batch_id>/school_list/school_list.json 提取批次号。"""
    try:
        return json_path.resolve().parents[1].name
    except IndexError as exc:
        raise ValidationError(f"school_list.json 路径不符合规范：{json_path}") from exc


def parse_batch_datetime(batch_id: str) -> datetime | None:
    """把批次号解析为采集时间，无法解析时返回 None。"""
    try:
        return datetime.strptime(batch_id, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def select_source(batch_id: str | None = None, csv_path: Path | None = None) -> SourceSelection:
    """选择 S04 输入源：优先 school_list.json，兜底 CSV。"""
    if batch_id:
        json_path = school_list_json_path(batch_id).resolve()
        inferred_csv = DEFAULT_INTEGRATED_DIR / f"kaoyan_v2_integrated_{batch_id}.csv"
        if json_path.exists():
            return SourceSelection(
                input_type="school_list_json",
                batch_id=batch_id,
                candidates_path=json_path,
                raw_batch_dir=(DEFAULT_RAW_ROOT / batch_id).resolve(),
                csv_path=inferred_csv.resolve() if inferred_csv.exists() else None,
            )
        if csv_path is None and inferred_csv.exists():
            csv_path = inferred_csv
        if csv_path is None:
            raise FileProcessError(
                f"批次 {batch_id} 未找到 school_list.json，也未找到兜底 CSV："
                f"{json_path}；{inferred_csv}"
            )

    if csv_path:
        selected_csv = csv_path.resolve()
        selected_batch_id = extract_batch_id(selected_csv)
        return SourceSelection(
            input_type="integrated_csv",
            batch_id=selected_batch_id,
            candidates_path=selected_csv,
            raw_batch_dir=(DEFAULT_RAW_ROOT / selected_batch_id).resolve(),
            csv_path=selected_csv,
        )

    try:
        json_path = find_latest_school_list_json().resolve()
    except FileProcessError:
        selected_csv = find_latest_source_csv().resolve()
        selected_batch_id = extract_batch_id(selected_csv)
        return SourceSelection(
            input_type="integrated_csv",
            batch_id=selected_batch_id,
            candidates_path=selected_csv,
            raw_batch_dir=(DEFAULT_RAW_ROOT / selected_batch_id).resolve(),
            csv_path=selected_csv,
        )

    selected_batch_id = extract_batch_id_from_school_list_json(json_path)
    inferred_csv = DEFAULT_INTEGRATED_DIR / f"kaoyan_v2_integrated_{selected_batch_id}.csv"
    return SourceSelection(
        input_type="school_list_json",
        batch_id=selected_batch_id,
        candidates_path=json_path,
        raw_batch_dir=(DEFAULT_RAW_ROOT / selected_batch_id).resolve(),
        csv_path=inferred_csv.resolve() if inferred_csv.exists() else None,
    )


def read_university_candidates(csv_path: Path) -> list[UniversityCandidate]:
    """读取并校验候选学校。

    V2 大合集 CSV 按 `school_id + school_name` 去重得到候选学校。
    """
    if not csv_path.exists():
        raise FileProcessError(f"候选库 CSV 不存在：{csv_path}")

    candidates: list[UniversityCandidate] = []
    school_id_to_name: dict[int, str] = {}
    name_to_school_id: dict[str, int] = {}

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        if "school_id" not in fieldnames or "school_name" not in fieldnames:
            raise ValidationError(f"V2 大合集 CSV 缺少 school_id 或 school_name 字段：{csv_path}")

        for line_no, row in enumerate(reader, start=2):
            school_id = _to_int(row.get("school_id"))
            school_name = _clean_text(row.get("school_name"))
            if school_id is None:
                raise ValidationError(f"第 {line_no} 行缺少合法 school_id")
            if not school_name:
                raise ValidationError(f"第 {line_no} 行缺少 school_name")
            if school_id in school_id_to_name:
                if school_id_to_name[school_id] != school_name:
                    raise ValidationError(f"候选库 CSV 中 school_id={school_id} 对应多个学校名称")
                continue
            if school_name in name_to_school_id:
                raise ValidationError(f"候选库 CSV 中学校名称对应多个 school_id：{school_name}")

            school_id_to_name[school_id] = school_name
            name_to_school_id[school_name] = school_id

            candidates.append(
                UniversityCandidate(
                    candidate_school_id=school_id,
                    university_name=school_name,
                    province=_clean_text(row.get("province_name")) or "重庆",
                    province_area=_normalize_province_area(row.get("province_area")),
                    school_type=_clean_text(row.get("type_name")),
                    school_org_type=_clean_text(row.get("type_school_name")),
                    school_level=_clean_text(row.get("school_level")),
                    recruit_number_reference=_to_int(row.get("school_recruit_number_reference"))
                    or _to_int(row.get("recruit_number_int"))
                    or _to_int(row.get("recruit_number")),
                    major_number_reference=_to_int(row.get("school_major_number_reference"))
                    or _to_int(row.get("major_number")),
                    rk_rank=_clean_text(row.get("rk_rank")),
                )
            )

    if not candidates:
        raise ValidationError(f"候选库 CSV 为空：{csv_path}")
    return candidates


def read_university_candidates_from_school_list_json(json_path: Path) -> list[UniversityCandidate]:
    """读取并校验 schoolList 聚合 JSON。"""
    if not json_path.exists():
        raise FileProcessError(f"schoolList 聚合 JSON 不存在：{json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValidationError(f"schoolList 聚合 JSON 缺少 items 数组：{json_path}")

    candidates: list[UniversityCandidate] = []
    school_id_to_name: dict[int, str] = {}
    name_to_school_id: dict[str, int] = {}

    for index, row in enumerate(items, start=1):
        if not isinstance(row, dict):
            raise ValidationError(f"schoolList 第 {index} 条不是对象")
        school_id = _to_int(row.get("school_id"))
        school_name = _clean_text(row.get("school_name"))
        if school_id is None:
            raise ValidationError(f"schoolList 第 {index} 条缺少合法 school_id")
        if not school_name:
            raise ValidationError(f"schoolList 第 {index} 条缺少 school_name")
        if school_id in school_id_to_name:
            if school_id_to_name[school_id] != school_name:
                raise ValidationError(f"schoolList 中 school_id={school_id} 对应多个学校名称")
            continue
        if school_name in name_to_school_id:
            raise ValidationError(f"schoolList 中学校名称对应多个 school_id：{school_name}")

        school_id_to_name[school_id] = school_name
        name_to_school_id[school_name] = school_id
        candidates.append(
            UniversityCandidate(
                candidate_school_id=school_id,
                university_name=school_name,
                province=_clean_text(row.get("province_name")) or "重庆",
                province_area=_normalize_province_area(row.get("province_area")),
                school_type=_clean_text(row.get("type_name")),
                school_org_type=_clean_text(row.get("type_school_name")),
                school_level=_school_level_from_raw(row),
                recruit_number_reference=_to_int(row.get("recruit_number")),
                major_number_reference=_to_int(row.get("major_number")),
                rk_rank=_clean_text(row.get("rk_rank")),
            )
        )

    if not candidates:
        raise ValidationError(f"schoolList 聚合 JSON 为空：{json_path}")
    return candidates


def read_candidates_from_selection(selection: SourceSelection) -> list[UniversityCandidate]:
    """按选择的数据源读取候选学校。"""
    if selection.input_type == "school_list_json":
        return read_university_candidates_from_school_list_json(selection.candidates_path)
    return read_university_candidates(selection.candidates_path)


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
    parsed_output_path: Path | None,
    fetched_count: int,
    input_type: str,
) -> int:
    """写入 crawler_runs，并返回主键 ID。"""
    request_params = {
        "province_id": 50,
        "years": [2024, 2025, 2026],
        "page": "auto",
        "limit": "auto",
        "batch_id": batch_id,
        "input_type": input_type,
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
                "crawler_name": "kaoyan_v2",
                "target_url": TARGET_URL,
                "api_url": UNIFIED_API_URL,
                "request_params_json": json.dumps(request_params, ensure_ascii=False),
                "raw_output_path": _project_relative(raw_output_path),
                "parsed_output_path": _project_relative(parsed_output_path) if parsed_output_path else None,
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
    """登记来源资料。

    school_list 候选来源按学校、类型、标题保持一条当前记录，重复跑样本/全量时更新路径。
    其他资料仍按学校、类型、标题、URL、路径去重。
    """
    with connection.cursor() as cursor:
        if document_type == SCHOOL_LIST_DOCUMENT_TYPE:
            cursor.execute(
                """
                SELECT id
                FROM source_documents
                WHERE university_id = %(university_id)s
                  AND document_type = %(document_type)s
                  AND document_title = %(document_title)s
                LIMIT 1
                """,
                {
                    "university_id": university_id,
                    "document_type": document_type,
                    "document_title": document_title,
                },
            )
        else:
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
                    source_url = %(source_url)s,
                    local_path = %(local_path)s,
                    process_status = 'loaded',
                    official_verified = 0,
                    remark = %(remark)s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %(id)s
                """,
                {
                    "id": existing["id"],
                    "source_url": source_url,
                    "local_path": local_path,
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
    source_path: Path,
    collector: str,
) -> int:
    """为每所学校登记一条掌上考研候选库来源记录。"""
    registered = 0
    local_path = _project_relative(source_path)
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
    batch_id: str | None = None,
    raw_dir: Path | None = None,
    collector: str = "S04",
    dry_run: bool = False,
) -> dict[str, Any]:
    """执行 S04 候选库入库与来源登记。"""
    selection = select_source(batch_id=batch_id, csv_path=csv_path)
    selected_raw_dir = (raw_dir or selection.raw_batch_dir).resolve()
    candidates = read_candidates_from_selection(selection)
    candidate_crawled_at = parse_batch_datetime(selection.batch_id)

    summary: dict[str, Any] = {
        "batch_id": selection.batch_id,
        "input_type": selection.input_type,
        "candidate_source_path": _project_relative(selection.candidates_path),
        "csv_path": _project_relative(selection.csv_path) if selection.csv_path else None,
        "csv_exists": bool(selection.csv_path and selection.csv_path.exists()),
        "raw_output_path": _project_relative(selected_raw_dir),
        "candidate_count": len(candidates),
        "candidate_schools": [
            {
                "school_id": candidate.candidate_school_id,
                "school_name": candidate.university_name,
            }
            for candidate in candidates
        ],
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
                batch_id=selection.batch_id,
                raw_output_path=selected_raw_dir,
                parsed_output_path=selection.csv_path,
                fetched_count=len(candidates),
                input_type=selection.input_type,
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
                source_path=selection.candidates_path,
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
        "--batch-id",
        default=None,
        help="V2 爬虫批次号；优先读取 data/raw/kaoyan_v2/<batch_id>/school_list/school_list.json",
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        type=Path,
        default=None,
        help="候选库 CSV 路径；当 batch_id 对应 JSON 不存在时作为兜底输入",
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
        help="只读取和校验输入源，不写入数据库",
    )
    return parser


def main() -> None:
    setup_logging()
    args = build_arg_parser().parse_args()
    set_trace_id("s04-source-registry")
    summary = run_registry(
        args.csv_path,
        batch_id=args.batch_id,
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


def _school_level_from_raw(row: dict[str, Any]) -> str:
    """按掌上考研 schoolList 标志位生成学校层次。"""
    levels: list[str] = []
    if _to_int(row.get("is_985")) == 1:
        levels.append("985")
    if _to_int(row.get("is_211")) == 1:
        levels.append("211")
    if _to_int(row.get("syl")) == 1:
        levels.append("双一流")
    if _to_int(row.get("is_zihuaxian")) == 1:
        levels.append("自划线")
    return " / ".join(levels) if levels else "普通院校"


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
