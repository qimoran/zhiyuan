from __future__ import annotations

import contextvars
from datetime import datetime
from uuid import uuid4

_trace_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id",
    default="",
)


def new_trace_id() -> str:
    """生成一次请求或一次任务使用的 trace_id。"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    random_suffix = uuid4().hex[:8]
    return f"{timestamp}{random_suffix}"


def set_trace_id(trace_id: str | None = None) -> str:
    """设置当前上下文 trace_id，并返回最终使用的值。"""
    current_trace_id = trace_id or new_trace_id()
    _trace_id_context.set(current_trace_id)
    return current_trace_id


def get_trace_id() -> str:
    """获取当前上下文 trace_id；没有时返回短横线，避免日志字段为空。"""
    return _trace_id_context.get() or "-"


def clear_trace_id() -> None:
    """清空当前上下文 trace_id。"""
    _trace_id_context.set("")
