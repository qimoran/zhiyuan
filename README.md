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
7. 执行环境连通性检查。

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

## 注意事项

1. 运行前先启动 Docker Desktop。
2. 不要把 `.env`、`.docker-data`、日志文件提交到 GitHub。
3. 不要执行 `docker compose down -v`，避免误删本地数据。
4. 如果端口被占用，修改 `.env` 中对应端口后重新运行启动脚本。
