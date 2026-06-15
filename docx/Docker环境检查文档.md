# Docker 环境检查文档

## 1. 文档说明

| 项目 | 内容 |
| --- | --- |
| 检查对象 | `D:\bigdatashixun\project-main` 中已有 Docker 大数据环境，以及其对 `D:\bigdatashixun\zhiyuan` 项目的可复用情况 |
| 检查时间 | 2026-06-15 12:09:59 |
| 检查目的 | 确认 Docker 是否真正可用、是否做了 D 盘映射、现有环境是否能支撑志愿填报项目后续开发 |
| 检查范围 | Docker Desktop、Docker Compose、MySQL、Redis、Hadoop、Hive、Spark、Python 工具容器、宿主机端口、项目目录挂载 |

本次检查只做环境读取、启动和连通性验证，没有执行 Git 提交、推送，也没有删除容器、镜像或数据卷。

## 2. 总体结论

当前 Docker 环境可用，并且确实使用了 D 盘映射。

1. Docker Desktop 程序安装在用户目录：
   - `C:\Users\杨林\AppData\Local\Programs\DockerDesktop`
2. Docker Desktop 的 WSL 数据目录已经映射到 D 盘：
   - `C:\Users\杨林\AppData\Local\Docker\wsl`
   - 映射目标：`D:\docker\desktop-wsl`
   - 类型：`Junction`
3. `project-main` 的大数据服务数据也映射在 D 盘：
   - 默认数据根目录：`D:\docker\bigdata\data`
4. 当前大数据环境已经正常启动，MySQL、Redis、Hadoop、Hive、Spark、Python 工具容器均可用。
5. 与志愿填报项目相关的主要问题是：当前 `python` 工具容器只挂载了 `D:\bigdatashixun\project-main` 到 `/workspace`，还没有直接挂载 `D:\bigdatashixun\zhiyuan`。
6. 后续建议不要重装 Docker，也不要重建已有大数据镜像；只需要补充当前项目目录挂载、独立数据库和项目运行配置。

## 3. Docker 基础环境检查

### 3.1 Docker 版本

| 项目 | 检查结果 |
| --- | --- |
| Docker Client | 29.5.3 |
| Docker Server | Docker Desktop 4.77.0 |
| Docker Engine | 29.5.3 |
| Docker Compose | v5.1.4 |
| 当前 context | `desktop-linux` |
| Docker daemon | 正常连接 |

Docker 命令来源：

| 命令 | 路径 |
| --- | --- |
| `docker.exe` | `C:\Users\杨林\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe` |
| `docker-compose.exe` | `C:\Users\杨林\AppData\Local\Programs\DockerDesktop\resources\bin\docker-compose.exe` |

### 3.2 D 盘映射确认

Docker Desktop 的 WSL 数据目录检查结果：

| 项目 | 内容 |
| --- | --- |
| 原路径 | `C:\Users\杨林\AppData\Local\Docker\wsl` |
| 实际目标 | `D:\docker\desktop-wsl` |
| 类型 | Junction |
| 结论 | Docker Desktop 的 WSL 数据已经迁移到 D 盘 |

`D:\docker` 当前目录包含：

| 目录 | 说明 |
| --- | --- |
| `D:\docker\desktop-wsl` | Docker Desktop WSL 后端数据 |
| `D:\docker\bigdata` | 大数据服务的数据目录 |
| `D:\docker\Docker` | 其他 Docker 相关目录 |
| `D:\docker\installers` | 安装包目录 |

`D:\docker\bigdata\data` 当前包含：

| 目录 | 说明 |
| --- | --- |
| `mysql` | MySQL 数据 |
| `redis` | Redis 数据 |
| `hdfs` | HDFS NameNode/DataNode 数据 |
| `hadoop-tmp` | Hadoop 临时数据 |
| `spark-events` | Spark 事件日志 |

## 4. Compose 项目检查

