from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_APP_CONFIG_PATH = PROJECT_ROOT / "config" / "app.yaml"
DEFAULT_DATABASE_CONFIG_PATH = PROJECT_ROOT / "config" / "database.yaml"
DEFAULT_RECOMMEND_RULES_PATH = PROJECT_ROOT / "config" / "recommend_rules.yaml"


@dataclass(frozen=True)
class DatabaseConfig:
    """数据库连接配置。"""

    host: str
    port: int
    database: str
    user: str
    password: str
    charset: str = "utf8mb4"


@dataclass(frozen=True)
class AppConfig:
    """后端应用基础配置。"""

    name: str
    host: str
    port: int
    debug: bool


def load_dotenv(path: str | Path = DEFAULT_ENV_PATH, override: bool = False) -> dict[str, str]:
    """读取 .env 文件到当前进程环境变量。

    不依赖 python-dotenv，避免基础阶段因为依赖缺失导致项目无法启动。
    """
    env_path = Path(path)
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())
        values[key] = value

        if override or key not in os.environ:
            os.environ[key] = value

    return values


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """读取 YAML 配置文件。

    如果 PyYAML 暂未安装，则返回空字典，让调用方继续使用环境变量默认值。
    """
    config_path = Path(path)
    if not config_path.exists():
        return {}

    try:
        import yaml  # type: ignore
    except ImportError:
        return {}

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return data if isinstance(data, dict) else {}


def get_env(name: str, default: str = "") -> str:
    """获取字符串环境变量。"""
    load_dotenv()
    return os.getenv(name, default)


def get_int_env(name: str, default: int) -> int:
    """获取整数环境变量。"""
    raw_value = get_env(name, str(default))
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def get_bool_env(name: str, default: bool = False) -> bool:
    """获取布尔环境变量。"""
    raw_value = get_env(name, str(default)).strip().lower()
    return raw_value in {"1", "true", "yes", "on", "y"}


def get_app_config() -> AppConfig:
    """获取 Flask 应用基础配置。"""
    load_dotenv()
    yaml_config = load_yaml_config(DEFAULT_APP_CONFIG_PATH).get("app", {})

    return AppConfig(
        name=str(get_env("APP_NAME", str(yaml_config.get("name") or "kaoyan_recommendation"))),
        host=str(get_env("APP_HOST", str(yaml_config.get("host") or "0.0.0.0"))),
        port=get_int_env("APP_PORT", int(yaml_config.get("port") or 5000)),
        debug=get_bool_env("APP_DEBUG", bool(yaml_config.get("debug", False))),
    )


def get_database_config() -> DatabaseConfig:
    """获取项目 MySQL 数据库配置。"""
    load_dotenv()
    yaml_config = load_yaml_config(DEFAULT_DATABASE_CONFIG_PATH).get("mysql", {})

    return DatabaseConfig(
        host=get_env("MYSQL_HOST", str(yaml_config.get("host") or "mysql")),
        port=get_int_env("MYSQL_PORT", int(yaml_config.get("port") or 3306)),
        database=get_env("ZHIYUAN_DB_NAME", str(yaml_config.get("database") or "zhiyuan")),
        user=get_env("ZHIYUAN_DB_USER", str(yaml_config.get("user") or "zhiyuan_app")),
        password=get_env("ZHIYUAN_DB_PASSWORD", str(yaml_config.get("password") or "")),
        charset=get_env("MYSQL_CHARSET", str(yaml_config.get("charset") or "utf8mb4")),
    )


def get_recommend_rules() -> dict[str, Any]:
    """获取推荐规则配置。"""
    return load_yaml_config(DEFAULT_RECOMMEND_RULES_PATH)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
