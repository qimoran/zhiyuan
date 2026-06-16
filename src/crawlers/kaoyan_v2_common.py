"""掌上考研 V2 爬虫公共工具。

本模块只放跨分块爬虫复用的能力：路径、请求、聚合 JSON 读写、去重和字段
清洗。各业务接口分别放在独立 crawler 文件中，避免一个文件过长又保持入口清晰。
"""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from src.common.config import PROJECT_ROOT
from src.common.logger import get_logger

logger = get_logger("crawler")

API_HOST = "https://api.kaoyan.cn"
PROVINCE_ID = 50
DEFAULT_YEARS = [2024, 2025, 2026]

REQUEST_TIMEOUT = 20
REQUEST_RETRIES = 3
PAGE_DELAY = 0.5
DETAIL_DELAY = 2.0
DETAIL_BACKOFF = 30.0
DETAIL_BACKOFF_ROUNDS = 1

RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "kaoyan_v2"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "kaoyan_v2_integrated"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://www.kaoyan.cn",
    "referer": "https://www.kaoyan.cn/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0"
    ),
}


@dataclass
class BlockStats:
    """单个分块爬虫的统计结果。"""

    count: int = 0
    success_count: int = 0
    error_count: int = 0
    duplicate_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "count": self.count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "duplicate_count": self.duplicate_count,
        }


class ApiError(RuntimeError):
    """掌上考研接口返回非成功业务码或请求失败。"""


class CrawlLockError(RuntimeError):
    """同一批次爬虫已经在运行。"""


def make_batch_id() -> str:
    """生成批次号。"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def raw_batch_dir(batch_id: str) -> Path:
    return RAW_ROOT / batch_id


def aggregate_path(batch_id: str, domain: str, filename: str) -> Path:
    return raw_batch_dir(batch_id) / domain / filename


@contextmanager
def acquire_batch_lock(batch_id: str):
    """同一批次只允许一个爬虫进程写聚合 JSON 和最终 CSV。"""
    batch_dir = raw_batch_dir(batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    lock_path = batch_dir / ".crawl.lock"
    lock_payload = {
        "batch_id": batch_id,
        "pid": os.getpid(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise CrawlLockError(
            f"批次 {batch_id} 已存在运行锁：{project_relative(lock_path)}；"
            "请先确认没有同批次爬虫在跑，再删除该锁文件后重试。"
        ) from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(lock_payload, file, ensure_ascii=False, indent=2)
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_json(path: Path, default: Any) -> Any:
    """读取 UTF-8 JSON；不存在时返回 default。"""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("聚合 JSON 读取异常，尝试恢复：%s，原因：%s", project_relative(path), exc)

    try:
        recovered_text = path.read_bytes().decode("utf-8", errors="ignore")
        recovered = json.loads(recovered_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        if path.name == "plan_detail_v2.json":
            recovered_plan_detail = recover_plan_detail_payload(path)
            if recovered_plan_detail:
                logger.warning("planDetailV2 聚合 JSON 已按完整 plan_id 条目恢复：%s", project_relative(path))
                return recovered_plan_detail
        logger.warning("聚合 JSON 恢复失败，将重新生成：%s，原因：%s", project_relative(path), exc)
        return default
    logger.warning("聚合 JSON 已通过忽略损坏字节恢复：%s", project_relative(path))
    return recovered


def save_json(path: Path, body: Any) -> None:
    """保存聚合 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def recover_plan_detail_payload(path: Path) -> dict[str, Any]:
    """从截断或粘连的 planDetailV2 聚合文件中提取完整详情条目。"""
    decoder = json.JSONDecoder()
    try:
        text = path.read_bytes().decode("utf-8", errors="ignore")
    except OSError:
        return {}

    marker_index = text.find('"items_by_plan_id"')
    if marker_index < 0:
        return {}
    position = text.find("{", marker_index)
    if position < 0:
        return {}
    position += 1

    items_by_plan_id: dict[str, dict[str, Any]] = {}
    while position < len(text):
        while position < len(text) and text[position] in " \r\n\t,":
            position += 1
        if position >= len(text) or text[position] == "}":
            break
        if text[position] != '"':
            break

        try:
            plan_id, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            break

        while position < len(text) and text[position].isspace():
            position += 1
        if position >= len(text) or text[position] != ":":
            break
        position += 1

        while position < len(text) and text[position].isspace():
            position += 1
        try:
            item, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            break

        if isinstance(item, dict):
            items_by_plan_id[str(plan_id)] = item

    if not items_by_plan_id:
        return {}

    errors = [
        {"plan_id": item.get("plan_id"), "error": item.get("error_message", "")}
        for item in items_by_plan_id.values()
        if item.get("source_status") == "error"
    ]
    stats = BlockStats(
        count=len(items_by_plan_id),
        success_count=sum(1 for item in items_by_plan_id.values() if item.get("source_status") == "success"),
        error_count=sum(1 for item in items_by_plan_id.values() if item.get("source_status") == "error"),
        duplicate_count=0,
    )
    return {
        "api": "/pc/school/planDetailV2",
        "items_by_plan_id": items_by_plan_id,
        "errors": errors,
        "stats": stats.to_dict(),
    }


