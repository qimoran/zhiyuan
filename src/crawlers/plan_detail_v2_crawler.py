"""planDetailV2 分块爬虫：按 plan_id 采集专业详情。"""

from __future__ import annotations

from typing import Any

from src.crawlers.kaoyan_v2_common import (
    DETAIL_BACKOFF_ROUNDS,
    DETAIL_DELAY,
    BlockStats,
    aggregate_path,
    logger,
    load_json,
    post_plan_detail_v2,
    save_json,
    sleep_between_detail_requests,
)


def fetch_plan_detail_v2(
    batch_id: str,
    plans: list[dict[str, Any]],
    *,
    detail_delay: float = DETAIL_DELAY,
    backoff_rounds: int = DETAIL_BACKOFF_ROUNDS,
    resume: bool = True,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """抓取 planDetailV2，按 plan_id 去重并保存到一个聚合 JSON。"""
    path = aggregate_path(batch_id, "plan_detail_v2", "plan_detail_v2.json")
    cached = load_json(path, {}) if resume else {}
    items_by_plan_id: dict[str, dict[str, Any]] = dict(cached.get("items_by_plan_id") or {})
    errors: list[dict[str, Any]] = list(cached.get("errors") or [])
    stats = BlockStats()

    unique_plan_ids: list[int] = []
    seen: set[int] = set()
    for plan in plans:
        plan_id = plan.get("plan_id")
        if plan_id is None or plan_id in seen:
            stats.duplicate_count += 1
            continue
        seen.add(plan_id)
        unique_plan_ids.append(int(plan_id))

    last_request_at: float | None = None
    total = len(unique_plan_ids)
    _log_current_cache(total, items_by_plan_id)
    for index, plan_id in enumerate(unique_plan_ids, start=1):
        key = str(plan_id)
        existing = items_by_plan_id.get(key)
        if existing and existing.get("source_status") == "success":
            _log_progress(index, total, items_by_plan_id, skipped=True)
            continue

        try:
            last_request_at = sleep_between_detail_requests(last_request_at, detail_delay)
            body = post_plan_detail_v2(plan_id, detail_delay=detail_delay, backoff_rounds=backoff_rounds)
        except Exception as exc:
            stats.error_count += 1
            error = {"plan_id": plan_id, "error": str(exc)}
            errors.append(error)
            items_by_plan_id[key] = {"plan_id": plan_id, "source_status": "error", "error_message": str(exc), "data": {}}
        else:
            items_by_plan_id[key] = {
                "plan_id": plan_id,
                "source_status": "success",
                "error_message": "",
                "data": body.get("data") or {},
            }

        _refresh_stats(stats, items_by_plan_id)
        save_json(path, _payload(items_by_plan_id, errors, stats))
        _log_progress(index, total, items_by_plan_id, failed=items_by_plan_id[key].get("source_status") == "error")

    _refresh_stats(stats, items_by_plan_id)
    payload = _payload(items_by_plan_id, errors, stats)
    save_json(path, payload)
    return items_by_plan_id, payload["stats"]


def _log_progress(index: int, total: int, items_by_plan_id: dict[str, dict[str, Any]], *, skipped: bool = False, failed: bool = False) -> None:
    """输出详情爬取进度，方便从 logs 目录直接看还剩多少。"""
    if not failed and index % 10 != 0 and index != total:
        return
    success_count = sum(1 for item in items_by_plan_id.values() if item.get("source_status") == "success")
    error_count = sum(1 for item in items_by_plan_id.values() if item.get("source_status") == "error")
    done_count = success_count + error_count
    logger_suffix = "，本条复用缓存" if skipped else ("，本条失败" if failed else "")

    logger.info(
        "planDetailV2 进度 %s/%s，已处理 %s，成功 %s，失败 %s，剩余待成功 %s%s",
        index,
        total,
        done_count,
        success_count,
        error_count,
        max(total - success_count, 0),
        logger_suffix,
    )


def _log_current_cache(total: int, items_by_plan_id: dict[str, dict[str, Any]]) -> None:
    """恢复运行时先输出一次缓存进度。"""
    success_count = sum(1 for item in items_by_plan_id.values() if item.get("source_status") == "success")
    error_count = sum(1 for item in items_by_plan_id.values() if item.get("source_status") == "error")
    logger.info(
        "planDetailV2 当前缓存进度：总计划 %s，已缓存 %s，成功 %s，失败待重试 %s，剩余待成功 %s",
        total,
        len(items_by_plan_id),
        success_count,
        error_count,
        max(total - success_count, 0),
    )


def _refresh_stats(stats: BlockStats, items_by_plan_id: dict[str, dict[str, Any]]) -> None:
    stats.count = len(items_by_plan_id)
    stats.success_count = sum(1 for item in items_by_plan_id.values() if item.get("source_status") == "success")
    stats.error_count = sum(1 for item in items_by_plan_id.values() if item.get("source_status") == "error")


def _payload(items_by_plan_id: dict[str, dict[str, Any]], errors: list[dict[str, Any]], stats: BlockStats) -> dict[str, Any]:
    return {
        "api": "/pc/school/planDetailV2",
        "items_by_plan_id": items_by_plan_id,
        "errors": errors,
        "stats": stats.to_dict(),
    }
