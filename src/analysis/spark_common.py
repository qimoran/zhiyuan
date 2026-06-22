"""S13 Spark 分析公共工具。"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


DEFAULT_BATCH_ID = "20260616_full_v2"
DEFAULT_INPUT_DIR = "hdfs://namenode:9000/zhiyuan/ods"
DEFAULT_OUTPUT_DIR = "/workspace/data/analysis"


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser


def cleaned_csv_path(input_dir: str, name: str, batch_id: str) -> str:
    if input_dir.startswith("hdfs://") or input_dir.rstrip("/").endswith("/zhiyuan/ods"):
        return f"{input_dir.rstrip('/')}/{name}/{name}_{batch_id}.csv"
    return f"{input_dir.rstrip('/')}/{name}_{batch_id}.csv"


def write_single_csv(dataframe, output_file: str) -> None:
    """把 Spark 输出目录收敛为一个 CSV 文件，方便答辩查看和后续写回 MySQL。"""
    if not output_file.startswith("hdfs://"):
        write_driver_csv(dataframe, output_file)
        return
    output_path = Path(output_file)
    temp_dir = output_path.with_suffix(output_path.suffix + ".spark_tmp")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.coalesce(1).write.mode("overwrite").option("header", True).csv(str(temp_dir))
    part_files = list(temp_dir.glob("part-*.csv"))
    if not part_files:
        raise RuntimeError(f"Spark 未生成 CSV part 文件：{temp_dir}")
    if output_path.exists():
        output_path.unlink()
    part_files[0].replace(output_path)
    shutil.rmtree(temp_dir)


def write_driver_csv(dataframe, output_file: str) -> None:
    """把结果收集到 driver 写本地 CSV，适合本项目 1 万级统计结果。"""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = dataframe.columns
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in dataframe.toLocalIterator():
            writer.writerow({field: row[field] for field in fields})
