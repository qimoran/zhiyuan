"""schoolLevelRate 分块爬虫：采集学科评估等级。"""

from __future__ import annotations

import time
from typing import Any

from src.crawlers.kaoyan_v2_common import BlockStats, PAGE_DELAY, aggregate_path, load_json, post_api, save_json


def fetch_level_rates(
    batch_id: str,
    schools: list[dict[str, Any]],
    *,
    resume: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    path = aggregate_path(batch_id, "level_rate", "level_rate.json")
    cached = load_json(path, {}) if resume else {}
    items: list[dict[str, Any]] = list(cached.get("items") or [])
    completed = set(cached.get("completed_school_ids") or [])
    errors: list[dict[str, Any]] = list(cached.get("errors") or [])
    stats = BlockStats()

    seen = {(row.get("school_id"), row.get("code"), row.get("degree_type"), row.get("rate")) for row in items}
    for school in schools:
        school_id = school.get("school_id")
        if school_id in completed:
            continue
        try:
            body = post_api("/pc/school/schoolLevelRate", {"school_id": school_id})
            data = body.get("data") or {}
            rows = data.get("data") or []
            for row in rows:
                enriched = dict(row)
                enriched["school_id"] = school_id
                enriched["school_name"] = school.get("school_name")
                key = (school_id, enriched.get("code"), enriched.get("degree_type"), enriched.get("rate"))
                if key in seen:
                    stats.duplicate_count += 1
                    continue
                seen.add(key)
                items.append(enriched)
            completed.add(school_id)
        except Exception as exc:
            stats.error_count += 1
            errors.append({"school_id": school_id, "error": str(exc)})
        save_json(path, _payload(items, completed, errors, stats))
        time.sleep(PAGE_DELAY)

    stats.count = len(items)
    stats.success_count = len(items)
    stats.error_count = len(errors)
    payload = _payload(items, completed, errors, stats)
    save_json(path, payload)
    return items, payload["stats"]


def _payload(items: list[dict[str, Any]], completed: set[Any], errors: list[dict[str, Any]], stats: BlockStats) -> dict[str, Any]:
    return {
        "api": "/pc/school/schoolLevelRate",
        "items": items,
        "completed_school_ids": sorted(completed),
        "errors": errors,
        "stats": stats.to_dict(),
    }
