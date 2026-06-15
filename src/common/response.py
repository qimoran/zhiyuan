from __future__ import annotations

from typing import Any

from src.common.trace import get_trace_id


def build_response(code: int, message: str, data: Any = None, trace_id: str | None = None) -> dict[str, Any]:
    """构造统一响应字典。"""
    return {
        "code": code,
        "message": message,
        "data": data,
        "trace_id": trace_id or get_trace_id(),
    }


def success_response(data: Any = None, message: str = "success") -> dict[str, Any]:
    """构造成功响应。"""
    return build_response(code=0, message=message, data=data)


def error_response(code: int, message: str, data: Any = None) -> dict[str, Any]:
    """构造失败响应。"""
    return build_response(code=code, message=message, data=data)
