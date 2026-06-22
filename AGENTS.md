# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目概述

重庆高校考研择校推荐系统 - 基于大数据技术的考研择校辅助工具。

项目采用 Python + MySQL + Redis + Hadoop + Hive + Spark 的大数据技术栈，通过爬虫采集重庆高校考研公开数据，经过清洗、入库、分析后，为考研学生提供"冲刺、稳妥、保底"三档院校推荐和 AI 择校建议报告。

**关键特点**：
- 数据来源可追溯：每条核心数据通过 `source_documents` 表关联到原始资料
- 半自动化数据处理：PDF/Excel 提取 + 人工校对 + 标准化入库
- 完整大数据链路：MySQL 在线查询 + HDFS/Hive 数据仓库 + Spark 离线分析
- 第三方数据核验：掌上考研 V2 API 数据作为候选库，关键字段需官网二次核验

## 环境与依赖

### 本地开发环境

- **操作系统**：Windows 11，默认 PowerShell 终端
- **Python 版本**：3.12（推荐用 Miniconda 管理独立环境）
- **容器环境**：Docker Desktop + Docker Compose
- **大数据组件**：Hadoop 3.3.6、Hive 4.0.1、Spark 3.5.1（均在 Docker 中）
- **数据库**：MySQL 8.0（端口 13306）、Redis 5.0.14（端口 16379）
- **Web 框架**：Flask

### 环境启动

一键启动完整 Docker 环境（首次运行会自动构建镜像）：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\start_dev_env.ps1"
```

环境检查（包含 Spark 作业验证）：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\check_dev_env.ps1" -SparkJob
```

