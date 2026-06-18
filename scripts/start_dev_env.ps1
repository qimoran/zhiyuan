[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$SkipCheck,
    [switch]$SkipSparkJob
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $ProjectRoot ".env"
$EnvExamplePath = Join-Path $ProjectRoot ".env.example"
$ComposeProfiles = @("--profile", "hadoop", "--profile", "hive", "--profile", "spark", "--profile", "tools")
[Environment]::SetEnvironmentVariable("COMPOSE_IGNORE_ORPHANS", "true", "Process")

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Import-DotEnv {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $values
    }

    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $parts = $trimmed.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()

        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        $values[$key] = $value
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }

    return $values
}

function Get-EnvValue {
    param(
        [hashtable]$Values,
        [string]$Name,
        [string]$Default
    )

    if ($Values.ContainsKey($Name) -and -not [string]::IsNullOrWhiteSpace($Values[$Name])) {
        return $Values[$Name]
    }

    return $Default
}

function Test-DockerImage {
    param([string]$Image)

    & docker image inspect $Image *> $null
    return $LASTEXITCODE -eq 0
}

function Invoke-Compose {
    param([string[]]$Arguments)

    $dockerArgs = @("compose") + $ComposeProfiles + $Arguments
    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose 命令执行失败：docker $($dockerArgs -join ' ')"
    }
}

function Wait-MysqlReady {
    param([string]$RootPassword)

    for ($i = 1; $i -le 40; $i++) {
        $dockerArgs = @("compose") + $ComposeProfiles + @(
            "exec", "-T", "-e", "MYSQL_PWD=$RootPassword", "mysql",
            "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "--silent"
        )
        & docker @dockerArgs *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 3
    }

    throw "MySQL 在等待时间内没有变为可用状态。"
}

function Initialize-ProjectDatabase {
    param(
        [string]$RootPassword,
        [string]$DatabaseName,
        [string]$UserName,
        [string]$Password
    )

    foreach ($identifier in @($DatabaseName, $UserName)) {
        if ($identifier -notmatch "^[A-Za-z0-9_]+$") {
            throw "数据库名和用户名只能包含字母、数字和下划线：$identifier"
        }
    }

    $escapedPassword = $Password.Replace("'", "''")
    $sql = @"
CREATE DATABASE IF NOT EXISTS ``$DatabaseName`` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$UserName'@'%' IDENTIFIED BY '$escapedPassword';
ALTER USER '$UserName'@'%' IDENTIFIED BY '$escapedPassword';
GRANT ALL PRIVILEGES ON ``$DatabaseName``.* TO '$UserName'@'%';
FLUSH PRIVILEGES;
"@

    $dockerArgs = @("compose") + $ComposeProfiles + @(
        "exec", "-T", "-e", "MYSQL_PWD=$RootPassword", "mysql",
        "mysql", "-uroot", "-e", $sql
    )
    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "初始化项目数据库失败。"
    }
}

function Test-LocalTcp {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds = 2
    )

    try {
        $socket = New-Object System.Net.Sockets.TcpClient
        $socket.SendTimeout = $TimeoutSeconds * 1000
        $socket.ReceiveTimeout = $TimeoutSeconds * 1000
        $socket.Connect($HostName, $Port)
        $socket.Close()
        return $true
    } catch {
        return $false
    }
}

function Wait-ServicePorts {
    param(
        [array]$Services,
        [int]$TimeoutSeconds = 240
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $pending = @($Services)

    while ($pending.Count -gt 0 -and (Get-Date) -lt $deadline) {
        $nextPending = @()
        foreach ($service in $pending) {
            # 优先测试本地端口（通过 127.0.0.1），容器间通信易出现 DNS 问题
            $testPort = $service.Port
            if ($service.ContainsKey("LocalPort") -and $service["LocalPort"]) {
                $testPort = $service["LocalPort"]
            }
            if (Test-LocalTcp -HostName "127.0.0.1" -Port $testPort) {
                Write-Host "[OK]   $($service.Name): 127.0.0.1:$testPort"
            } else {
                $nextPending += $service
            }
        }

        if ($nextPending.Count -eq 0) {
            return
        }

        $names = ($nextPending | ForEach-Object { $_.Name }) -join ", "
        Write-Host "等待服务就绪：$names"
        Start-Sleep -Seconds 5
        $pending = $nextPending
    }

    $remaining = ($pending | ForEach-Object { "$($_.Name)(port $($_.Port))" }) -join ", "
    throw "等待服务就绪超时：$remaining"
}

Set-Location -LiteralPath $ProjectRoot

Write-Step "检查 Docker"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "没有找到 docker 命令。请先安装并启动 Docker Desktop。"
}
& docker version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker daemon 未连接。请先启动 Docker Desktop。"
}

if (-not (Test-Path -LiteralPath $EnvPath)) {
    if (-not (Test-Path -LiteralPath $EnvExamplePath)) {
        throw "缺少 .env.example，无法生成本地 .env。"
    }
    Copy-Item -LiteralPath $EnvExamplePath -Destination $EnvPath
    Write-Host "已根据 .env.example 生成本地 .env。"
}

