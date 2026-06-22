"""前台用户认证与个人推荐历史服务。"""

from __future__ import annotations

import json
import re
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from src.common.config import get_recommend_rules
from src.common.database import fetch_all, fetch_one, mysql_connection
from src.common.exceptions import ValidationError

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_HISTORY_LIMIT = 50


def public_user(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    email = row.get("email") or row.get("username")
    return {
        "id": int(row["id"]),
        "email": email,
        "nickname": row["nickname"],
        "created_at": row.get("created_at").isoformat(sep=" ", timespec="seconds")
        if hasattr(row.get("created_at"), "isoformat")
        else row.get("created_at"),
    }


def get_user_by_id(user_id: int | None) -> dict[str, Any] | None:
    if not user_id:
        return None
    return fetch_one(
        """
        SELECT id, email, username, nickname, created_at
        FROM users
        WHERE id = %(id)s
        """,
        {"id": user_id},
    )


def register_user(payload: dict[str, Any]) -> dict[str, Any]:
    email = normalize_email(payload.get("email"))
    password = clean_text(payload.get("password"))
    nickname = clean_text(payload.get("nickname")) or email.split("@", 1)[0]
    validate_password(password)
    validate_nickname(nickname)

    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE email = %(email)s OR username = %(email)s",
                {"email": email},
            )
            if cursor.fetchone():
                raise ValidationError("邮箱已注册，请直接登录")
            cursor.execute(
                """
                INSERT INTO users (email, username, nickname, password_hash)
                VALUES (%(email)s, %(email)s, %(nickname)s, %(password_hash)s)
                """,
                {
                    "email": email,
                    "nickname": nickname,
                    "password_hash": generate_password_hash(password),
                },
            )
            user_id = int(cursor.lastrowid)
        connection.commit()
    return public_user(get_user_by_id(user_id)) or {}


def authenticate_user(payload: dict[str, Any]) -> dict[str, Any]:
    email = normalize_email(payload.get("email"))
    password = clean_text(payload.get("password"))
    if not password:
        raise ValidationError("密码不能为空")
    row = fetch_one(
        """
        SELECT id, email, username, nickname, password_hash, created_at
        FROM users
        WHERE email = %(email)s OR username = %(email)s
        """,
        {"email": email},
    )
    if not row or not check_password_hash(row["password_hash"], password):
        raise ValidationError("邮箱或密码错误")
    return public_user(row) or {}


def update_user_profile(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    nickname = clean_text(payload.get("nickname"))
    current_password = clean_text(payload.get("current_password"))
    new_password = clean_text(payload.get("new_password"))
    updates: list[str] = []
    params: dict[str, Any] = {"user_id": user_id}

    if nickname is not None:
        validate_nickname(nickname)
        updates.append("nickname = %(nickname)s")
        params["nickname"] = nickname

    if new_password:
        validate_password(new_password)
        if not current_password:
            raise ValidationError("修改密码需要填写当前密码")
        row = fetch_one("SELECT password_hash FROM users WHERE id = %(user_id)s", {"user_id": user_id})
        if not row or not check_password_hash(row["password_hash"], current_password):
            raise ValidationError("当前密码不正确")
        updates.append("password_hash = %(password_hash)s")
        params["password_hash"] = generate_password_hash(new_password)

    if not updates:
        raise ValidationError("没有需要更新的信息")

    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE users
                SET {", ".join(updates)}
                WHERE id = %(user_id)s
                """,
                params,
            )
        connection.commit()
    return public_user(get_user_by_id(user_id)) or {}


def list_user_recommendation_history(user_id: int, limit: int = MAX_HISTORY_LIMIT) -> dict[str, Any]:
    limit = max(1, min(int(limit or MAX_HISTORY_LIMIT), MAX_HISTORY_LIMIT))
    rows = fetch_all(
        f"""
        SELECT id, trace_id, request_json, result_summary_json, warning_json, created_at
        FROM recommendation_logs
        WHERE user_id = %(user_id)s
        ORDER BY created_at DESC, id DESC
        LIMIT {limit}
        """,
        {"user_id": user_id},
    )
    items = [history_item(row) for row in rows]
    return {"items": items, "total": len(items), "limit": limit}


def get_user_recommendation_detail(user_id: int, log_id: int) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT id, trace_id, request_json, result_summary_json, warning_json, created_at
        FROM recommendation_logs
        WHERE id = %(log_id)s
          AND user_id = %(user_id)s
        """,
        {"log_id": log_id, "user_id": user_id},
    )
    if not row:
        raise ValidationError("未找到该推荐记录")
    item = history_item(row)
    result = normalize_recommendation_result_by_score_diff(parse_json(row.get("result_summary_json"), {}))
    return {
        **item,
        "request": parse_json(row.get("request_json"), {}),
        "result": result,
        "warnings": parse_json(row.get("warning_json"), []),
    }


