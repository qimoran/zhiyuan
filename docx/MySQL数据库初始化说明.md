# MySQL 数据库初始化说明

本文档用于说明 S02「MySQL 表结构与基础数据脚本」的执行方法和验证方法。命令默认在 Windows PowerShell 中执行。

## 1. 前置条件

1. 已启动 Docker Desktop。
2. 已进入项目根目录。
3. `.env` 文件已存在，并且包含项目数据库配置。
4. MySQL 容器处于 `healthy` 状态。

进入项目目录：

```powershell
cd "D:\bigdatashixun\zhiyuan"
```

检查容器状态：

```powershell
docker compose --profile hadoop --profile hive --profile spark --profile tools ps
```

## 2. 初始化表结构

执行初始化脚本：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\init_mysql_schema.ps1"
```

脚本会自动读取 `.env` 中的数据库名、业务用户和密码，然后执行：

```text
sql/mysql/001_create_tables.sql
```

当前项目的索引已经写入 `001_create_tables.sql`，不单独维护 `003_create_indexes.sql`，避免同一索引在多个脚本中重复定义。

## 3. 重复执行说明

初始化脚本可以重复执行。建表脚本使用 `CREATE TABLE IF NOT EXISTS`，重复运行不会删除已有数据，也不会重建已有表。

建议每次修改表结构后至少连续执行两次初始化脚本，确认脚本具备幂等性：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\init_mysql_schema.ps1"
powershell -ExecutionPolicy Bypass -File ".\scripts\init_mysql_schema.ps1"
```

## 4. 表结构验证

查看项目表：

```powershell
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T mysql mysql -uzhiyuan_app -p"<项目数据库密码>" zhiyuan -e "SHOW TABLES;"
```

检查核心表数量：

```powershell
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T mysql mysql -uzhiyuan_app -p"<项目数据库密码>" zhiyuan -e "SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema = DATABASE();"
```

检查数据库字符集：

```powershell
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T mysql mysql -uzhiyuan_app -p"<项目数据库密码>" zhiyuan -e "SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = DATABASE();"
```

检查 `universities` 唯一约束：

```powershell
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T mysql mysql -uzhiyuan_app -p"<项目数据库密码>" zhiyuan -e "SHOW INDEX FROM universities;"
```
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T mysql mysql -uzhiyuan_app -p"zhiyuan123456" zhiyuan -e "SHOW INDEX FROM universities;"
## 5. S02 核心表清单

本步骤创建以下 13 张表：

| 表名 | 用途 |
| --- | --- |
| `crawler_runs` | 记录掌上考研等爬虫任务批次 |
| `universities` | 保存重庆研招单位候选库和官网核验状态 |
| `source_documents` | 登记官方 PDF、Excel、网页公告等来源资料 |
| `departments` | 保存学院信息 |
| `majors` | 保存招生专业信息 |
| `enrollment_plans` | 保存招生计划信息 |
| `score_lines` | 保存复试分数线信息 |
| `admission_records` | 保存拟录取样例记录 |
| `major_statistics` | 保存 Spark 或统计任务产出的专业分析结果 |
| `recommendation_logs` | 保存推荐请求和推荐结果日志 |
| `report_records` | 保存 AI 或模板报告生成记录 |
| `pipeline_runs` | 记录数据处理任务运行状态 |
| `data_quality_issues` | 记录数据质量问题 |

## 6. 注意事项

1. 不要把 `.env` 中的真实密码写入文档或代码。
2. 不要执行 `docker compose down -v`，除非明确要删除本地数据库数据。
3. 如果同学拉取项目后数据库为空，先启动 Docker 环境，再执行本初始化脚本。
4. 后续 S03 和 S04 可以基于 `crawler_runs`、`universities`、`source_documents` 继续开发。