$envValues = Import-DotEnv -Path $EnvPath
$imagePrefix = Get-EnvValue -Values $envValues -Name "IMAGE_PREFIX" -Default "zhitu"
$mysqlRootPassword = Get-EnvValue -Values $envValues -Name "MYSQL_ROOT_PASSWORD" -Default "root123456"
$databaseName = Get-EnvValue -Values $envValues -Name "ZHIYUAN_DB_NAME" -Default "zhiyuan"
$databaseUser = Get-EnvValue -Values $envValues -Name "ZHIYUAN_DB_USER" -Default "zhiyuan_app"
$databasePassword = Get-EnvValue -Values $envValues -Name "ZHIYUAN_DB_PASSWORD" -Default "zhiyuan123456"

$requiredImages = @(
    "$imagePrefix/hadoop:3.3.6-java8",
    "$imagePrefix/hive:4.0.1-java8",
    "$imagePrefix/spark:3.5.1-java8-python3",
    "$imagePrefix/python-bigdata:3.12"
)

$missingImages = @()
foreach ($image in $requiredImages) {
    if (-not (Test-DockerImage -Image $image)) {
        $missingImages += $image
    }
}

if ($missingImages.Count -gt 0) {
    $Build = $true
    Write-Host "缺少以下本地镜像，将执行 Docker build：" -ForegroundColor Yellow
    $missingImages | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "首次构建会下载 Hadoop、Hive、Spark 等依赖，体积较大，网络较慢时需要较长时间。" -ForegroundColor Yellow
}

Write-Step "启动 Docker 大数据环境"
$runningServices = @()
try {
    $runningServices = & docker @(@("compose") + $ComposeProfiles + @("ps", "--services", "--status", "running"))
} catch {
    $runningServices = @()
}

$requiredServices = @(
    "mysql", "redis", "namenode", "datanode", "resourcemanager", "nodemanager",
    "hive-metastore", "hiveserver2", "spark-master", "spark-worker", "python"
)
$allServicesRunning = $true
foreach ($service in $requiredServices) {
    if ($runningServices -notcontains $service) {
        $allServicesRunning = $false
        break
    }
}

if ($allServicesRunning -and -not $Build) {
    Write-Host "检测到完整大数据环境已在运行，仅重建 python 工具容器以挂载当前项目目录。"
    Invoke-Compose -Arguments @("up", "-d", "--no-build", "--no-deps", "--force-recreate", "python")
} else {
    $upArgs = @("up", "-d")
    if ($Build) {
        $upArgs += "--build"
    } else {
        $upArgs += "--no-build"
    }
    Invoke-Compose -Arguments $upArgs
}

Write-Step "初始化志愿填报项目数据库"
Wait-MysqlReady -RootPassword $mysqlRootPassword
Initialize-ProjectDatabase `
    -RootPassword $mysqlRootPassword `
    -DatabaseName $databaseName `
    -UserName $databaseUser `
    -Password $databasePassword

Write-Step "等待大数据服务就绪"
Wait-ServicePorts -Services @(
    @{
        Name = "MySQL"
        Host = "mysql"
        Port = 3306
        LocalPort = [int](Get-EnvValue -Values $envValues -Name "MYSQL_PORT" -Default "13306")
    },
    @{
        Name = "Redis"
        Host = "redis"
        Port = 6379
        LocalPort = [int](Get-EnvValue -Values $envValues -Name "REDIS_PORT" -Default "16379")
    }
) -TimeoutSeconds 60

# 大数据服务需要更长的启动时间，特别是 HiveServer2，这里仅输出提示信息
Write-Host "等待大数据服务就绪：HDFS NameNode, YARN, Hive, Spark"
Write-Host "（后续访问时会自动重试，可暂时忽略连接错误）"
Start-Sleep -Seconds 15

Write-Step "当前容器状态"
Invoke-Compose -Arguments @("ps")

if (-not $SkipCheck) {
    $checkScript = Join-Path $PSScriptRoot "check_dev_env.ps1"
    if (-not $SkipSparkJob) {
        & $checkScript -SparkJob
    } else {
        & $checkScript
    }
}

Write-Host ""
Write-Host "Docker 开发环境已准备完成。" -ForegroundColor Green
Write-Host "常用地址："
Write-Host "  MySQL: 127.0.0.1:$((Get-EnvValue -Values $envValues -Name 'MYSQL_PORT' -Default '13306'))"
Write-Host "  Redis: 127.0.0.1:$((Get-EnvValue -Values $envValues -Name 'REDIS_PORT' -Default '16379'))"
Write-Host "  HDFS:  http://127.0.0.1:$((Get-EnvValue -Values $envValues -Name 'HDFS_NAMENODE_WEB_PORT' -Default '9870'))"
Write-Host "  YARN:  http://127.0.0.1:$((Get-EnvValue -Values $envValues -Name 'YARN_RESOURCEMANAGER_WEB_PORT' -Default '8088'))"
Write-Host "  Spark: http://127.0.0.1:$((Get-EnvValue -Values $envValues -Name 'SPARK_MASTER_WEB_PORT' -Default '18080'))"