### 4.1 Compose 文件位置

当前大数据环境的 compose 文件位于：

```powershell
"D:\bigdatashixun\project-main\docker-compose.yml"
```

当前项目目录为：

```powershell
"D:\bigdatashixun\zhiyuan"
```

这两个目录不是同一个项目目录。也就是说，Docker 环境已经在 `project-main` 中配置好，但志愿填报项目代码在 `zhiyuan` 中，后续开发需要处理目录挂载关系。

### 4.2 Compose 服务与 profile

默认情况下，只启动无 profile 的基础服务：

| 默认服务 | 说明 |
| --- | --- |
| `mysql` | MySQL 8.0.39 |
| `redis` | Redis 5.0.14 |

完整大数据环境需要指定 profile：

```powershell
cd "D:\bigdatashixun\project-main"
docker compose --profile hadoop --profile hive --profile spark --profile tools up -d --no-build
```

完整服务包括：

| 服务 | 说明 |
| --- | --- |
| `mysql` | MySQL 数据库 |
| `redis` | Redis 缓存 |
| `python` | Python 3.12 工具容器 |
| `namenode` | Hadoop NameNode |
| `datanode` | Hadoop DataNode |
| `resourcemanager` | YARN ResourceManager |
| `nodemanager` | YARN NodeManager |
| `hive-metastore` | Hive Metastore |
| `hiveserver2` | HiveServer2 |
| `spark-master` | Spark Master |
| `spark-worker` | Spark Worker |

### 4.3 关键卷映射

`docker-compose.yml` 中的主要映射关系如下：

| 服务 | 宿主机路径 | 容器路径 | 用途 |
| --- | --- | --- | --- |
| MySQL | `D:\docker\bigdata\data\mysql` | `/var/lib/mysql` | MySQL 数据持久化 |
| Redis | `D:\docker\bigdata\data\redis` | `/data` | Redis 数据持久化 |
| Hadoop NameNode | `D:\docker\bigdata\data\hdfs\namenode` | `/hadoop/dfs/name` | HDFS 元数据 |
| Hadoop DataNode | `D:\docker\bigdata\data\hdfs\datanode` | `/hadoop/dfs/data` | HDFS 数据块 |
| Spark | `D:\docker\bigdata\data\spark-events` | `/spark-events` | Spark 事件日志 |
| Python 工具容器 | `D:\bigdatashixun\project-main` | `/workspace` | 当前工具容器工作目录 |
| Python 工具容器 | `D:\docker\bigdata\data` | `/data` | 访问大数据数据目录 |

需要注意：当前 `D:\bigdatashixun\zhiyuan` 没有挂载到 `python` 工具容器内。

## 5. 当前容器运行状态

| 容器 | 镜像 | 状态 | 端口 |
| --- | --- | --- | --- |
| `zhitu-mysql` | `mysql:8.0.39` | Up healthy | `13306 -> 3306` |
| `zhitu-redis` | `redis:5.0.14` | Up healthy | `16379 -> 6379` |
| `zhitu-hadoop-namenode` | `zhitu/hadoop:3.3.6-java8` | Up | `9000`, `9870` |
| `zhitu-hadoop-datanode` | `zhitu/hadoop:3.3.6-java8` | Up | `9864` |
| `zhitu-yarn-resourcemanager` | `zhitu/hadoop:3.3.6-java8` | Up | `8088` |
| `zhitu-yarn-nodemanager` | `zhitu/hadoop:3.3.6-java8` | Up | `8042` |
| `zhitu-hive-metastore` | `zhitu/hive:4.0.1-java8` | Up | `9083` |
| `zhitu-hiveserver2` | `zhitu/hive:4.0.1-java8` | Up | `10000`, `10002` |
| `zhitu-spark-master` | `zhitu/spark:3.5.1-java8-python3` | Up | `7077`, `18080 -> 8080` |
| `zhitu-spark-worker` | `zhitu/spark:3.5.1-java8-python3` | Up | `18081 -> 8081` |
| `zhitu-python` | `zhitu/python-bigdata:3.12` | Up | 无对外端口 |

