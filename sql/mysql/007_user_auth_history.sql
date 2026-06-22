-- 007_user_auth_history.sql
-- 变更原因：
-- - 增加前端登录注册、个人中心和个人推荐历史功能。
-- - recommendation_logs 增加 user_id，用于按登录用户查询历史推荐记录。

CREATE TABLE IF NOT EXISTS users (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  email VARCHAR(120) NOT NULL COMMENT '登录邮箱',
  username VARCHAR(80) NULL COMMENT '兼容旧版登录用户名',
  nickname VARCHAR(100) NOT NULL COMMENT '昵称',
  password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_email (email),
  UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='前台用户表';

SET @has_recommendation_user_id := (
  SELECT COUNT(*)
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'recommendation_logs'
    AND COLUMN_NAME = 'user_id'
);

SET @add_recommendation_user_id_sql := IF(
  @has_recommendation_user_id = 0,
  'ALTER TABLE recommendation_logs ADD COLUMN user_id BIGINT NULL COMMENT ''前台用户 ID'' AFTER id',
  'SELECT ''recommendation_logs.user_id already exists'' AS message'
);
PREPARE add_recommendation_user_id_stmt FROM @add_recommendation_user_id_sql;
EXECUTE add_recommendation_user_id_stmt;
DEALLOCATE PREPARE add_recommendation_user_id_stmt;

SET @has_recommendation_user_idx := (
  SELECT COUNT(*)
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'recommendation_logs'
    AND INDEX_NAME = 'idx_recommendation_logs_user_created'
);

SET @add_recommendation_user_idx_sql := IF(
  @has_recommendation_user_idx = 0,
  'ALTER TABLE recommendation_logs ADD KEY idx_recommendation_logs_user_created (user_id, created_at)',
  'SELECT ''idx_recommendation_logs_user_created already exists'' AS message'
);
PREPARE add_recommendation_user_idx_stmt FROM @add_recommendation_user_idx_sql;
EXECUTE add_recommendation_user_idx_stmt;
DEALLOCATE PREPARE add_recommendation_user_idx_stmt;

SET @has_recommendation_user_fk := (
  SELECT COUNT(*)
  FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'recommendation_logs'
    AND CONSTRAINT_NAME = 'fk_recommendation_logs_user'
);

SET @add_recommendation_user_fk_sql := IF(
  @has_recommendation_user_fk = 0,
  'ALTER TABLE recommendation_logs ADD CONSTRAINT fk_recommendation_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE SET NULL',
  'SELECT ''fk_recommendation_logs_user already exists'' AS message'
);
PREPARE add_recommendation_user_fk_stmt FROM @add_recommendation_user_fk_sql;
EXECUTE add_recommendation_user_fk_stmt;
DEALLOCATE PREPARE add_recommendation_user_fk_stmt;
