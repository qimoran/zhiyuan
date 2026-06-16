"""schoolList 分块爬虫：采集重庆研招单位花名册。"""

from __future__ import annotations

import time
from typing import Any

from src.crawlers.kaoyan_v2_common import (
    BlockStats,
    PAGE_DELAY,
    PROVINCE_ID,
    aggregate_path,
    load_json,
    post_api,
    save_json,
)


def fetch_school_list(batch_id: str, *, resume: bool = True) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """抓取 schoolList，并聚合保存为一个 JSON 文件。"""
    path = aggregate_path(batch_id, "school_list", "school_list.json")
    cached = load_json(path, {}) if resume else {}
    if cached.get("items"):
        return list(cached["items"]), dict(cached.get("stats") or {})

    stats = BlockStats()
    schools: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    page = 1
    total: int | None = None

    while True:
        body = post_api("/pc/school/schoolList", {"province_id": PROVINCE_ID, "page": page, "limit": 20})
        data = body.get("data") or {}
        rows = data.get("data") or []
        if total is None:
            total = data.get("total")

        for row in rows:
            school_id = row.get("school_id")
            if school_id in seen_ids:
                stats.duplicate_count += 1
                continue
            seen_ids.add(school_id)
            schools.append(row)

        if not rows or (total and len(schools) >= int(total)):
            break
        page += 1
        time.sleep(PAGE_DELAY)

    stats.count = len(schools)
    stats.success_count = len(schools)
    payload = {
        "api": "/pc/school/schoolList",
        "request": {"province_id": PROVINCE_ID},
        "items": schools,
        "stats": stats.to_dict(),
    }
    save_json(path, payload)
    return schools, stats.to_dict()

