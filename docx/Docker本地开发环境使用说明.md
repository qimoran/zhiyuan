# Docker 本地开发环境使用说明

## 1. 适用场景

本说明用于志愿填报数据分析系统的本地开发环境搭建。项目已经内置 Docker Compose 配置和 PowerShell 脚本，开发同学从 GitHub 拉取项目后，可以通过一个启动脚本在本机 Docker Desktop 中启动 MySQL、Redis、Hadoop、Hive、Spark 和 Python 工具容器。

## 2. 前置条件

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10/11 |
| Docker | 已安装并启动 Docker Desktop |
| 终端 | Windows PowerShell |
| 网络 | 首次构建镜像时需要能访问 Docker Hub、Apache Archive、Maven Central |

首次在新电脑运行时，如果本地没有大数据镜像，脚本会自动执行 Docker build。构建过程会下载 Hadoop、Hive、Spark 等依赖，体积较大，耗时取决于网络速度。

## 3. 一键启动

进入项目根目录后执行：

```powershell
cd "D:\bigdatashixun\zhiyuan"
powershell -ExecutionPolicy Bypass -File ".\scripts\start_dev_env.ps1"
```

脚本会自动完成以下工作：

1. 检查 Docker Desktop 是否可用。
2. 如果缺少 `.env`，根据 `.env.example` 生成本地环境配置。
3. 检查 Hadoop、Hive、Spark、Python 大数据镜像是否存在。
4. 缺少镜像时自动构建镜像。
5. 启动 MySQL、Redis、Hadoop、Hive、Spark、Python 容器。
6. 创建 `zhiyuan` 数据库和 `zhiyuan_app` 开发用户。
7. 执行服务连通性检查。

## 4. 常用命令

### 4.1 检查环境

普通检查：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\check_dev_env.ps1"
```

带 Spark 小作业检查：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\check_dev_env.ps1" -SparkJob
```

### 4.2 停止环境

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\stop_dev_env.ps1"
```

该命令只停止容器，不删除 MySQL、Redis、HDFS、Spark 数据。

### 4.3 启动但跳过检查

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\start_dev_env.ps1" -SkipCheck
```

## 5. 服务地址

| 服务 | Windows 访问地址 | 容器内部地址 |
| --- | --- | --- |
| MySQL | `127.0.0.1:13306` | `mysql:3306` |
| Redis | `127.0.0.1:16379` | `redis:6379` |
| HDFS NameNode | `http://127.0.0.1:9870` | `namenode:9870` |
| YARN ResourceManager | `http://127.0.0.1:8088` | `resourcemanager:8088` |
| HiveServer2 JDBC | `127.0.0.1:10000` | `hiveserver2:10000` |
| HiveServer2 Web | `http://127.0.0.1:10002` | `hiveserver2:10002` |
| Spark Master | `http://127.0.0.1:18080` | `spark-master:8080` |
| Spark Worker | `http://127.0.0.1:18081` | `spark-worker:8081` |

## 6. 数据库默认配置

| 项目 | 默认值 |
| --- | --- |
| MySQL root 密码 | `root123456` |
| 业务库 | `zhiyuan` |
| 业务用户 | `zhiyuan_app` |
| 业务用户密码 | `zhiyuan123456` |
| Hive 元数据库 | `hive_metastore` |
| Hive 用户 | `hive` |
| Hive 用户密码 | `hive123456` |

这些默认值只用于本地开发和课程实训，不用于真实生产环境。

## 7. 文件说明

| 文件或目录 | 说明 |
| --- | --- |
| `docker-compose.yml` | Docker Compose 主配置 |
| `.env.example` | 可提交到 GitHub 的环境变量模板 |
| `.env` | 本机私有配置，不提交 GitHub |
| `docker/build-context/` | Hadoop、Hive、Spark、Python 镜像构建上下文 |
| `docker/mysql/init/01-create-databases.sql` | MySQL 首次初始化脚本 |
| `scripts/start_dev_env.ps1` | 一键启动和初始化脚本 |
| `scripts/check_dev_env.ps1` | 环境检查脚本 |
| `scripts/stop_dev_env.ps1` | 停止环境脚本 |
| `scripts/check_bigdata_connections.py` | 容器内部服务连通性检查脚本 |

## 8. 本机已验证结果

当前电脑已完成验证：

| 检查项 | 结果 |
| --- | --- |
| Docker Desktop | 可用 |
| Docker 数据目录 D 盘映射 | 已确认 |
| MySQL | 可访问，`zhiyuan` 数据库已创建 |
| Redis | 可访问 |
| HDFS | 可访问 |
| HiveServer2 | 可访问 |
| Spark | 可访问 |
| Python 工具容器 | `/workspace` 已挂载到 `D:\bigdatashixun\zhiyuan` |
| 普通连通性检查 | `15/15 checks passed` |
| Spark 作业检查 | `16/16 checks passed` |

## 9. 注意事项

1. 运行脚本前先启动 Docker Desktop。
2. 不要提交 `.env`、`.docker-data`、日志文件和本地数据库数据。
3. 不要执行 `docker compose down -v`，避免误删数据。
4. 如果端口被占用，修改 `.env` 中对应端口后重新启动。
5. 如果首次构建镜像下载很慢，可以配置当前终端代理后重新运行启动脚本。
6. 本机保留了兼容旧大数据环境的 `zhitu` 镜像名和容器名前缀，不影响志愿填报项目开发。
