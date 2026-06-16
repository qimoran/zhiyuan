"""S08 基础 API 路由。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.common.database import ping_database
from src.common.logger import get_logger
from src.common.response import success_response
from src.services.query_service import (
    get_health_detail,
    list_majors,
    list_sources,
    list_universities,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")
logger = get_logger("app")


@api_bp.get("/health")
def health_check():
    """系统健康检查接口。"""
    database_ok = False
    detail = {}
    try:
        database_ok = ping_database()
        detail = get_health_detail() if database_ok else {}
    except Exception as exc:
        logger.warning("数据库健康检查失败：%s", exc)

    return jsonify(
        success_response(
            {
                "status": "ok",
                "database": "ok" if database_ok else "unavailable",
                "detail": detail,
            }
        )
    )


@api_bp.get("/university/list")
def university_list():
    """招生单位列表。"""
    data = list_universities(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/major/list")
def major_list():
    """专业列表。"""
    data = list_majors(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/source/list")
def source_list():
    """来源资料列表。"""
    data = list_sources(request.args.to_dict())
    return jsonify(success_response(data))
