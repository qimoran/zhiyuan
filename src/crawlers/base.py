"""掌上考研爬虫公共能力：HTTP 请求、分页、原始 JSON 落盘、学校清单读取。

供 S03b 三个扩展爬虫（planList、schoolScore、schoolLevelRate）复用，
统一请求头、超时、重试、翻页间隔，避免对接口造成压力。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from src.common.config import PROJECT_ROOT
from src.common.logger import get_logger

logger = get_logger("crawler")

API_HOST = "https://api.kaoyan.cn"
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

REQUEST_TIMEOUT = 20
MAX_RETRIES = 2
PAGE_DELAY = 0.5  # 翻页/逐条请求间隔，秒

DATA_ROOT = PROJECT_ROOT / "data"
RAW_BASE_DIR = DATA_ROOT / "raw"
PROCESSED_BASE_DIR = DATA_ROOT / "processed"


def _to_int(value: Any) -> int | None:
    """安全转换为整数；空值或非数字返回 None。"""
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def post_api(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST 请求掌上考研接口，返回完整响应体字典。

    接口失败、超时或返回非成功 code 时抛出 RuntimeError，由调用方记录。
    """
    url = f"{API_HOST}{path}"
    body_text = json.dumps(payload)
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                url,
                headers=DEFAULT_HEADERS,
                data=body_text,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            body = response.json()
        except requests.Timeout:
            last_error = f"请求超时 {path}"
            logger.warning("%s 请求超时，第 %s/%s 次重试", path, attempt, MAX_RETRIES)
        except requests.RequestException as exc:
            last_error = f"请求异常 {path}: {exc}"
            logger.warning("%s 请求异常：%s（第 %s/%s 次重试）", path, exc, attempt, MAX_RETRIES)
        except ValueError as exc:
            last_error = f"响应非 JSON {path}: {exc}"
            logger.error("%s 响应解析失败：%s", path, exc)
            break

        else:
            if body.get("code") != "0000":
                last_error = f"接口失败 code={body.get('code')} message={body.get('message')}"
                logger.error("%s %s", path, last_error)
                break
            return body

        if attempt < MAX_RETRIES:
            time.sleep(PAGE_DELAY)

    raise RuntimeError(last_error or "未知请求错误")


def save_raw_json(base_dir: Path, filename: str, body: dict[str, Any]) -> Path:
    """保存原始响应 JSON，保留接口真实结构，便于复核与降级。"""
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / filename
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def sleep_briefly() -> None:
    """请求间短暂休眠，避免对接口造成压力。"""
    time.sleep(PAGE_DELAY)


def major_category_code(code: str | None) -> str | None:
    """取专业代码前 2 位，用于推导学科门类。"""
    if not code or len(str(code)) < 2:
        return None
    return str(code)[:2]
