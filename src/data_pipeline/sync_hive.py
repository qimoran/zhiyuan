"""S13 HDFS/Hive 同步入口。

把 S06 cleaned CSV 上传到 HDFS，并执行 Hive 外部表建表脚本。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Any

from src.common.config import PROJECT_ROOT, get_env
from src.common.database import mysql_connection

DEFAULT_BATCH_ID = "20260616_full_v2"
DEFAULT_HDFS_ROOT = "/zhiyuan/ods"
DEFAULT_WEBHDFS_URL = "http://namenode:9870/webhdfs/v1"
DEFAULT_HDFS_USER = "root"
DEFAULT_HIVE_JDBC_URL = "jdbc:hive2://hiveserver2:10000/default"
DEFAULT_HIVE_USER = "hive"
DEFAULT_HIVE_PASSWORD = ""


def sync_hive(
    batch_id: str,
    input_dir: Path,
    hdfs_root: str,
    webhdfs_url: str,
    hdfs_user: str,
    hive_jdbc_url: str,
    hive_user: str,
    hive_password: str,
    skip_upload: bool,
    skip_hive: bool,
    dry_run: bool,
) -> dict[str, Any]:
    files = {
        "majors": input_dir / f"majors_{batch_id}.csv",
        "enrollment_plans": input_dir / f"enrollment_plans_{batch_id}.csv",
        "score_lines": input_dir / f"score_lines_{batch_id}.csv",
        "admission_records": input_dir / f"admission_records_{batch_id}.csv",
    }
    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("S13 输入文件不存在：" + "；".join(missing))
    if not skip_hive and not hive_password:
        raise ValueError("缺少 HIVE_DB_PASSWORD，请在 .env、容器环境变量或 --hive-password 中配置")

    planned_commands: list[list[str]] = []
    for table_name, path in files.items():
        target_dir = f"{hdfs_root.rstrip('/')}/{table_name}"
        planned_commands.append(["WEBHDFS", "MKDIRS", target_dir])
        planned_commands.append(["WEBHDFS", "CREATE", str(path), f"{target_dir}/{path.name}"])

    hive_sql = PROJECT_ROOT / "sql" / "hive" / "001_create_external_tables.sql"
    beeline_command = build_beeline_command(hive_jdbc_url, hive_user, hive_password, hive_sql)
    planned_commands.append(beeline_command)

    if dry_run:
        return {
            "batch_id": batch_id,
            "input_dir": str(input_dir),
            "hdfs_root": hdfs_root,
            "webhdfs_url": webhdfs_url,
            "hive_jdbc_url": hive_jdbc_url,
            "hive_user": hive_user,
            "commands": [" ".join(mask_command(command)) for command in planned_commands],
            "status": "dry_run",
        }

    run_id = create_pipeline_run(batch_id, input_dir, hdfs_root, len(files))
    try:
        if not skip_upload:
            for table_name, path in files.items():
                target_dir = f"{hdfs_root.rstrip('/')}/{table_name}"
                webhdfs_mkdirs(webhdfs_url, hdfs_user, target_dir)
                webhdfs_upload(webhdfs_url, hdfs_user, path, f"{target_dir}/{path.name}")
        if not skip_hive:
            ensure_command("beeline")
            run_command(beeline_command)
        update_pipeline_run(run_id, "success", len(files), 0, None)
    except Exception as exc:
        update_pipeline_run(run_id, "failed", 0, len(files), str(exc))
        raise

    return {
        "batch_id": batch_id,
        "input_dir": str(input_dir),
        "hdfs_root": hdfs_root,
        "webhdfs_url": webhdfs_url,
        "status": "success",
        "synced_files": list(files.keys()),
}


def build_beeline_command(
    hive_jdbc_url: str,
    hive_user: str,
    hive_password: str,
    hive_sql: Path,
) -> list[str]:
    return [
        "beeline",
        "-u",
        hive_jdbc_url,
        "-n",
        hive_user,
        "-p",
        hive_password,
        "-f",
        str(hive_sql),
    ]


def mask_command(command: list[str]) -> list[str]:
    masked = list(command)
    for index, value in enumerate(masked[:-1]):
        if value == "-p":
            masked[index + 1] = "******"
    return masked


def run_command(command: list[str]) -> None:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"命令执行失败：{' '.join(mask_command(command))}\n"
            f"STDOUT:{completed.stdout}\nSTDERR:{completed.stderr}"
        )


def ensure_command(command: str) -> None:
    if shutil.which(command) is None:
        raise RuntimeError(f"当前容器找不到命令：{command}")


def webhdfs_mkdirs(base_url: str, user: str, hdfs_path: str) -> None:
    import requests

    response = requests.put(
        build_webhdfs_url(base_url, hdfs_path),
        params={"op": "MKDIRS", "user.name": user},
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"WebHDFS MKDIRS 失败：{hdfs_path}，{response.status_code} {response.text}")


def webhdfs_upload(base_url: str, user: str, local_path: Path, hdfs_path: str) -> None:
    import requests

    with local_path.open("rb") as file:
        response = requests.put(
            build_webhdfs_url(base_url, hdfs_path),
            params={"op": "CREATE", "overwrite": "true", "user.name": user},
            data=file,
            allow_redirects=True,
            timeout=120,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"WebHDFS CREATE 失败：{hdfs_path}，{response.status_code} {response.text}")


def build_webhdfs_url(base_url: str, hdfs_path: str) -> str:
    return f"{base_url.rstrip('/')}/{hdfs_path.strip('/')}"


def create_pipeline_run(batch_id: str, input_dir: Path, hdfs_root: str, total_count: int) -> int:
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_runs (
                  task_name, task_type, status, input_path, output_path,
                  total_count, success_count, failed_count, started_at
                )
                VALUES (
                  %(task_name)s, 'sync_hive', 'running', %(input_path)s, %(output_path)s,
                  %(total_count)s, 0, 0, NOW()
                )
                """,
                {
                    "task_name": f"S13_sync_hive_{batch_id}",
                    "input_path": project_relative(input_dir),
                    "output_path": f"hdfs:{hdfs_root}",
                    "total_count": total_count,
                },
            )
            run_id = int(cursor.lastrowid)
        connection.commit()
    return run_id


