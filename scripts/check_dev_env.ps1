[CmdletBinding()]
param(
    [switch]$SparkJob
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $ProjectRoot ".env"
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

function Invoke-Compose {
    param([string[]]$Arguments)

    $dockerArgs = @("compose") + $ComposeProfiles + $Arguments
    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose 命令执行失败：docker $($dockerArgs -join ' ')"
    }
}

function Test-LocalPort {
    param([int]$Port, [int]$TimeoutMs = 2000)
    try {
        $socket = New-Object System.Net.Sockets.TcpClient
        $socket.SendTimeout = $TimeoutMs
        $socket.ReceiveTimeout = $TimeoutMs
        $socket.Connect("127.0.0.1", $Port)
        $socket.Close()
        return $true
    } catch {
        return $false
    }
}

Set-Location -LiteralPath $ProjectRoot
$envValues = Import-DotEnv -Path $EnvPath

Write-Step "检查宿主机端口"
$ports = @(
    @{ Name = "MySQL"; Port = [int](Get-EnvValue -Values $envValues -Name "MYSQL_PORT" -Default "13306") },
    @{ Name = "Redis"; Port = [int](Get-EnvValue -Values $envValues -Name "REDIS_PORT" -Default "16379") },
    @{ Name = "HDFS NameNode Web"; Port = [int](Get-EnvValue -Values $envValues -Name "HDFS_NAMENODE_WEB_PORT" -Default "9870") },
    @{ Name = "YARN ResourceManager Web"; Port = [int](Get-EnvValue -Values $envValues -Name "YARN_RESOURCEMANAGER_WEB_PORT" -Default "8088") },
    @{ Name = "HiveServer2 JDBC"; Port = [int](Get-EnvValue -Values $envValues -Name "HIVE_SERVER2_PORT" -Default "10000") },
    @{ Name = "Spark Master Web"; Port = [int](Get-EnvValue -Values $envValues -Name "SPARK_MASTER_WEB_PORT" -Default "18080") }
)

$failed = @()
foreach ($item in $ports) {
    if (Test-LocalPort -Port $item.Port) {
        Write-Host "[OK]   $($item.Name): 127.0.0.1:$($item.Port)"
    } else {
        Write-Host "[FAIL] $($item.Name): 127.0.0.1:$($item.Port)" -ForegroundColor Yellow
        $failed += $item.Name
    }
}

if ($failed.Count -gt 0) {
    Write-Host "注意：以下端口不可访问，可能是大数据服务启动较慢，稍后会自动就绪：$($failed -join ', ')" -ForegroundColor Yellow
}

Write-Step "检查容器状态"
Invoke-Compose -Arguments @("ps")

Write-Step "检查容器内部服务连通性"
$pythonArgs = @("python", "scripts/check_bigdata_connections.py")
if ($SparkJob) {
    $pythonArgs += "--spark-job"
}
Invoke-Compose -Arguments (@("exec", "-T", "python") + $pythonArgs)

Write-Host ""
Write-Host "环境检查通过。" -ForegroundColor Green