额外发现一个历史容器：

| 容器 | 状态 | 处理建议 |
| --- | --- | --- |
| `zhitu-agent-web` | `Exited (137)` | 当前不影响大数据环境，不建议在未确认用途前删除 |

## 6. 服务连通性检查

### 6.1 容器内部连通性

执行检查：

```powershell
cd "D:\bigdatashixun\project-main"
docker compose exec -T python python src/python/check_bigdata_connections.py
```

结果：

| 检查项 | 结果 |
| --- | --- |
| MySQL TCP | 通过 |
| MySQL 数据库访问 | 通过 |
| Redis TCP | 通过 |
| Redis PING | 通过 |
| HDFS NameNode RPC | 通过 |
| HDFS NameNode Web | 通过 |
| HDFS WebHDFS | 通过 |
| YARN ResourceManager Web | 通过 |
| Hive Metastore TCP | 通过 |
| HiveServer2 JDBC TCP | 通过 |
| HiveServer2 Web TCP | 通过 |
| Spark Master TCP | 通过 |
| Spark Master Web | 通过 |
| Spark Worker Web | 通过 |

结论：`14/14 checks passed`。

### 6.2 Spark 作业检查

执行检查：

```powershell
cd "D:\bigdatashixun\project-main"
docker compose exec -T python python src/python/check_bigdata_connections.py --spark-job
```

结果：

| 检查项 | 结果 |
| --- | --- |
| 基础服务检查 | 14 项全部通过 |
| Spark range count 作业 | 通过 |

结论：`15/15 checks passed`。

检查过程中出现两个非阻塞警告：

| 警告 | 影响 | 处理建议 |
| --- | --- | --- |
| `ps: command not found` | Spark 启动脚本尝试调用 `ps`，但当前镜像未安装该命令；本次作业仍成功 | 当前可不处理，后续如要优化镜像，可安装 `procps` |
| `Unable to load native-hadoop library` | 常见 Hadoop 本地库警告，Spark 使用 Java 内置实现继续运行 | 当前不影响课程项目开发 |

### 6.3 Windows 宿主机端口检查

| 服务 | Windows 访问地址 | 状态 |
| --- | --- | --- |
| MySQL | `127.0.0.1:13306` | 可访问 |
| Redis | `127.0.0.1:16379` | 可访问 |
| HDFS NameNode UI | `http://127.0.0.1:9870` | 可访问 |
| YARN ResourceManager UI | `http://127.0.0.1:8088` | 可访问 |
| HiveServer2 JDBC | `127.0.0.1:10000` | 可访问 |
| HiveServer2 Web | `http://127.0.0.1:10002` | 可访问 |
| Spark Master UI | `http://127.0.0.1:18080` | 可访问 |
| Spark Worker UI | `http://127.0.0.1:18081` | 可访问 |

### 6.4 应用开发端口检查

| 端口 | 状态 | 建议 |
| --- | --- | --- |
| `5000` | 空闲 | Flask 后端可优先使用 |
| `8000` | 已占用 | 被 `D:\miniconda\python.exe` 进程占用，如使用 FastAPI 需换端口或释放端口 |
| `8080` | 空闲 | 可作为备用后端端口 |
| `5173` | 空闲 | 可作为前端 Vite 端口 |

## 7. MySQL 与 Redis 当前状态

### 7.1 MySQL

当前已有数据库：

| 数据库 |
| --- |
| `hive_metastore` |
| `mysql` |
| `performance_schema` |
| `sys` |
| `zhitu` |

当前已有业务用户：

| 用户 | Host |
| --- | --- |
| `root` | `%`、`localhost` |
| `hive` | `%` |
| `zhitu` | `%` |

