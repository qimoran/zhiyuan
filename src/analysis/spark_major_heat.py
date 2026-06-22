"""S13 Spark 专业热度统计。"""

from __future__ import annotations

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

try:
    from src.analysis.spark_common import build_parser, cleaned_csv_path, write_single_csv
except ModuleNotFoundError:
    from spark_common import build_parser, cleaned_csv_path, write_single_csv


def run(batch_id: str, input_dir: str, output_dir: str) -> str:
    spark = SparkSession.builder.appName("zhiyuan-spark-major-heat").getOrCreate()
    try:
        majors = (
            spark.read.option("header", True)
            .option("multiLine", True)
            .csv(cleaned_csv_path(input_dir, "majors", batch_id))
        )
        plans = (
            spark.read.option("header", True)
            .option("multiLine", True)
            .csv(cleaned_csv_path(input_dir, "enrollment_plans", batch_id))
            .withColumn("plan_count_int", F.col("plan_count").cast("int"))
        )
        latest_year = plans.select(F.max(F.col("year").cast("int")).alias("year")).first()["year"]
        result = (
            plans.where(F.col("year").cast("int") == F.lit(latest_year))
            .join(
                majors.select("school_id", "department_name", "major_code", "research_direction", "major_category"),
                ["school_id", "department_name", "major_code", "research_direction"],
                "left",
            )
            .withColumn("plan_count_int", F.coalesce(F.col("plan_count_int"), F.lit(0)))
            .withColumn(
                "heat_score",
                F.round(F.col("plan_count_int") * F.lit(1.0) + F.when(F.col("major_category").isNotNull(), 5).otherwise(0), 4),
            )
            .select(
                F.col("year").cast("int").alias("year"),
                "school_id",
                "school_name",
                "department_name",
                "major_code",
                "major_name",
                "major_category",
                "research_direction",
                F.col("plan_count_int").alias("plan_count"),
                "heat_score",
            )
            .orderBy(F.desc("heat_score"), "school_id", "major_code")
        )
        output_file = f"{output_dir.rstrip('/')}/spark_major_heat_{batch_id}.csv"
        write_single_csv(result, output_file)
        return output_file
    finally:
        spark.stop()


def main() -> None:
    args = build_parser("S13 Spark 专业热度统计").parse_args()
    output_file = run(args.batch_id, args.input_dir, args.output_dir)
    print(f"major heat output: {output_file}")


if __name__ == "__main__":
    main()