停止环境（保留数据）：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\stop_dev_env.ps1"
```

### 配置管理

- **`.env`**：本地配置，不提交仓库（从 `.env.example` 复制生成）
- **`config/*.yaml`**：应用配置、数据库配置、推荐规则配置
- **优先级**：环境变量 > YAML 配置 > 代码默认值
- **配置加载**：`src/common/config.py` 提供 `get_app_config()`、`get_database_config()`、`get_recommend_rules()` 等方法

### Python 依赖

项目依赖在 `requirements.txt`（暂未创建），核心依赖包括：

- Flask：Web 框架
- PyMySQL：MySQL 驱动
- Requests、BeautifulSoup：爬虫
- Pandas、NumPy：数据处理
- PyYAML：配置文件读取（可选，缺失时回退到 `.env`）

安装依赖前务必激活项目专属 conda 环境，不要污染 `base` 环境。

## 项目架构

### 目录结构

```
zhiyuan/
├── src/                        # 项目源代码
│   ├── common/                 # 公共模块
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # MySQL 连接和基础查询
│   │   ├── logger.py          # 日志管理
│   │   ├── exceptions.py      # 自定义异常
│   │   ├── response.py        # 统一响应格式
│   │   └── trace.py           # 请求追踪 ID
│   ├── crawlers/              # 爬虫模块
│   │   ├── run_kaoyan_crawl.py        # 掌上考研 V2 统一爬虫入口
│   │   ├── school_list_crawler.py     # 重庆院校列表爬虫
│   │   ├── plan_list_v2_crawler.py    # 招生计划列表爬虫
│   │   ├── plan_detail_v2_crawler.py  # 专业详情爬虫
│   │   ├── score_line_crawler.py      # 分数线爬虫
│   │   └── level_rate_crawler.py      # 学科评估爬虫
│   ├── data_pipeline/         # 数据处理模块
│   │   └── source_registry.py # S04 候选库入库与来源登记
│   └── app.py                 # Flask 应用入口
├── sql/mysql/                 # MySQL 建表和升级脚本
│   ├── 001_create_tables.sql  # 核心表结构
│   └── 002_s04_schema_patch.sql  # S04 表结构补丁
├── config/                    # 配置文件
│   └── logging.yaml          # 日志配置
├── scripts/                   # 运维脚本
│   ├── start_dev_env.ps1     # 启动 Docker 环境
│   ├── check_dev_env.ps1     # 环境检查
│   └── stop_dev_env.ps1      # 停止环境
├── docker/                    # Docker 构建上下文
│   ├── build-context/        # Hadoop/Hive/Spark 配置和 Dockerfile
│   └── mysql/init/           # MySQL 初始化脚本
├── data/                      # 数据目录（不提交仓库）
│   ├── raw/kaoyan_v2/        # 爬虫原始 JSON 输出
│   └── processed/kaoyan_v2_integrated/  # 统一整合 CSV
├── logs/                      # 运行日志（不提交仓库）
├── docx/                      # 项目文档
├── .env                       # 本地配置（不提交）
├── .env.example               # 配置模板
├── docker-compose.yml         # Docker 编排文件
└── README.md                  # 项目说明
```

### 核心模块说明

#### 1. 公共模块（`src/common/`）

- **`config.py`**：统一配置管理，支持 `.env` 和 YAML 配置文件，提供 `get_app_config()`、`get_database_config()` 等便捷方法
- **`database.py`**：MySQL 连接池和基础查询封装，提供 `mysql_connection()` 上下文管理器、`fetch_one()`、`fetch_all()` 和 `execute()` 方法
- **`logger.py`**：日志管理，支持按模块获取 logger，日志输出到 `logs/` 目录
- **`exceptions.py`**：自定义异常类 `AppError`、`ValidationError`、`FileProcessError` 等
- **`response.py`**：统一 API 响应格式 `{"code": 0, "message": "success", "data": {}, "trace_id": "..."}`
- **`trace.py`**：请求追踪 ID 管理，支持跨模块传递

#### 2. 爬虫模块（`src/crawlers/`）

采用 **掌上考研 V2 API 分块爬虫** 架构：

- **目标页面**：`https://www.kaoyan.cn/school-list/50-0-0`（重庆院校库）
- **实际请求**：调用 5 个公开接口（schoolList、planListV2、planDetailV2、schoolScore、schoolLevelRate）
- **数据范围**：近三年（2024-2026）重庆研招单位候选库、招生计划、专业详情、分数线、学科评估
- **输出格式**：
  - 5 个聚合 JSON 文件（原始响应）
  - 1 个 `crawl_summary.json`（运行摘要）
  - 1 个方向级大合集 CSV：`kaoyan_v2_integrated_<batch_id>.csv`（一行一个研究方向）
- **去重规则**：`(school_id, year, plan_id, research_area, exam_subject_clean)` 唯一

**运行爬虫**：

```bash
# 进入 Python 工具容器
docker exec -it zhitu-python bash
cd /workspace

# 运行统一爬虫
python -m src.crawlers.run_kaoyan_crawl --limit 20
```

#### 3. 数据处理模块（`src/data_pipeline/`）

- **`source_registry.py`**（S04）：候选库入库与来源登记
  - 优先读取 `school_list.json`，兜底读取大合集 CSV
  - 写入 `crawler_runs`（爬虫批次）、`universities`（候选招生单位）、`source_documents`（来源索引）
  - 支持幂等执行，重复运行时更新已有记录

**运行 S04**：

```bash
# 自动选择最新批次
python -m src.data_pipeline.source_registry

# 指定批次号
python -m src.data_pipeline.source_registry --batch-id 20260615_163000

# 仅校验不写库
python -m src.data_pipeline.source_registry --dry-run
```

#### 4. Flask 应用（`src/app.py`）

- **健康检查接口**：`GET /api/health`
- **统一异常处理**：`AppError` 返回 400，其他异常返回 500
- **请求追踪**：每个请求自动分配 `trace_id`，通过响应头 `X-Trace-Id` 返回

**运行 Flask**（开发模式）：

```bash
python -m src.app
```

### 数据库设计

#### 核心表结构

| 表名 | 说明 | 关键字段 |
|-----|------|---------|
| `crawler_runs` | 爬虫运行批次 | `id`, `crawler_name`, `batch_id`, `status`, `fetched_count` |
| `universities` | 招生单位（候选库） | `id`, `candidate_school_id`, `university_name`, `school_level`, `coverage_priority` |
| `source_documents` | 来源资料索引 | `id`, `university_id`, `year`, `document_type`, `source_url`, `local_path` |
| `departments` | 学院 | `id`, `university_id`, `department_name` |
| `majors` | 专业 | `id`, `university_id`, `department_id`, `major_code`, `major_name`, `research_direction` |
| `enrollment_plans` | 招生计划 | `id`, `year`, `major_id`, `plan_count`, `recommended_exemption_count` |
| `score_lines` | 复试分数线 | `id`, `year`, `line_type`, `university_id`, `major_id`, `total_score_line` |
| `admission_records` | 拟录取记录 | `id`, `year`, `major_id`, `initial_total_score`, `admission_status` |
| `major_statistics` | 专业统计结果（ADS） | `id`, `year`, `major_id`, `min_initial_score`, `avg_initial_score`, `heat_score` |
| `recommendation_logs` | 推荐日志 | `id`, `trace_id`, `request_json`, `result_summary_json` |
| `subject_level_rates` | 学科评估等级 | `id`, `university_id`, `subject_code`, `level_rate` |

#### 数据可追溯性设计

所有核心业务表（`departments`、`majors`、`enrollment_plans`、`score_lines`、`admission_records`）都包含 `source_id` 外键，关联到 `source_documents` 表，保证每条数据可追溯到原始文件或 API 来源。

#### 建表脚本

```bash
# 在 MySQL 容器中执行
docker exec -i zhitu-mysql mysql -uroot -proot123456 zhiyuan < sql/mysql/001_create_tables.sql
```

### 数据流转流程

1. **S03 爬虫**：`run_kaoyan_crawl.py` → 5 个聚合 JSON + 大合集 CSV
2. **S04 入库**：`source_registry.py` → `crawler_runs` + `universities` + `source_documents`
3. **数据清洗**：PDF/Excel 提取 → 人工校对 → 标准化
4. **MySQL 入库**：`departments`、`majors`、`enrollment_plans`、`score_lines`、`admission_records`
5. **HDFS/Hive 同步**：CSV → HDFS → Hive 分区表
6. **Spark 分析**：Hive 表 → Spark 统计分析 → `major_statistics`（ADS 表）
7. **Web 查询**：Flask 接口 → MySQL 查询 → ECharts 可视化
8. **推荐服务**：用户输入 → 推荐规则 → `recommendation_logs`
9. **AI 报告**：推荐结果 → 大模型 API → `report_records`

## 开发规范

### 代码风格

- **Python 版本**：要求 3.12+，使用 `from __future__ import annotations` 支持类型注解
- **类型注解**：公共函数和类方法应添加类型注解
- **文档字符串**：模块级别和重要函数应添加中文文档字符串
- **日志规范**：使用 `src.common.logger.get_logger(__name__)` 获取 logger，不要直接 print
- **异常处理**：业务异常使用 `AppError`，明确错误码和错误信息
- **SQL 规范**：
  - 使用参数化查询，不要拼接 SQL
  - 复杂查询放在 SQL 文件中，不要硬编码在 Python 代码里
  - 表名、字段名使用下划线命名法（`snake_case`）

### 文件编码与路径

- **编码要求**：所有 Python 文件读写必须显式指定 `encoding="utf-8"`
- **路径处理**：用户目录包含中文"杨林"，所有路径必须用双引号包裹，避免 PowerShell 解析错误
- **相对路径**：代码中使用 `PROJECT_ROOT`（`src/common/config.py` 定义）计算相对路径
- **数据目录**：优先放 D 盘（如 `D:\bigdatashixun\zhiyuan`），避免 C 盘中文路径问题

### Git 规范

- **提交说明**：用中文，包含变更原因、主要修改内容和验证情况
- **不提交内容**：`.env`、`.docker-data/`、`logs/`、`data/raw/`、`data/processed/`、`__pycache__/`
- **敏感信息**：不要在代码、配置、文档中暴露真实账号、密码、Token、API Key

### 测试与验证

- **环境检查**：修改 Docker 配置或数据库表结构后，运行 `check_dev_env.ps1` 验证
- **数据质量**：清洗脚本应输出统计报告（原始数量、有效数量、重复数量、异常数量）
- **接口测试**：推荐接口、图表接口应记录请求参数和响应结果到 `recommendation_logs`
- **单元测试**：核心业务逻辑（推荐规则、分数线评估）应有测试用例

## 常见任务

### 添加新的爬虫模块

1. 在 `src/crawlers/` 创建新的爬虫脚本
2. 继承 `kaoyan_v2_common.py` 的公共方法
3. 输出 JSON 到 `data/raw/kaoyan_v2/<batch_id>/` 对应子目录
4. 在 `run_kaoyan_crawl.py` 中注册新爬虫
5. 更新 `source_registry.py` 的 `document_type` 枚举

### 添加新的数据清洗脚本

1. 在 `src/data_pipeline/` 创建新脚本，例如 `clean_score_lines.py`
2. 读取 `source_documents` 表，过滤 `document_type` 和 `process_status`
3. 使用 Pandas 读取原始文件，执行清洗逻辑
4. 写入目标业务表（`score_lines`、`admission_records` 等）
5. 更新 `source_documents.process_status` 为 `'loaded'` 或 `'error'`
6. 记录异常数据到 `data_quality_issues` 表

### 添加新的 Flask 接口

1. 在 `src/app.py` 或新建 Blueprint 中添加路由
2. 使用 `@app.before_request` 自动注入 `trace_id`
3. 查询参数校验失败时抛出 `AppError`
4. 使用 `src.common.database` 的 `fetch_one()`、`fetch_all()` 执行查询
5. 返回 `jsonify(success_response(data))` 或 `jsonify(error_response(code, message))`
6. 推荐接口应记录请求到 `recommendation_logs`

### 添加新的 Spark 分析任务

1. 在 `src/spark/` 创建新脚本（目录暂未创建）
2. 读取 Hive 表：`spark.sql("SELECT * FROM zhiyuan.score_lines")`
3. 执行统计分析，使用 PySpark DataFrame API
4. 结果写回 MySQL ADS 表（`major_statistics`）或导出 CSV
5. 在 `check_dev_env.ps1` 中添加 Spark 作业检查

### 数据库表结构变更

1. 在 `sql/mysql/` 创建新的升级脚本，例如 `003_add_xxx_table.sql`
2. 使用 `ALTER TABLE` 或 `CREATE TABLE IF NOT EXISTS`
3. 在脚本开头添加注释说明变更原因和影响范围
4. 在 Docker 启动脚本中自动执行升级脚本（或手动执行）
5. 更新 `docx/详细设计文档.md` 中的表结构说明

## 重要注意事项

### 数据来源核验

- **第三方数据**：掌上考研 V2 API 数据只能作为候选库和参考，不能直接用于推荐结论
- **官网核验**：关键字段（学校名称、招生人数、复试线、拟录取名单）必须通过高校官网、研招网或考试院公开信息二次核验
- **核验状态**：`universities.official_verified_status` 和 `source_documents.official_verified` 字段标记核验状态
- **来源记录**：所有入库数据必须关联 `source_id`，保证可追溯

### 推荐系统边界

- **不承诺录取**：推荐结果仅供参考，页面和报告中不得出现"一定录取"、"保证上岸"等绝对化表达
- **风险提示**：推荐结果必须包含数据年份、数据不足、分数线波动、招生人数变化等风险提示
- **AI 报告限制**：大模型只能基于系统提供的数据生成报告，不能编造学校、专业或分数信息
- **降级策略**：大模型接口不可用时，使用模板生成基础报告

### 数据安全与隐私

- **敏感字段**：拟录取名单中的考生姓名、考生编号应脱敏或只做统计分析
- **密码管理**：不在代码仓库保存真实密码、Token、API Key，使用 `.env` 管理
- **日志脱敏**：日志中不输出完整密码、Token，只记录前后缀或 `***`

### 性能优化建议

- **批量插入**：使用 `executemany()` 或事务批量插入，避免逐条 INSERT
- **索引优化**：查询频繁的字段（`year`、`university_id`、`major_code`）应建索引
- **分页查询**：列表接口应支持 `limit` 和 `offset` 分页
- **缓存策略**：推荐规则、国家线等静态数据可缓存到 Redis

## 项目状态

### 已完成模块

- ✅ Docker 本地开发环境
- ✅ MySQL 表结构设计
- ✅ 掌上考研 V2 分块爬虫（S03）
- ✅ 候选库入库与来源登记（S04）
- ✅ Flask 基础框架和健康检查接口
- ✅ 公共模块（配置、数据库、日志、异常、响应）

### 待开发模块

- ⏳ PDF/Excel 数据提取脚本
- ⏳ 数据清洗与标准化脚本
- ⏳ HDFS/Hive 数据同步脚本
- ⏳ Spark 统计分析任务
- ⏳ 推荐规则实现与推荐接口
- ⏳ 图表数据接口（复试线趋势、招生人数变化）
- ⏳ AI 择校建议报告生成
- ⏳ 前端页面（查询、推荐、可视化）

### 当前工作重点

根据 `docx/开发步骤文档.md`，当前处于 **S04 阶段后期**，下一步：

1. 补充更多官网资料的 PDF/Excel 提取脚本
2. 实现 `departments`、`majors`、`enrollment_plans` 等业务表的入库逻辑
3. 开发推荐规则和推荐接口
4. 搭建前端页面框架

## 文档参考

- **需求文档**：`docx/需求文档.md` - 完整功能需求、数据范围、接口定义、验收标准
- **详细设计文档**：`docx/详细设计文档.md` - 表结构、推荐规则、接口设计
- **开发步骤文档**：`docx/开发步骤文档.md` - 按阶段拆分的开发任务
- **数据采集模块技术文档**：`docx/数据采集模块技术文档.md` - 爬虫架构和运行说明
- **项目文档**：`docx/项目文档.md` - 项目背景、目标、技术栈、小组分工

## 联系与协作

- **项目组成员**：大三学生四人小组
- **开发周期**：三周实训项目
- **答辩要求**：可运行、可演示、可追溯、文档完整