当前没有发现 `zhiyuan` 业务库和 `zhiyuan_app` 业务用户。

建议后续为志愿填报项目单独建立数据库和用户，避免继续混用 `zhitu` 项目的业务库。

示例命令如下，正式执行前建议把密码换成项目 `.env` 中的本地开发密码：

```powershell
cd "D:\bigdatashixun\project-main"
docker compose exec -T mysql mysql -uroot -proot123456 -e "CREATE DATABASE IF NOT EXISTS zhiyuan DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER IF NOT EXISTS 'zhiyuan_app'@'%' IDENTIFIED BY '请替换为本地开发密码'; GRANT ALL PRIVILEGES ON zhiyuan.* TO 'zhiyuan_app'@'%'; FLUSH PRIVILEGES;"
```

### 7.2 Redis

Redis 当前可用，容器内部访问地址和 Windows 访问地址如下：

| 使用位置 | Host | Port |
| --- | --- | --- |
| Windows 宿主机 | `127.0.0.1` | `16379` |
| Docker 容器内部 | `redis` | `6379` |

## 8. 志愿填报项目需要的额外配置

### 8.1 需要补充当前项目目录挂载

当前 `zhitu-python` 容器挂载情况：

| 宿主机路径 | 容器路径 |
| --- | --- |
| `D:\bigdatashixun\project-main` | `/workspace` |
| `D:\docker\bigdata\data` | `/data` |

如果后续要在 `python` 工具容器里直接运行 `zhiyuan` 项目代码，建议在 `D:\bigdatashixun\project-main` 下新增 `docker-compose.override.yml`，只增加挂载，不改原有服务逻辑：

```yaml
services:
  python:
    volumes:
      - ./:/workspace
      - ${BIGDATA_DOCKER_DATA:-D:/docker/bigdata/data}:/data
      - D:/bigdatashixun/zhiyuan:/workspace/zhiyuan
```

新增后重建 `python` 容器：

```powershell
cd "D:\bigdatashixun\project-main"
docker compose --profile hadoop --profile hive --profile spark --profile tools up -d --no-build --force-recreate python
```

验证挂载：

```powershell
cd "D:\bigdatashixun\project-main"
docker compose exec -T -w /workspace/zhiyuan python python -c "import os; print(os.getcwd()); print(os.listdir('.'))"
```

### 8.2 建议补充项目环境变量

建议在 `D:\bigdatashixun\zhiyuan` 中使用 `.env.example` 记录示例配置，不在文档和代码中写真实密码。

Windows 本机运行 Python 后端时：

```env
APP_ENV=dev
MYSQL_HOST=127.0.0.1
MYSQL_PORT=13306
MYSQL_DATABASE=zhiyuan
MYSQL_USER=zhiyuan_app
MYSQL_PASSWORD=请替换为本地开发密码
REDIS_HOST=127.0.0.1
REDIS_PORT=16379
HDFS_URI=hdfs://127.0.0.1:9000
HIVE_HOST=127.0.0.1
HIVE_PORT=10000
SPARK_MASTER=spark://127.0.0.1:7077
```

在 Docker 容器内部运行项目代码时：

```env
APP_ENV=dev
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=zhiyuan
MYSQL_USER=zhiyuan_app
MYSQL_PASSWORD=请替换为本地开发密码
REDIS_HOST=redis
REDIS_PORT=6379
HDFS_URI=hdfs://namenode:9000
HIVE_HOST=hiveserver2
HIVE_PORT=10000
SPARK_MASTER=spark://spark-master:7077
```

### 8.3 建议保留现有大数据环境，不直接重命名

虽然当前容器、数据库和镜像名称都带有 `zhitu`，但这套环境可以继续作为本机大数据底座使用。后续志愿填报项目只需要新增自己的数据库、配置文件、表结构和项目挂载。

不建议现在直接把 `zhitu-*` 容器、镜像、数据库全部改名，原因如下：

