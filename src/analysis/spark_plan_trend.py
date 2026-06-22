"""S13 Spark 招生计划趋势统计。"""

from __future__ import annotations

from pyspark.sql import SparkSession
from pyspark.sql import Window
from pyspark.sql import functions as F

try:
    from src.analysis.spark_common import build_parser, cleaned_csv_path, write_single_csv
except ModuleNotFoundError:
    from spark_common import build_parser, cleaned_csv_path, write_single_csv


def run(batch_id: str, input_dir: str, output_dir: str) -> str:
    spark = SparkSession.builder.appName("zhiyuan-spark-plan-trend").getOrCreate()
    try:
        plans = (
            spark.read.option("header", True)
            .option("multiLine", True)
            .csv(cleaned_csv_path(input_dir, "enrollment_plans", batch_id))
            .withColumn("year_int", F.col("year").cast("int"))
            .withColumn("plan_count_int", F.col("plan_count").cast("int"))
        )
        window = Window.partitionBy("school_id", "major_code", "research_direction").orderBy("year_int")
        result = (
            plans.withColumn("previous_plan_count", F.lag("plan_count_int").over(window))
            .withColumn(
                "plan_change_rate",
                F.when(
                    F.col("previous_plan_count").isNotNull() & (F.col("previous_plan_count") != 0),
                    F.round((F.col("plan_count_int") - F.col("previous_plan_count")) / F.col("previous_plan_count"), 4),
                ),
            )
            .select(
                F.col("year_int").alias("year"),
                "school_id",
                "school_name",
                "department_name",
                "major_code",
                "major_name",
                "research_direction",
                F.col("plan_count_int").alias("plan_count"),
                "previous_plan_count",
                "plan_change_rate",
            )
            .orderBy("school_id", "major_code", "research_direction", "year")
        )
        output_file = f"{output_dir.rstrip('/')}/spark_plan_trend_{batch_id}.csv"
        write_single_csv(result, output_file)
        return output_file
    finally:
        spark.stop()


def main() -> None:
    args = build_parser("S13 Spark 招生计划趋势统计").parse_args()
    output_file = run(args.batch_id, args.input_dir, args.output_dir)
    print(f"plan trend output: {output_file}")


if __name__ == "__main__":
    main()
