-- 008_user_email_auth.sql
-- 变更原因：
-- - 登录注册从用户名切换为邮箱。
-- - 兼容已执行 007_user_auth_history.sql 的现有数据库。

SET @has_users_email := (
  SELECT COUNT(*)
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'users'
    AND COLUMN_NAME = 'email'
);

SET @add_users_email_sql := IF(
  @has_users_email = 0,
  'ALTER TABLE users ADD COLUMN email VARCHAR(120) NULL COMMENT ''登录邮箱'' AFTER id',
  'SELECT ''users.email already exists'' AS message'
);
PREPARE add_users_email_stmt FROM @add_users_email_sql;
EXECUTE add_users_email_stmt;
DEALLOCATE PREPARE add_users_email_stmt;

UPDATE users
SET email = CASE
  WHEN username REGEXP '^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$' THEN username
  ELSE CONCAT('legacy+', id, '@local.invalid')
END
WHERE email IS NULL OR email = '';

SET @has_users_email_idx := (
  SELECT COUNT(*)
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'users'
    AND INDEX_NAME = 'uk_users_email'
);

SET @add_users_email_idx_sql := IF(
  @has_users_email_idx = 0,
  'ALTER TABLE users ADD UNIQUE KEY uk_users_email (email)',
  'SELECT ''uk_users_email already exists'' AS message'
);
PREPARE add_users_email_idx_stmt FROM @add_users_email_idx_sql;
EXECUTE add_users_email_idx_stmt;
DEALLOCATE PREPARE add_users_email_idx_stmt;
