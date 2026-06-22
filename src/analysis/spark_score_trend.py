"""S13 Spark 复试线趋势统计。"""

from __future__ import annotations

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

try:
    from src.analysis.spark_common import build_parser, cleaned_csv_path, write_single_csv
except ModuleNotFoundError:
    from spark_common import build_parser, cleaned_csv_path, write_single_csv


def run(batch_id: str, input_dir: str, output_dir: str) -> str:
    spark = SparkSession.builder.appName("zhiyuan-spark-score-trend").getOrCreate()
    try:
        score_lines = (
            spark.read.option("header", True)
            .option("multiLine", True)
            .csv(cleaned_csv_path(input_dir, "score_lines", batch_id))
        )
        result = (
            score_lines.where(F.col("line_type") == "major")
            .withColumn("year_int", F.col("year").cast("int"))
            .withColumn("score_line_int", F.col("total_score_line").cast("int"))
            .groupBy(
                "year_int",
                "school_id",
                "school_name",
                "department_name",
                "major_code",
                "major_name",
                "research_direction",
            )
            .agg(
                F.max("score_line_int").alias("score_line"),
                F.max("politics_line").alias("politics_line"),
                F.max("english_line").alias("english_line"),
                F.max("subject_one_line").alias("subject_one_line"),
                F.max("subject_two_line").alias("subject_two_line"),
            )
            .withColumnRenamed("year_int", "year")
            .withColumn("score_line_year_count", F.lit(1))
            .withColumn(
                "data_quality_level",
                F.when(F.col("score_line").isNotNull(), F.lit("medium")).otherwise(F.lit("low")),
            )
            .orderBy("school_id", "major_code", "research_direction", "year")
        )
        output_file = f"{output_dir.rstrip('/')}/spark_score_trend_{batch_id}.csv"
        write_single_csv(result, output_file)
        return output_file
    finally:
        spark.stop()


def main() -> None:
    args = build_parser("S13 Spark 复试线趋势统计").parse_args()
    output_file = run(args.batch_id, args.input_dir, args.output_dir)
    print(f"score trend output: {output_file}")


if __name__ == "__main__":
    main()
