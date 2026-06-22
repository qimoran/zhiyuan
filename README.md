# 志愿填报数据分析系统

本项目使用 Python、MySQL、Redis、Hadoop、Hive、Spark 搭建本地开发环境。Docker 环境已经封装在项目内，同学 clone 项目后可以用 PowerShell 一键启动。

## 一键启动

在 Windows PowerShell 中进入项目根目录：

```powershell
cd "D:\bigdatashixun\zhiyuan"
powershell -ExecutionPolicy Bypass -File ".\scripts\start_dev_env.ps1"
```

脚本会自动完成：

1. 检查 Docker Desktop 是否已经启动。
2. 缺少 `.env` 时根据 `.env.example` 生成本地配置。
3. 检查本地是否已有 Hadoop、Hive、Spark、Python 大数据镜像。
4. 缺少镜像时自动执行 Docker build。
5. 启动 MySQL、Redis、Hadoop、Hive、Spark、Python 工具容器。
6. 初始化 `zhiyuan` 数据库和 `zhiyuan_app` 开发用户。
7. 自动应用 MySQL 结构脚本 `001_create_tables.sql`、`002_s04_schema_patch.sql`、`005_score_lines_unique_patch.sql`。
8. 执行环境连通性检查。

首次在新电脑运行时，Docker build 会下载 Hadoop、Hive、Spark 等依赖，体积较大，耗时取决于网络速度。

## 常用命令

检查环境：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\check_dev_env.ps1" -SparkJob
```

停止环境，不删除数据：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\stop_dev_env.ps1"
```

只启动，不跑检查：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\start_dev_env.ps1" -SkipCheck
```

启动 Flask Web：

```powershell
docker compose --profile hadoop --profile hive --profile spark --profile tools exec python python -m src.app
```

浏览器访问：

```text
http://127.0.0.1:5000/
```

## 项目主流程命令

S07 入库检查：

```powershell
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T python python -m src.data_pipeline.load_mysql --batch-id 20260616_full_v2 --dry-run
```

数据库结构补丁检查：

```powershell
Get-Content -Path ".\sql\mysql\005_score_lines_unique_patch.sql" | docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T mysql mysql --default-character-set=utf8mb4 -uroot -p"root123456" zhiyuan
```

该补丁会给 `score_lines` 增加严格唯一索引和触发器，防止重复导入国家线。

S12 图表接口检查：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/chart/university-type" -Method Get
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/chart/line-trend?university_id=1&major_id=100" -Method Get
```

S13 HDFS/Hive/Spark 分析链路（会同步 `majors`、`enrollment_plans`、`score_lines`、`admission_records` 到 HDFS）：

```powershell
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T python python -m src.data_pipeline.sync_hive --batch-id 20260616_full_v2
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T python spark-submit --master "spark://spark-master:7077" "/workspace/src/analysis/spark_score_trend.py" --batch-id 20260616_full_v2
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T python spark-submit --master "spark://spark-master:7077" "/workspace/src/analysis/spark_plan_trend.py" --batch-id 20260616_full_v2
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T python spark-submit --master "spark://spark-master:7077" "/workspace/src/analysis/spark_major_heat.py" --batch-id 20260616_full_v2
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T python python -m src.analysis.write_analysis_result --batch-id 20260616_full_v2
```

`sync_hive` 默认读取 `.env` 或容器环境变量中的 `HIVE_JDBC_URL`、`HIVE_DB_USER`、`HIVE_DB_PASSWORD`。本地开发可以继续使用 `.env.example` 里的默认值；正式环境请替换为自己的 Hive 账号密码，dry-run 输出会自动隐藏密码。

S14 模板报告接口：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/report/generate" -Method Post -ContentType "application/json" -Body '{"recommendation_trace_id":"test-trace-id","report_type":"template"}'
```

S15 测试：

```powershell
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T python python -m compileall /workspace/src
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T python pytest "/workspace/tests/unit"
docker compose --profile hadoop --profile hive --profile spark --profile tools exec -T python pytest "/workspace/tests/integration"
```

## 服务地址

| 服务 | Windows 访问地址 |
| --- | --- |
| MySQL | `127.0.0.1:13306` |
| Redis | `127.0.0.1:16379` |
| HDFS NameNode | `http://127.0.0.1:9870` |
| YARN ResourceManager | `http://127.0.0.1:8088` |
| HiveServer2 JDBC | `127.0.0.1:10000` |
| HiveServer2 Web | `http://127.0.0.1:10002` |
| Spark Master | `http://127.0.0.1:18080` |
| Spark Worker | `http://127.0.0.1:18081` |

## 配置说明

本机配置文件是 `.env`，不提交到 GitHub。需要提交的是 `.env.example`。

默认开发账号：

| 项目 | 值 |
| --- | --- |
| 数据库 | `zhiyuan` |
| 业务用户 | `zhiyuan_app` |
| 业务用户密码 | `zhiyuan123456` |
| MySQL root 密码 | `root123456` |

这些是本地开发默认值，不要用于真实生产环境。

## 目录说明

| 目录 | 说明 |
| --- | --- |
| `docker/` | Docker Compose 构建上下文、配置和 MySQL 初始化脚本 |
| `scripts/` | PowerShell 启动、检查、停止脚本 |
| `src/` | 项目源代码 |
| `config/` | 项目配置 |
| `docx/` | 项目文档 |
| `logs/` | 本地日志目录 |
| `data/analysis/` | Spark 分析输出 |
| `sql/hive/` | Hive 外部表建表脚本 |
| `tests/` | 单元测试和集成测试 |

## 注意事项

1. 运行前先启动 Docker Desktop。
2. 不要把 `.env`、`.docker-data`、日志文件提交到 GitHub。
3. 不要执行 `docker compose down -v`，避免误删本地数据。
4. 如果端口被占用，修改 `.env` 中对应端口后重新运行启动脚本。
