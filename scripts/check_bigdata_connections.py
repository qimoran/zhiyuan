from __future__ import annotations

import argparse
import os
import socket
import sys
from contextlib import closing

import pymysql
import redis
import requests


def ok(name: str, detail: str) -> bool:
    print(f"[OK]   {name}: {detail}")
    return True


def fail(name: str, detail: str) -> bool:
    print(f"[FAIL] {name}: {detail}")
    return False


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


def check_tcp(name: str, host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with closing(socket.create_connection((host, port), timeout=timeout)):
            return ok(name, f"{host}:{port} reachable")
    except OSError as exc:
        return fail(name, f"{host}:{port} unreachable ({exc})")


def check_mysql_databases(host: str, port: int, user: str, password: str, required_db: str) -> bool:
    name = "MySQL databases"
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW DATABASES")
                databases = [row[0] for row in cursor.fetchall()]
            if required_db not in databases:
                return fail(name, f"missing database={required_db}; existing={','.join(databases)}")
            return ok(name, "databases=" + ",".join(databases))
        finally:
            conn.close()
    except Exception as exc:
        return fail(name, str(exc))


def check_mysql_app_user(host: str, port: int, user: str, password: str, database: str) -> bool:
    name = "MySQL app user"
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DATABASE()")
                current_db = cursor.fetchone()[0]
            return ok(name, f"user={user}, database={current_db}")
        finally:
            conn.close()
    except Exception as exc:
        return fail(name, str(exc))


def check_redis(host: str, port: int) -> bool:
    name = "Redis"
    try:
        client = redis.Redis(host=host, port=port, socket_connect_timeout=5, protocol=2)
        response = client.ping()
        return ok(name, f"PING={response}")
    except Exception as exc:
        return fail(name, str(exc))


def check_hdfs_webhdfs(host: str, port: int, user: str) -> bool:
    name = "HDFS WebHDFS"
    url = f"http://{host}:{port}/webhdfs/v1/?op=LISTSTATUS&user.name={user}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        statuses = data.get("FileStatuses", {}).get("FileStatus", [])
        paths = [item.get("pathSuffix", "") or "/" for item in statuses]
        return ok(name, "root entries=" + ",".join(paths))
    except Exception as exc:
        return fail(name, str(exc))


def check_spark_job(master: str) -> bool:
    name = "Spark job"
    try:
        from pyspark.sql import SparkSession

        spark = (
            SparkSession.builder.master(master)
            .appName("zhiyuan-check-bigdata-connections")
            .getOrCreate()
        )
        try:
            count = spark.range(1, 6).count()
            if count != 5:
                return fail(name, f"unexpected count={count}")
            return ok(name, f"{master} range count={count}")
        finally:
            spark.stop()
    except Exception as exc:
        return fail(name, str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the local Docker bigdata stack.")
    parser.add_argument("--spark-job", action="store_true", help="Run a tiny Spark job.")
    args = parser.parse_args()

    mysql_host = env("MYSQL_HOST", "mysql")
    mysql_port = int(env("MYSQL_PORT", "3306"))
    mysql_root_password = env("MYSQL_ROOT_PASSWORD", "root123456")
    mysql_database = env("ZHIYUAN_DB_NAME", "zhiyuan")
    mysql_user = env("ZHIYUAN_DB_USER", "zhiyuan_app")
    mysql_password = env("ZHIYUAN_DB_PASSWORD", "zhiyuan123456")
    redis_host = env("REDIS_HOST", "redis")
    redis_port = int(env("REDIS_PORT", "6379"))
    spark_master = env("SPARK_MASTER", "spark://spark-master:7077")

    checks = [
        check_tcp("MySQL TCP", mysql_host, mysql_port),
        check_mysql_databases(mysql_host, mysql_port, "root", mysql_root_password, mysql_database),
        check_mysql_app_user(mysql_host, mysql_port, mysql_user, mysql_password, mysql_database),
        check_tcp("Redis TCP", redis_host, redis_port),
        check_redis(redis_host, redis_port),
        check_tcp("HDFS NameNode RPC", "namenode", 9000),
        check_tcp("HDFS NameNode Web", "namenode", 9870),
        check_hdfs_webhdfs("namenode", 9870, "root"),
        check_tcp("YARN ResourceManager Web", "resourcemanager", 8088),
        check_tcp("Hive Metastore TCP", "hive-metastore", 9083),
        check_tcp("HiveServer2 JDBC TCP", "hiveserver2", 10000),
        check_tcp("HiveServer2 Web TCP", "hiveserver2", 10002),
        check_tcp("Spark Master TCP", "spark-master", 7077),
        check_tcp("Spark Master Web", "spark-master", 8080),
        check_tcp("Spark Worker Web", "spark-worker", 8081),
    ]

    if args.spark_job:
        checks.append(check_spark_job(spark_master))

    passed = sum(1 for item in checks if item)
    total = len(checks)
    print(f"\nResult: {passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
