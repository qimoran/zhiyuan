-- 重庆高校考研择校推荐系统 MySQL 表结构初始化脚本。
-- 执行前请确认当前数据库为项目数据库 zhiyuan。

SET NAMES utf8mb4;
SET time_zone = '+08:00';

CREATE TABLE IF NOT EXISTS crawler_runs (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  crawler_name VARCHAR(100) NOT NULL COMMENT '爬虫名称，例如 kaoyan_school_list',
  target_url VARCHAR(1000) NOT NULL COMMENT '目标页面 URL',
  api_url VARCHAR(1000) NULL COMMENT '实际请求接口 URL',
  request_params_json JSON NULL COMMENT '请求参数 JSON',
  raw_output_path VARCHAR(500) NULL COMMENT '原始响应保存路径',
  parsed_output_path VARCHAR(500) NULL COMMENT '解析后 CSV 保存路径',
  status VARCHAR(30) NOT NULL DEFAULT 'running' COMMENT '运行状态：running、success、failed',
  total_count INT NULL COMMENT '接口返回总数',
  fetched_count INT NULL COMMENT '实际抓取数量',
  error_message TEXT NULL COMMENT '异常信息',
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
  finished_at DATETIME NULL COMMENT '结束时间',
  PRIMARY KEY (id),
  KEY idx_crawler_runs_name_status (crawler_name, status),
  KEY idx_crawler_runs_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='爬虫运行表';

CREATE TABLE IF NOT EXISTS universities (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  candidate_school_id BIGINT NULL COMMENT '掌上考研院校库学校 ID',
  university_name VARCHAR(100) NOT NULL COMMENT '招生单位名称',
  province VARCHAR(50) NOT NULL DEFAULT '重庆' COMMENT '省份',
  city VARCHAR(50) NOT NULL DEFAULT '重庆市' COMMENT '城市',
  province_area VARCHAR(20) NOT NULL DEFAULT 'A区' COMMENT '考研分区',
  school_type VARCHAR(50) NULL COMMENT '学校类型，例如综合类、理工类、医药类',
  school_org_type VARCHAR(50) NULL COMMENT '招生单位类型，例如高等院校、科研院所',
  school_level VARCHAR(100) NULL COMMENT '学校层次，例如985、211、双一流、自划线、普通院校',
  coverage_priority VARCHAR(10) NOT NULL DEFAULT 'P2' COMMENT '项目覆盖优先级：P0、P1、P2、P3',
  official_site VARCHAR(500) NULL COMMENT '研究生院官网或招生网',
  candidate_source_url VARCHAR(500) NULL COMMENT '候选来源 URL',
  recruit_number_reference INT NULL COMMENT '掌上考研返回的参考招生人数',
  major_number_reference INT NULL COMMENT '掌上考研返回的专业数量',
  crawler_run_id BIGINT NULL COMMENT '爬虫运行批次 ID',
  candidate_crawled_at DATETIME NULL COMMENT '候选库抓取时间',
  official_verified_status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '官网核验状态：pending、verified、unconfirmed',
  remark VARCHAR(500) NULL COMMENT '备注',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_universities_name (university_name),
  UNIQUE KEY uk_universities_candidate_school_id (candidate_school_id),
  KEY idx_universities_priority (coverage_priority),
  KEY idx_universities_type (school_type),
  KEY idx_universities_verified_status (official_verified_status),
  KEY idx_universities_crawler_run_id (crawler_run_id),
  CONSTRAINT fk_universities_crawler_run
    FOREIGN KEY (crawler_run_id) REFERENCES crawler_runs(id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='招生单位表';

CREATE TABLE IF NOT EXISTS source_documents (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  university_id BIGINT NOT NULL COMMENT '招生单位 ID',
  year INT NULL COMMENT '招生年份或公告年份',
  document_type VARCHAR(50) NOT NULL COMMENT '文档类型：catalog、score_line、admission_list、plan、notice、ratio',
  document_title VARCHAR(300) NOT NULL COMMENT '文件或公告标题',
  source_url VARCHAR(1000) NULL COMMENT '来源页面或文件 URL',
  local_path VARCHAR(500) NULL COMMENT '本地保存路径',
  published_date DATE NULL COMMENT '官网发布日期',
  collector VARCHAR(50) NULL COMMENT '采集人',
  collected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '采集时间',
  process_status VARCHAR(30) NOT NULL DEFAULT 'pending' COMMENT '处理状态：pending、extracted、review_required、loaded、error',
  official_verified TINYINT NOT NULL DEFAULT 0 COMMENT '是否已核验官网来源',
  remark VARCHAR(1000) NULL COMMENT '备注',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_source_university_year (university_id, year),
  KEY idx_source_type_status (document_type, process_status),
  KEY idx_source_collected_at (collected_at),
  CONSTRAINT fk_source_documents_university
    FOREIGN KEY (university_id) REFERENCES universities(id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='来源资料表';

CREATE TABLE IF NOT EXISTS departments (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  university_id BIGINT NOT NULL COMMENT '招生单位 ID',
  department_name VARCHAR(150) NOT NULL COMMENT '学院或招生院系名称',
  standard_name VARCHAR(150) NULL COMMENT '标准化名称',
  source_id BIGINT NULL COMMENT '来源资料 ID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_departments_university_name (university_id, department_name),
  KEY idx_departments_source_id (source_id),
  CONSTRAINT fk_departments_university
    FOREIGN KEY (university_id) REFERENCES universities(id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_departments_source
    FOREIGN KEY (source_id) REFERENCES source_documents(id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学院表';

CREATE TABLE IF NOT EXISTS majors (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  university_id BIGINT NOT NULL COMMENT '招生单位 ID',
  department_id BIGINT NOT NULL COMMENT '学院 ID',
  major_code VARCHAR(20) NOT NULL COMMENT '专业代码',
  major_name VARCHAR(150) NOT NULL COMMENT '专业名称',
  major_category VARCHAR(100) NULL COMMENT '专业门类，例如电子信息、教育、法学',
  degree_type VARCHAR(20) NULL COMMENT '学位类型：academic、professional',
  study_mode VARCHAR(20) NULL COMMENT '学习方式：full_time、part_time',
  research_direction VARCHAR(300) NULL COMMENT '研究方向',
  exam_subjects VARCHAR(500) NULL COMMENT '初试科目',
  source_id BIGINT NULL COMMENT '来源资料 ID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_majors_unique (university_id, department_id, major_code, study_mode, research_direction),
  KEY idx_majors_major_code (major_code),
  KEY idx_majors_category (major_category),
  KEY idx_majors_source_id (source_id),
  CONSTRAINT fk_majors_university
    FOREIGN KEY (university_id) REFERENCES universities(id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_majors_department
    FOREIGN KEY (department_id) REFERENCES departments(id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_majors_source
    FOREIGN KEY (source_id) REFERENCES source_documents(id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='专业表';

CREATE TABLE IF NOT EXISTS enrollment_plans (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  year INT NOT NULL COMMENT '招生年份',
  university_id BIGINT NOT NULL COMMENT '招生单位 ID',
  department_id BIGINT NULL COMMENT '学院 ID',
  major_id BIGINT NOT NULL COMMENT '专业 ID',
  plan_count INT NULL COMMENT '总招生计划',
  recommended_exemption_count INT NULL COMMENT '推免人数',
  unified_exam_count INT NULL COMMENT '统考名额',
  source_id BIGINT NULL COMMENT '来源资料 ID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_enrollment_plans_unique (year, university_id, major_id),
  KEY idx_enrollment_plans_year_university (year, university_id),
  KEY idx_enrollment_plans_major (major_id),
  KEY idx_enrollment_plans_source_id (source_id),
  CONSTRAINT chk_enrollment_plan_count CHECK (plan_count IS NULL OR plan_count >= 0),
  CONSTRAINT chk_enrollment_recommended_count CHECK (recommended_exemption_count IS NULL OR recommended_exemption_count >= 0),
  CONSTRAINT chk_enrollment_unified_count CHECK (unified_exam_count IS NULL OR unified_exam_count >= 0),
  CONSTRAINT fk_enrollment_plans_university
    FOREIGN KEY (university_id) REFERENCES universities(id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_enrollment_plans_department
    FOREIGN KEY (department_id) REFERENCES departments(id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_enrollment_plans_major
    FOREIGN KEY (major_id) REFERENCES majors(id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_enrollment_plans_source
    FOREIGN KEY (source_id) REFERENCES source_documents(id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='招生计划表';

CREATE TABLE IF NOT EXISTS score_lines (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  year INT NOT NULL COMMENT '年份',
  line_type VARCHAR(30) NOT NULL COMMENT '分数线类型：national、university、major',
  university_id BIGINT NULL COMMENT '招生单位 ID，国家线可为空',
  department_id BIGINT NULL COMMENT '学院 ID',
  major_id BIGINT NULL COMMENT '专业 ID',
  major_category VARCHAR(100) NULL COMMENT '专业门类',
  total_score_line INT NOT NULL COMMENT '总分线',
  politics_line INT NULL COMMENT '政治线',
  english_line INT NULL COMMENT '英语线',
  subject_one_line INT NULL COMMENT '业务课一线',
  subject_two_line INT NULL COMMENT '业务课二线',
  source_id BIGINT NULL COMMENT '来源资料 ID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_score_lines_unique (year, line_type, university_id, major_id, major_category),
  KEY idx_score_lines_year_type (year, line_type),
  KEY idx_score_lines_university_major (university_id, major_id),
  KEY idx_score_lines_category (major_category),
  KEY idx_score_lines_source_id (source_id),
  CONSTRAINT chk_score_lines_total CHECK (total_score_line >= 0),
  CONSTRAINT fk_score_lines_university
    FOREIGN KEY (university_id) REFERENCES universities(id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_score_lines_department
    FOREIGN KEY (department_id) REFERENCES departments(id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_score_lines_major
    FOREIGN KEY (major_id) REFERENCES majors(id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_score_lines_source
    FOREIGN KEY (source_id) REFERENCES source_documents(id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='复试分数线表';

CREATE TABLE IF NOT EXISTS admission_records (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  year INT NOT NULL COMMENT '年份',
  university_id BIGINT NOT NULL COMMENT '招生单位 ID',
  department_id BIGINT NULL COMMENT '学院 ID',
  major_id BIGINT NOT NULL COMMENT '专业 ID',
  candidate_no_hash VARCHAR(128) NULL COMMENT '脱敏后的考生编号哈希',
  initial_total_score DECIMAL(6,2) NULL COMMENT '初试总分',
  politics_score DECIMAL(6,2) NULL COMMENT '政治分数',
  english_score DECIMAL(6,2) NULL COMMENT '英语分数',
  subject_one_score DECIMAL(6,2) NULL COMMENT '业务课一分数',
  subject_two_score DECIMAL(6,2) NULL COMMENT '业务课二分数',
  reexam_score DECIMAL(6,2) NULL COMMENT '复试成绩',
  final_score DECIMAL(6,2) NULL COMMENT '总成绩',
  admission_status VARCHAR(30) NOT NULL DEFAULT 'unknown' COMMENT '录取状态：admitted、not_admitted、unknown',
  source_id BIGINT NULL COMMENT '来源资料 ID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_admission_records_unique (year, university_id, major_id, candidate_no_hash),
  KEY idx_admission_year_university_major (year, university_id, major_id),
  KEY idx_admission_status (admission_status),
  KEY idx_admission_source_id (source_id),
  CONSTRAINT fk_admission_records_university
    FOREIGN KEY (university_id) REFERENCES universities(id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_admission_records_department
    FOREIGN KEY (department_id) REFERENCES departments(id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_admission_records_major
    FOREIGN KEY (major_id) REFERENCES majors(id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_admission_records_source
    FOREIGN KEY (source_id) REFERENCES source_documents(id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='拟录取记录表';

CREATE TABLE IF NOT EXISTS major_statistics (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  year INT NOT NULL COMMENT '年份',
  university_id BIGINT NOT NULL COMMENT '招生单位 ID',
  major_id BIGINT NOT NULL COMMENT '专业 ID',
  plan_count INT NULL COMMENT '招生计划',
  admission_count INT NULL COMMENT '拟录取人数',
  min_initial_score DECIMAL(6,2) NULL COMMENT '初试最低分',
  avg_initial_score DECIMAL(6,2) NULL COMMENT '初试平均分',
  max_initial_score DECIMAL(6,2) NULL COMMENT '初试最高分',
  score_line INT NULL COMMENT '参考复试线',
  plan_change_rate DECIMAL(8,4) NULL COMMENT '招生计划变化率',
  heat_score DECIMAL(8,4) NULL COMMENT '专业热度评分',
  data_quality_level VARCHAR(20) NOT NULL DEFAULT 'low' COMMENT '数据质量等级：high、medium、low',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_major_statistics_unique (year, university_id, major_id),
  KEY idx_major_statistics_university_major (university_id, major_id),
  KEY idx_major_statistics_heat_score (heat_score),
  CONSTRAINT fk_major_statistics_university
    FOREIGN KEY (university_id) REFERENCES universities(id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_major_statistics_major
    FOREIGN KEY (major_id) REFERENCES majors(id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='专业统计结果表';

CREATE TABLE IF NOT EXISTS recommendation_logs (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  trace_id VARCHAR(64) NOT NULL COMMENT '请求追踪 ID',
  request_json JSON NOT NULL COMMENT '推荐请求参数',
  result_summary_json JSON NULL COMMENT '推荐结果摘要',
  warning_json JSON NULL COMMENT '风险提示',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_recommendation_logs_trace_id (trace_id),
  KEY idx_recommendation_logs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='推荐日志表';

CREATE TABLE IF NOT EXISTS report_records (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  trace_id VARCHAR(64) NOT NULL COMMENT '请求追踪 ID',
  recommendation_log_id BIGINT NULL COMMENT '推荐日志 ID',
  report_type VARCHAR(30) NOT NULL COMMENT '报告类型：llm、template',
  prompt_json JSON NULL COMMENT '提示词结构化内容',
  report_content MEDIUMTEXT NOT NULL COMMENT '报告内容',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_report_records_trace_id (trace_id),
  KEY idx_report_records_recommendation_log_id (recommendation_log_id),
  CONSTRAINT fk_report_records_recommendation_log
    FOREIGN KEY (recommendation_log_id) REFERENCES recommendation_logs(id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报告记录表';

CREATE TABLE IF NOT EXISTS pipeline_runs (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  task_name VARCHAR(100) NOT NULL COMMENT '任务名称',
  task_type VARCHAR(50) NOT NULL COMMENT '任务类型：extract、clean、load、sync_hive、spark_analysis',
  status VARCHAR(30) NOT NULL DEFAULT 'running' COMMENT '任务状态：running、success、failed',
  input_path VARCHAR(500) NULL COMMENT '输入路径',
  output_path VARCHAR(500) NULL COMMENT '输出路径',
  total_count INT NULL COMMENT '总记录数',
  success_count INT NULL COMMENT '成功数',
  failed_count INT NULL COMMENT '失败数',
  error_message TEXT NULL COMMENT '错误信息',
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
  finished_at DATETIME NULL COMMENT '结束时间',
  PRIMARY KEY (id),
  KEY idx_pipeline_runs_type_status (task_type, status),
  KEY idx_pipeline_runs_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据任务运行表';

CREATE TABLE IF NOT EXISTS data_quality_issues (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  source_id BIGINT NULL COMMENT '来源资料 ID',
  table_name VARCHAR(100) NULL COMMENT '涉及表',
  field_name VARCHAR(100) NULL COMMENT '涉及字段',
  issue_type VARCHAR(50) NOT NULL COMMENT '问题类型：missing、invalid_format、duplicate、inconsistent',
  raw_value VARCHAR(1000) NULL COMMENT '原始值',
  suggestion VARCHAR(1000) NULL COMMENT '处理建议',
  status VARCHAR(30) NOT NULL DEFAULT 'open' COMMENT '处理状态：open、fixed、ignored',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_data_quality_source_id (source_id),
  KEY idx_data_quality_type_status (issue_type, status),
  CONSTRAINT fk_data_quality_issues_source
    FOREIGN KEY (source_id) REFERENCES source_documents(id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据质量问题表';
