-- S16 数据库结构补丁：修正 score_lines 在 NULL 字段下唯一约束不生效的问题。
--
-- 背景：
-- MySQL 的 UNIQUE KEY 允许多行 NULL，因此旧索引
-- (year, line_type, university_id, major_id, major_category)
-- 不能阻止 national 分数线重复插入，因为 university_id、major_id 为 NULL。
--
-- 策略：
-- 新增 3 个普通归一列，把 NULL 归一化为 0 / 空字符串；
-- 用触发器在 INSERT/UPDATE 时自动维护，再建立严格唯一索引。
-- 本脚本只补结构，不删除已有数据。

SET NAMES utf8mb4;
SET time_zone = '+08:00';

SET @university_key_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'score_lines'
    AND COLUMN_NAME = 'university_id_key'
);

SET @university_key_ddl := IF(
  @university_key_exists = 0,
  'ALTER TABLE score_lines ADD COLUMN university_id_key BIGINT NOT NULL DEFAULT 0 COMMENT ''唯一索引用学校 ID 归一值，由触发器维护'' AFTER major_category',
  'SELECT ''score_lines.university_id_key already exists'' AS message'
);

PREPARE university_key_stmt FROM @university_key_ddl;
EXECUTE university_key_stmt;
DEALLOCATE PREPARE university_key_stmt;

SET @major_key_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'score_lines'
    AND COLUMN_NAME = 'major_id_key'
);

SET @major_key_ddl := IF(
  @major_key_exists = 0,
  'ALTER TABLE score_lines ADD COLUMN major_id_key BIGINT NOT NULL DEFAULT 0 COMMENT ''唯一索引用专业 ID 归一值，由触发器维护'' AFTER university_id_key',
  'SELECT ''score_lines.major_id_key already exists'' AS message'
);

PREPARE major_key_stmt FROM @major_key_ddl;
EXECUTE major_key_stmt;
DEALLOCATE PREPARE major_key_stmt;

SET @category_key_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'score_lines'
    AND COLUMN_NAME = 'major_category_key'
);

SET @category_key_ddl := IF(
  @category_key_exists = 0,
  'ALTER TABLE score_lines ADD COLUMN major_category_key VARCHAR(100) NOT NULL DEFAULT '''' COMMENT ''唯一索引用专业门类归一值，由触发器维护'' AFTER major_id_key',
  'SELECT ''score_lines.major_category_key already exists'' AS message'
);

PREPARE category_key_stmt FROM @category_key_ddl;
EXECUTE category_key_stmt;
DEALLOCATE PREPARE category_key_stmt;

UPDATE score_lines
SET university_id_key = IFNULL(university_id, 0),
    major_id_key = IFNULL(major_id, 0),
    major_category_key = IFNULL(major_category, '');

DROP TRIGGER IF EXISTS trg_score_lines_before_insert;
DROP TRIGGER IF EXISTS trg_score_lines_before_update;

DELIMITER $$
CREATE TRIGGER trg_score_lines_before_insert
BEFORE INSERT ON score_lines
FOR EACH ROW
BEGIN
  SET NEW.university_id_key = IFNULL(NEW.university_id, 0);
  SET NEW.major_id_key = IFNULL(NEW.major_id, 0);
  SET NEW.major_category_key = IFNULL(NEW.major_category, '');
END$$

CREATE TRIGGER trg_score_lines_before_update
BEFORE UPDATE ON score_lines
FOR EACH ROW
BEGIN
  SET NEW.university_id_key = IFNULL(NEW.university_id, 0);
  SET NEW.major_id_key = IFNULL(NEW.major_id, 0);
  SET NEW.major_category_key = IFNULL(NEW.major_category, '');
END$$
DELIMITER ;

SET @strict_index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'score_lines'
    AND INDEX_NAME = 'uk_score_lines_strict_unique'
);

SET @strict_index_ddl := IF(
  @strict_index_exists = 0,
  'ALTER TABLE score_lines ADD UNIQUE KEY uk_score_lines_strict_unique (year, line_type, university_id_key, major_id_key, major_category_key)',
  'SELECT ''score_lines.uk_score_lines_strict_unique already exists'' AS message'
);

PREPARE strict_index_stmt FROM @strict_index_ddl;
EXECUTE strict_index_stmt;
DEALLOCATE PREPARE strict_index_stmt;
