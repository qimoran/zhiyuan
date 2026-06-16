"""schoolScore 分块爬虫：采集近三年分数线。"""

from __future__ import annotations

import time
from typing import Any

from src.crawlers.kaoyan_v2_common import BlockStats, PAGE_DELAY, aggregate_path, load_json, post_api, save_json


def fetch_score_lines(
    batch_id: str,
    schools: list[dict[str, Any]],
    years: list[int],
    *,
    resume: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    path = aggregate_path(batch_id, "score_line", "score_line.json")
    cached = load_json(path, {}) if resume else {}
    items: list[dict[str, Any]] = list(cached.get("items") or [])
    completed = {tuple(x) for x in cached.get("completed_school_years") or []}
    errors: list[dict[str, Any]] = list(cached.get("errors") or [])
    stats = BlockStats()

    seen = {
        (
            row.get("school_id"),
            row.get("year"),
            row.get("data_type"),
            row.get("depart_id"),
            row.get("code"),
            row.get("name"),
            row.get("degree_type"),
        )
        for row in items
    }

    for school in schools:
        school_id = school.get("school_id")
        for year in years:
            if (school_id, year) in completed:
                continue
            try:
                body = post_api("/pc/school/schoolScore", {"school_id": school_id, "year": year})
                rows = body.get("data") or []
                for row in rows:
                    enriched = dict(row)
                    enriched["school_id"] = school_id
                    enriched["school_name"] = school.get("school_name")
                    enriched["year"] = row.get("year") or year
                    key = (
                        enriched.get("school_id"),
                        enriched.get("year"),
                        enriched.get("data_type"),
                        enriched.get("depart_id"),
                        enriched.get("code"),
                        enriched.get("name"),
                        enriched.get("degree_type"),
                    )
                    if key in seen:
                        stats.duplicate_count += 1
                        continue
                    seen.add(key)
                    items.append(enriched)
                completed.add((school_id, year))
            except Exception as exc:
                stats.error_count += 1
                errors.append({"school_id": school_id, "year": year, "error": str(exc)})
            save_json(path, _payload(items, completed, errors, stats))
            time.sleep(PAGE_DELAY)

    stats.count = len(items)
    stats.success_count = len(items)
    stats.error_count = len(errors)
    payload = _payload(items, completed, errors, stats)
    save_json(path, payload)
    return items, payload["stats"]


def _payload(items: list[dict[str, Any]], completed: set[tuple[Any, Any]], errors: list[dict[str, Any]], stats: BlockStats) -> dict[str, Any]:
    return {
        "api": "/pc/school/schoolScore",
        "items": items,
        "completed_school_years": [list(item) for item in sorted(completed)],
        "errors": errors,
        "stats": stats.to_dict(),
    }