def update_pipeline_run(
    run_id: int,
    status: str,
    success_count: int,
    failed_count: int,
    error_message: str | None,
) -> None:
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_runs
                SET status = %(status)s,
                    success_count = %(success_count)s,
                    failed_count = %(failed_count)s,
                    error_message = %(error_message)s,
                    finished_at = NOW()
                WHERE id = %(id)s
                """,
                {
                    "id": run_id,
                    "status": status,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "error_message": error_message,
                },
            )
        connection.commit()


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="S13 HDFS/Hive 同步")
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "kaoyan_v2_cleaned",
    )
    parser.add_argument("--hdfs-root", default=DEFAULT_HDFS_ROOT)
    parser.add_argument("--webhdfs-url", default=DEFAULT_WEBHDFS_URL)
    parser.add_argument("--hdfs-user", default=DEFAULT_HDFS_USER)
    parser.add_argument("--hive-jdbc-url", default=get_env("HIVE_JDBC_URL", DEFAULT_HIVE_JDBC_URL))
    parser.add_argument("--hive-user", default=get_env("HIVE_DB_USER", DEFAULT_HIVE_USER))
    parser.add_argument("--hive-password", default=get_env("HIVE_DB_PASSWORD", DEFAULT_HIVE_PASSWORD))
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--skip-hive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = sync_hive(
        batch_id=args.batch_id,
        input_dir=args.input_dir,
        hdfs_root=args.hdfs_root,
        webhdfs_url=args.webhdfs_url,
        hdfs_user=args.hdfs_user,
        hive_jdbc_url=args.hive_jdbc_url,
        hive_user=args.hive_user,
        hive_password=args.hive_password,
        skip_upload=args.skip_upload,
        skip_hive=args.skip_hive,
        dry_run=args.dry_run,
    )
    print(summary)


if __name__ == "__main__":
    main()