1. 现有环境已经验证可用，直接重命名可能引入新的启动和网络问题。
2. Hadoop、Hive、Spark 镜像体积较大，重建成本高。
3. 课程开发重点应放在志愿填报项目业务功能、数据处理和可视化上。
4. 通过独立数据库和项目配置即可隔离两个项目，不需要破坏原环境。

## 9. 后续启动与检查命令

### 9.1 启动完整环境

```powershell
cd "D:\bigdatashixun\project-main"
docker compose --profile hadoop --profile hive --profile spark --profile tools up -d --no-build
```

### 9.2 查看容器状态

```powershell
cd "D:\bigdatashixun\project-main"
docker compose ps
```

### 9.3 检查基础连通性

```powershell
cd "D:\bigdatashixun\project-main"
docker compose exec -T python python src/python/check_bigdata_connections.py
```

### 9.4 检查 Spark 作业

```powershell
cd "D:\bigdatashixun\project-main"
docker compose exec -T python python src/python/check_bigdata_connections.py --spark-job
```

### 9.5 访问 Web 页面

| 页面 | 地址 |
| --- | --- |
| HDFS NameNode | `http://127.0.0.1:9870` |
| YARN ResourceManager | `http://127.0.0.1:8088` |
| HiveServer2 Web | `http://127.0.0.1:10002` |
| Spark Master | `http://127.0.0.1:18080` |
| Spark Worker | `http://127.0.0.1:18081` |

### 9.6 停止环境

只停止容器，不删除数据：

```powershell
cd "D:\bigdatashixun\project-main"
docker compose --profile hadoop --profile hive --profile spark --profile tools down
```

不要随意执行下面这种命令：

```powershell
docker compose down -v
```

`-v` 会删除 volume。虽然当前主要数据使用了 D 盘目录映射，但养成不随便删卷的习惯更安全。

## 10. 风险点与处理建议

| 风险点 | 当前状态 | 影响 | 建议 |
| --- | --- | --- | --- |
| `zhiyuan` 项目未挂载到工具容器 | 存在 | 容器内不能直接运行当前项目代码 | 添加 `docker-compose.override.yml` 挂载当前项目 |
| 当前只有 `zhitu` 业务库和用户 | 存在 | 志愿填报项目与旧项目数据混用 | 新建 `zhiyuan` 库和业务用户 |
| `project-main` 没有 `.env` | 存在 | 当前依赖 compose 默认值，可运行但不够规范 | 后续补 `.env.example` 和本机 `.env` |
| 构建资源包不完整 | 需要注意 | 如果换电脑重建镜像，可能缺 Hadoop/Hive/Spark 安装包 | 当前已有镜像不需要重建；迁移时带上安装包或镜像 |
| 端口 `8000` 被占用 | 存在 | FastAPI 默认端口可能冲突 | Flask 用 `5000`，或将后端端口改为 `5001/8080` |
| Spark 有非阻塞警告 | 存在 | 不影响当前作业 | 暂不处理，后续优化镜像时再解决 |
| 历史容器 `zhitu-agent-web` 已退出 | 存在 | 当前无影响 | 不确认用途前不删除 |

## 11. 结论

本机 Docker 环境已经配置完成，并且确实采用了 D 盘映射。`project-main` 中的大数据服务可以作为志愿填报项目的开发底座继续使用，不需要重新安装 Docker，也不需要重新构建 Hadoop、Hive、Spark 镜像。

后续真正需要补充的是三件事：

1. 给 `python` 工具容器增加 `D:\bigdatashixun\zhiyuan` 的目录挂载。
2. 为志愿填报项目创建独立的 MySQL 数据库和业务用户。
3. 在 `zhiyuan` 项目中补充 `.env.example`、本地 `.env`、数据库初始化 SQL 和运行说明。

完成以上配置后，就可以在现有 Docker 大数据环境上继续开发志愿填报系统。