def post_api(path: str, payload: dict[str, Any], *, retry_delay: float = PAGE_DELAY) -> dict[str, Any]:
    """请求普通掌上考研接口。

    成功返回完整 JSON。失败抛出 ApiError，由分块爬虫记录错误并继续。
    """
    url = f"{API_HOST}{path}"
    last_error = ""
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            response = requests.post(url, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            if body.get("code") == "0000":
                return body
            last_error = f"code={body.get('code')} message={body.get('message')}"

        if attempt < REQUEST_RETRIES:
            time.sleep(retry_delay)

    raise ApiError(f"{path} 请求失败：{last_error}")


def post_plan_detail_v2(plan_id: int, *, detail_delay: float = DETAIL_DELAY, backoff_rounds: int = DETAIL_BACKOFF_ROUNDS) -> dict[str, Any]:
    """请求 planDetailV2，并按接口限流规则处理。

    规则：每次真实详情请求前由调用方控制 2 秒间隔；如果接口返回 0010
    「请求频繁」，先每隔 2 秒快速重试 2 次；仍失败则等待 30 秒后再来一轮。
    超过配置轮数后抛出 ApiError，该条详情由上层记录为空。
    """
    path = "/pc/school/planDetailV2"
    url = f"{API_HOST}{path}"
    payload = {"plan_id": plan_id}
    last_error = ""

    for backoff_index in range(backoff_rounds + 1):
        for attempt in range(1, REQUEST_RETRIES + 1):
            try:
                response = requests.post(url, headers=HEADERS, json=payload, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                body = response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if body.get("code") == "0000":
                    return body
                last_error = f"code={body.get('code')} message={body.get('message')}"
                if body.get("code") == "0010" and attempt < REQUEST_RETRIES:
                    logger.warning("planDetailV2 plan_id=%s 请求频繁：%s，第 %s/2 次重试", plan_id, body.get("message"), attempt)

            if attempt < REQUEST_RETRIES:
                time.sleep(detail_delay)

        if backoff_index < backoff_rounds:
            logger.warning("planDetailV2 plan_id=%s 连续失败，等待 %.1f 秒后再试：%s", plan_id, DETAIL_BACKOFF, last_error)
            time.sleep(DETAIL_BACKOFF)

    raise ApiError(f"{path} plan_id={plan_id} 请求失败：{last_error}")


def sleep_between_detail_requests(last_request_at: float | None, detail_delay: float) -> float:
    """让 planDetailV2 真实请求保持全局间隔。"""
    now = time.monotonic()
    if last_request_at is not None:
        wait_seconds = detail_delay - (now - last_request_at)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
    return time.monotonic()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def clean_html(value: Any) -> str:
    """清理接口中的 br/html 片段，统一换行。"""
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def to_int(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def json_compact(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def degree_type_std(value: Any) -> str:
    code = to_int(value)
    if code == 1:
        return "professional"
    if code == 2:
        return "academic"
    text = clean_text(value)
    if "专" in text:
        return "professional"
    if "学" in text:
        return "academic"
    return ""


def study_mode_std(value: Any) -> str:
    text = clean_text(value)
    if "非全" in text:
        return "part_time"
    if "全日制" in text:
        return "full_time"
    return ""


def school_level(school: dict[str, Any]) -> str:
    levels: list[str] = []
    if to_int(school.get("is_985")) == 1:
        levels.append("985")
    if to_int(school.get("is_211")) == 1:
        levels.append("211")
    if to_int(school.get("syl")) == 1:
        levels.append("双一流")
    if to_int(school.get("is_zihuaxian")) == 1:
        levels.append("自划线")
    return " / ".join(levels) if levels else "普通院校"


def province_area(value: Any) -> str:
    text = clean_text(value)
    if text in {"A", "A区"}:
        return "A区"
    if text in {"B", "B区"}:
        return "B区"
    return text or "A区"


def project_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)
