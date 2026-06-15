"""掌上考研院校库爬虫：抓取重庆研招单位候选库（开发步骤文档 S03）。

数据来源
--------
- 目标页面 https://www.kaoyan.cn/school-list/50-0-0
- 实际接口 POST https://api.kaoyan.cn/pc/school/schoolList

采集逻辑
--------
1. 固定请求重庆（province_id=50），分页参数为 page 与 limit。
2. 自动翻页，直到累计抓取数量等于接口返回的 total。
3. 每页原始响应落盘到 data/raw/kaoyan_school_list/<batch_id>/page_<n>.json。
4. 解析后的标准化候选库写入 data/processed/universities/university_candidates_<batch_id>.csv。

本脚本仅使用 requests 完成接口请求，不依赖浏览器自动化，符合 S03 完成标准。
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from src.common.logger import get_logger, setup_logging
from src.common.trace import set_trace_id

logger = get_logger("crawler")

# 目标页面与实际接口
TARGET_URL = "https://www.kaoyan.cn/school-list/50-0-0"
API_URL = "https://api.kaoyan.cn/pc/school/schoolList"

# 重庆研招单位固定参数
PROVINCE_ID = 50
PROVINCE_NAME = "重庆"

# 采集控制参数
PAGE_SIZE = 20
REQUEST_TIMEOUT = 20
MAX_RETRIES = 2
PAGE_DELAY = 0.5  # 翻页间隔，避免对接口造成压力
MAX_PAGES = 50  # 分页保护上限，防止接口异常导致死循环

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "kaoyan_school_list"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "universities"

# 与开发步骤文档 S03 字段清单保持一致的标准字段
BASE_FIELDS = [
    "school_id",
    "school_name",
    "province_name",
    "province_area",
    "type_name",
    "type_school_name",
    "is_985",
    "is_211",
    "syl",
    "is_zihuaxian",
    "recruit_number",
    "major_number",
]
# 标准化辅助字段：school_level 供 S04 写入 universities.school_level，
# recruit_number_int 供 S04 写入 universities.recruit_number_reference。
EXTRA_FIELDS = ["school_level", "recruit_number_int", "rk_rank"]
CSV_FIELDS = BASE_FIELDS + EXTRA_FIELDS

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.kaoyan.cn",
    "Referer": "https://www.kaoyan.cn/",
}


def _is_yes(value: Any) -> bool:
    """掌上考研标志位统一为：1 表示是，其余值表示否。"""
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return False


def _to_int(value: Any) -> int | None:
    """安全转换为整数；空值或非数字返回 None。"""
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def build_school_level(record: dict[str, Any]) -> str:
    """根据 985、211、双一流、自划线标志位组合学校层次标签。

    全部标志位为否则判定为“普通院校”，与 universities.school_level 注释一致。
    """
    tags: list[str] = []
    if _is_yes(record.get("is_985")):
        tags.append("985")
    if _is_yes(record.get("is_211")):
        tags.append("211")
    if _is_yes(record.get("syl")):
        tags.append("双一流")
    if _is_yes(record.get("is_zihuaxian")):
        tags.append("自划线")
    return " / ".join(tags) if tags else "普通院校"


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """把单条原始记录整理成标准化候选库字段。"""
    normalized = {field: raw.get(field) for field in BASE_FIELDS}
    normalized["school_level"] = build_school_level(raw)
    normalized["recruit_number_int"] = _to_int(raw.get("recruit_number"))
    normalized["rk_rank"] = raw.get("rk_rank")
    return normalized


def fetch_page(page: int, limit: int = PAGE_SIZE) -> dict[str, Any]:
    """请求单页院校列表，返回完整响应体字典。

    接口失败、超时或返回非成功 code 时抛出 RuntimeError，由调用方记录并决定是否中断。
    """
    payload = {"province_id": PROVINCE_ID, "page": page, "limit": limit}
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                API_URL,
                headers=DEFAULT_HEADERS,
                data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            body = response.json()
        except requests.Timeout:
            last_error = f"请求超时 page={page}"
            logger.warning("第 %s 页请求超时，第 %s/%s 次重试", page, attempt, MAX_RETRIES)
        except requests.RequestException as exc:
            last_error = f"请求异常 page={page}: {exc}"
            logger.warning("第 %s 页请求异常：%s（第 %s/%s 次重试）", page, exc, attempt, MAX_RETRIES)
        except ValueError as exc:
            last_error = f"响应不是合法 JSON page={page}: {exc}"
            logger.error("第 %s 页响应解析失败：%s", page, exc)
            break  # 非 JSON 响应重试无意义，直接失败

        else:
            if body.get("code") != "0000":
                last_error = f"接口返回失败 code={body.get('code')} message={body.get('message')}"
                logger.error("接口返回失败：%s", last_error)
                break
            return body

        if attempt < MAX_RETRIES:
            time.sleep(PAGE_DELAY)

    raise RuntimeError(last_error or "未知请求错误")


def save_raw_page(batch_id: str, page: int, body: dict[str, Any]) -> Path:
    """保存单页原始响应 JSON，保留接口真实结构，便于复核与降级。"""
    raw_dir = RAW_DIR / batch_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"page_{page}.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_candidates_csv(batch_id: str, records: list[dict[str, Any]]) -> Path:
    """把全部候选记录写入标准化 CSV（UTF-8-SIG，便于 Excel 直接打开）。"""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / f"university_candidates_{batch_id}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field) for field in CSV_FIELDS})
    return path


def _build_summary(
    batch_id: str,
    total: int | None,
    records: list[dict[str, Any]],
    page_count: int,
    status: str,
    raw_output_path: str,
    parsed_output_path: str,
    error: str | None = None,
) -> dict[str, Any]:
    """构造爬虫运行摘要，字段对齐 crawler_runs 表，供 S04 直接登记。"""
    return {
        "crawler_name": "kaoyan_school_list",
        "target_url": TARGET_URL,
        "api_url": API_URL,
        "request_params": {"province_id": PROVINCE_ID, "limit": PAGE_SIZE},
        "batch_id": batch_id,
        "status": status,
        "total_count": total,
        "fetched_count": len(records),
        "page_count": page_count,
        "raw_output_path": raw_output_path,
        "parsed_output_path": parsed_output_path,
        "error_message": error,
    }


def run_crawler(province_id: int = PROVINCE_ID) -> dict[str, Any]:
    """运行爬虫主流程，返回采集摘要。

    province_id 默认 50（重庆），保留参数方便后续扩展到其他省份。
    """
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    set_trace_id(f"crawl-{batch_id}")

    logger.info("开始抓取重庆研招单位候选库，batch_id=%s", batch_id)
    logger.info("目标页面：%s", TARGET_URL)
    logger.info("接口地址：%s", API_URL)

    total: int | None = None
    collected: list[dict[str, Any]] = []
    page = 1

    while page <= MAX_PAGES:
        try:
            body = fetch_page(page, PAGE_SIZE)
        except RuntimeError as exc:
            logger.error("抓取中断：第 %s 页失败：%s", page, exc)
            raw_dir = str(RAW_DIR / batch_id)
            return _build_summary(
                batch_id, total, collected, page - 1, "failed",
                raw_output_path=raw_dir, parsed_output_path="", error=str(exc),
            )

        data = body.get("data") or {}
        records = data.get("data") or []
        page_total = _to_int(data.get("total"))
        if total is None:
            total = page_total
            logger.info("接口声明总数 total=%s", total)

        if records:
            raw_path = save_raw_page(batch_id, page, body)
            logger.info("第 %s 页抓取 %s 条，原始 JSON 已保存：%s", page, len(records), raw_path)
            collected.extend(records)
        else:
            logger.warning("第 %s 页返回空记录", page)

        if total and len(collected) >= total:
            break
        if not records:
            # 既没拿到数据又没到 total，继续翻页无意义，停止抓取
            logger.warning("第 %s 页无数据且未达到 total，停止抓取", page)
            break

        page += 1
        time.sleep(PAGE_DELAY)

    normalized = [normalize_record(item) for item in collected]
    csv_path = save_candidates_csv(batch_id, normalized) if normalized else PROCESSED_DIR

    if total and len(collected) >= total:
        status = "success"
    elif collected:
        status = "partial"
    else:
        status = "failed"

    summary = _build_summary(
        batch_id, total, normalized, page, status,
        raw_output_path=str(RAW_DIR / batch_id),
        parsed_output_path=str(csv_path),
    )
    logger.info(
        "抓取完成：状态=%s，共 %s 条（接口 total=%s），标准化 CSV：%s",
        status, len(collected), total, csv_path,
    )
    return summary


def main() -> None:
    """爬虫命令行入口。"""
    setup_logging()
    summary = run_crawler()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
