-- S04 数据库结构补丁。
-- 作用：补齐当前库与 001_create_tables.sql 不一致的结构。
-- 注意：本脚本只新增缺失表/字段，不删除任何已有数据。

SET NAMES utf8mb4;
SET time_zone = '+08:00';

CREATE TABLE IF NOT EXISTS subject_level_rates (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  university_id BIGINT NOT NULL COMMENT '招生单位 ID',
  subject_code VARCHAR(20) NOT NULL COMMENT '一级学科代码，例如 0802',
  subject_name VARCHAR(150) NULL COMMENT '一级学科名称，例如 机械工程',
  degree_type VARCHAR(20) NULL COMMENT '学位类型：academic、professional',
  level_rate VARCHAR(10) NULL COMMENT '学科评估等级，例如 A+、A、A-、B+、B、B-、C+、C、C-',
  rate_sort INT NULL COMMENT '等级排序值，数值越小越靠前',
  has_doctor TINYINT NOT NULL DEFAULT 0 COMMENT '是否有一级学科博士点：0、1',
  candidate_school_id BIGINT NULL COMMENT '掌上考研学校 ID，便于回溯',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_subject_level_rates_unique (university_id, subject_code),
  KEY idx_subject_level_rates_code (subject_code),
  KEY idx_subject_level_rates_rate (level_rate),
  CONSTRAINT fk_subject_level_rates_university
    FOREIGN KEY (university_id) REFERENCES universities(id)
    ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学科评估等级表';

SET @score_diff_column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'score_lines'
    AND COLUMN_NAME = 'score_diff_to_national'
);

SET @score_diff_ddl := IF(
  @score_diff_column_exists = 0,
  'ALTER TABLE score_lines ADD COLUMN score_diff_to_national INT NULL COMMENT ''院校/专业线总分超出当年国家线的分差，来源掌上考研 schoolScore.diff_total'' AFTER subject_two_line',
  'SELECT ''score_lines.score_diff_to_national already exists'' AS message'
);

PREPARE score_diff_stmt FROM @score_diff_ddl;
EXECUTE score_diff_stmt;
DEALLOCATE PREPARE score_diff_stmt;
