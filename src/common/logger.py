from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Any

from src.common.trace import get_trace_id

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "logging.yaml"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"


class TraceIdFilter(logging.Filter):
    """为每条日志补充 trace_id 字段。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


def setup_logging(config_path: str | Path | None = None) -> None:
    """初始化日志配置。

    优先读取 config/logging.yaml；如果 PyYAML 未安装或配置读取失败，
    则使用标准库默认配置，保证项目早期也能正常产生日志。
    """
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if path.exists():
        try:
            import yaml  # type: ignore

            with path.open("r", encoding="utf-8") as file:
                config: dict[str, Any] = yaml.safe_load(file)
            _ensure_handler_dirs(config)
            logging.config.dictConfig(config)
            return
        except Exception:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            )
            logging.getLogger(__name__).exception("日志配置文件加载失败，已使用默认日志配置")
            return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def get_logger(name: str = "app") -> logging.Logger:
    """获取项目 Logger。"""
    return logging.getLogger(name)


def _ensure_handler_dirs(config: dict[str, Any]) -> None:
    handlers = config.get("handlers", {})
    for handler_config in handlers.values():
        filename = handler_config.get("filename")
        if not filename:
            continue
        log_path = Path(filename)
        if not log_path.is_absolute():
            log_path = PROJECT_ROOT / log_path
            handler_config["filename"] = str(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