def history_item(row: dict[str, Any]) -> dict[str, Any]:
    request_payload = parse_json(row.get("request_json"), {})
    result_payload = normalize_recommendation_result_by_score_diff(parse_json(row.get("result_summary_json"), {}))
    summary = result_payload.get("summary") if isinstance(result_payload, dict) else {}
    if not isinstance(summary, dict):
        summary = result_payload if isinstance(result_payload, dict) else {}
    created_at = row.get("created_at")
    return {
        "id": int(row["id"]),
        "trace_id": row["trace_id"],
        "created_at": created_at.isoformat(sep=" ", timespec="seconds")
        if hasattr(created_at, "isoformat")
        else created_at,
        "target_year": request_payload.get("target_year"),
        "major_name": request_payload.get("major_name") or request_payload.get("major_category") or "未填写",
        "total_score": request_payload.get("total_score"),
        "returned_count": summary.get("returned_count", 0),
        "rush": summary.get("rush", 0),
        "stable": summary.get("stable", 0),
        "safe": summary.get("safe", 0),
    }


def normalize_recommendation_result_by_score_diff(result: dict[str, Any]) -> dict[str, Any]:
    """读取历史记录时按当前分差规则重新归档，避免旧日志展示错档。"""
    if not isinstance(result, dict):
        return {}
    recommendations = result.get("recommendations")
    if not isinstance(recommendations, dict):
        return result

    normalized = {rank_type: [] for rank_type in ("rush", "stable", "safe")}
    for items in recommendations.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            rank_type = classify_history_rank_type(item.get("score_diff"))
            copied = dict(item)
            copied["rank_type"] = rank_type
            copied["reason"] = rewrite_history_rank_reason(copied.get("reason"), rank_type)
            normalized[rank_type].append(copied)

    for rank_type in normalized:
        normalized[rank_type] = sorted(
            normalized[rank_type],
            key=lambda item: history_score_diff_sort_key(item, rank_type),
        )

    copied_result = dict(result)
    copied_result["recommendations"] = normalized
    summary = dict(copied_result.get("summary") or {})
    summary["rush"] = len(normalized["rush"])
    summary["stable"] = len(normalized["stable"])
    summary["safe"] = len(normalized["safe"])
    summary["returned_count"] = sum(len(items) for items in normalized.values())
    copied_result["summary"] = summary
    copied_result["returned_count"] = summary["returned_count"]
    return copied_result


def classify_history_rank_type(score_diff: Any) -> str:
    thresholds = get_recommend_rules().get("score_thresholds", {})
    stable_min = int(thresholds.get("stable_avg_score_diff_min") or 10)
    safe_min = int(thresholds.get("safe_min_score_diff_min") or 25)
    try:
        diff = float(score_diff)
    except (TypeError, ValueError):
        diff = 0.0
    if diff >= safe_min:
        return "safe"
    if diff >= stable_min:
        return "stable"
    return "rush"


def history_score_diff_sort_key(item: dict[str, Any], rank_type: str) -> tuple[float, int, str]:
    try:
        diff = float(item.get("score_diff") or 0)
    except (TypeError, ValueError):
        diff = 0.0
    plan_count = parse_history_plan_count(item.get("plan_count"))
    school_name = str(item.get("university_name") or "")
    if rank_type == "rush":
        return (diff, -plan_count, school_name)
    return (-diff, -plan_count, school_name)


def parse_history_plan_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def rewrite_history_rank_reason(reason: Any, rank_type: str) -> str:
    text = str(reason or "")
    if not text:
        return text
    label = {"rush": "冲刺", "stable": "稳妥", "safe": "保底"}[rank_type]
    return re.sub(r"可作为(冲刺|稳妥|保底)目标", f"可作为{label}目标", text)


def build_recommendation_log_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": {
            "candidate_count": result["candidate_count"],
            "returned_count": result["returned_count"],
            "rush": len(result["recommendations"]["rush"]),
            "stable": len(result["recommendations"]["stable"]),
            "safe": len(result["recommendations"]["safe"]),
        },
        "score_evaluation": result.get("score_evaluation") or {},
        "recommendations": result.get("recommendations") or {},
        "recommendation_agent": result.get("recommendation_agent") or {},
    }


def normalize_email(value: Any) -> str:
    email = (clean_text(value) or "").lower()
    if len(email) > 120 or not EMAIL_PATTERN.match(email):
        raise ValidationError("请输入有效的邮箱地址")
    return email


def validate_password(password: str | None) -> None:
    if not password or len(password) < 6 or len(password) > 64:
        raise ValidationError("密码长度需为 6-64 位")


def validate_nickname(nickname: str) -> None:
    if len(nickname) < 1 or len(nickname) > 30:
        raise ValidationError("昵称长度需为 1-30 位")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default
