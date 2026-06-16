"""planListV2 分块爬虫：按学校和年份采集专业级招生计划。"""

from __future__ import annotations

import time
from typing import Any

from src.crawlers.kaoyan_v2_common import BlockStats, PAGE_DELAY, aggregate_path, load_json, post_api, save_json


def fetch_plan_list_v2(
    batch_id: str,
    schools: list[dict[str, Any]],
    years: list[int],
    *,
    resume: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """抓取 planListV2。

    V2 列表是专业级，详情中的 research_area_data 再展开为研究方向级明细。
    """
    path = aggregate_path(batch_id, "plan_list_v2", "plan_list_v2.json")
    cached = load_json(path, {}) if resume else {}
    items: list[dict[str, Any]] = list(cached.get("items") or [])
    completed = {tuple(x) for x in cached.get("completed_school_years") or []}

    stats = BlockStats()
    seen_keys = {(row.get("school_id"), row.get("year"), row.get("plan_id")) for row in items}
    errors: list[dict[str, Any]] = list(cached.get("errors") or [])

    for school in schools:
        school_id = school.get("school_id")
        for year in years:
            if (school_id, year) in completed:
                continue
            page = 1
            total: int | None = None
            fetched = 0
            try:
                while True:
                    body = post_api(
                        "/pc/school/planListV2",
                        {"school_id": school_id, "year": year, "page": page, "limit": 50},
                    )
                    data = body.get("data") or {}
                    rows = data.get("data") or []
                    if total is None:
                        total = data.get("total")

                    for row in rows:
                        key = (school_id, row.get("year"), row.get("plan_id"))
                        if key in seen_keys:
                            stats.duplicate_count += 1
                            continue
                        seen_keys.add(key)
                        enriched = dict(row)
                        enriched["school_id"] = school_id
                        enriched["school_name"] = school.get("school_name")
                        items.append(enriched)
                        fetched += 1

                    if not rows or (total and fetched >= int(total)):
                        break
                    page += 1
                    time.sleep(PAGE_DELAY)
                completed.add((school_id, year))
            except Exception as exc:  # 记录单校单年错误，主流程继续
                stats.error_count += 1
                errors.append({"school_id": school_id, "year": year, "error": str(exc)})

            save_json(path, _payload(items, completed, errors, stats))

    stats.count = len(items)
    stats.success_count = len(items)
    stats.error_count = len(errors)
    payload = _payload(items, completed, errors, stats)
    save_json(path, payload)
    return items, payload["stats"]


def _payload(items: list[dict[str, Any]], completed: set[tuple[Any, Any]], errors: list[dict[str, Any]], stats: BlockStats) -> dict[str, Any]:
    return {
        "api": "/pc/school/planListV2",
        "items": items,
        "completed_school_years": [list(item) for item in sorted(completed)],
        "errors": errors,
        "stats": stats.to_dict(),
    }
