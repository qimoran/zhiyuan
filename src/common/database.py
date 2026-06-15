from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from src.common.config import DatabaseConfig, get_database_config


def get_connection(config: DatabaseConfig | None = None):
    """创建 MySQL 连接。

    调用方负责关闭连接；业务代码优先使用 `mysql_connection()` 上下文管理器。
    """
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:
        raise RuntimeError("缺少 PyMySQL 依赖，请先安装 requirements.txt。") from exc

    db_config = config or get_database_config()
    return pymysql.connect(
        host=db_config.host,
        port=db_config.port,
        user=db_config.user,
        password=db_config.password,
        database=db_config.database,
        charset=db_config.charset,
        cursorclass=DictCursor,
        autocommit=False,
    )


@contextmanager
def mysql_connection(config: DatabaseConfig | None = None) -> Iterator[Any]:
    """MySQL 连接上下文，自动关闭连接。"""
    connection = get_connection(config)
    try:
        yield connection
    finally:
        connection.close()


def ping_database() -> bool:
    """检查项目数据库是否可连接。"""
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS ok")
            row = cursor.fetchone()
    return bool(row and row.get("ok") == 1)


def fetch_one(sql: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> dict[str, Any] | None:
    """查询单行数据。"""
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()


def fetch_all(sql: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """查询多行数据。"""
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())


def execute(sql: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> int:
    """执行写入、更新或删除语句，返回影响行数。"""
    with mysql_connection() as connection:
        try:
            with connection.cursor() as cursor:
                affected_rows = cursor.execute(sql, params)
            connection.commit()
            return affected_rows
        except Exception:
            connection.rollback()
            raise
