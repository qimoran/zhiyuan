CREATE DATABASE IF NOT EXISTS zhiyuan_ods;

USE zhiyuan_ods;

CREATE EXTERNAL TABLE IF NOT EXISTS ods_majors (
  batch_id STRING,
  school_id BIGINT,
  school_name STRING,
  depart_id BIGINT,
  department_name STRING,
  year INT,
  plan_id BIGINT,
  spe_id BIGINT,
  major_code STRING,
  major_name STRING,
  major_category_code STRING,
  major_category STRING,
  level1_code STRING,
  level1_name STRING,
  level2_code STRING,
  level2_name STRING,
  degree_type STRING,
  degree_type_name STRING,
  study_mode STRING,
  recruit_type STRING,
  recruit_type_name STRING,
  exam_class STRING,
  exam_class_name STRING,
  research_direction STRING,
  research_area_note STRING,
  exam_subjects STRING,
  exam_book_clean STRING,
  exam_book_year STRING,
  intro_id STRING,
  source_file STRING
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
STORED AS TEXTFILE
LOCATION '/zhiyuan/ods/majors'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS ods_enrollment_plans (
  batch_id STRING,
  year INT,
  school_id BIGINT,
  school_name STRING,
  depart_id BIGINT,
  department_name STRING,
  plan_id BIGINT,
  major_code STRING,
  major_name STRING,
  degree_type STRING,
  study_mode STRING,
  research_direction STRING,
  exam_subjects STRING,
  plan_count INT,
  recommended_exemption_count INT,
  unified_exam_count INT,
  min_score INT,
  score_years_json STRING,
  plan_remark STRING,
  source_file STRING
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
STORED AS TEXTFILE
LOCATION '/zhiyuan/ods/enrollment_plans'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS ods_score_lines (
  batch_id STRING,
  year INT,
  school_id BIGINT,
  school_name STRING,
  depart_id BIGINT,
  department_name STRING,
  plan_id BIGINT,
  major_code STRING,
  major_name STRING,
  degree_type STRING,
  study_mode STRING,
  research_direction STRING,
  exam_subjects STRING,
  line_type STRING,
  score_data_type STRING,
  score_depart_id BIGINT,
  score_depart_name STRING,
  score_code STRING,
  score_name STRING,
  score_degree_type STRING,
  total_score_line INT,
  politics_line INT,
  english_line INT,
  subject_one_line INT,
  subject_two_line INT,
  score_diff_to_national INT,
  score_diff_politics INT,
  score_diff_english INT,
  score_note STRING,
  score_special_remark STRING,
  source_file STRING
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
STORED AS TEXTFILE
LOCATION '/zhiyuan/ods/score_lines'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS ods_admission_records (
  batch_id STRING,
  year INT,
  school_id BIGINT,
  school_name STRING,
  depart_id BIGINT,
  department_name STRING,
  major_code STRING,
  major_name STRING,
  research_direction STRING,
  candidate_no_hash STRING,
  initial_total_score DECIMAL(6,2),
  politics_score DECIMAL(6,2),
  english_score DECIMAL(6,2),
  subject_one_score DECIMAL(6,2),
  subject_two_score DECIMAL(6,2),
  reexam_score DECIMAL(6,2),
  final_score DECIMAL(8,2),
  admission_status STRING,
  source_file STRING
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar' = '"',
  'escapeChar' = '\\'
)
STORED AS TEXTFILE
LOCATION '/zhiyuan/ods/admission_records'
TBLPROPERTIES ('skip.header.line.count'='1');
