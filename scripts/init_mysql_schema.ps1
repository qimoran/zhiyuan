[CmdletBinding()]
param(
    [string]$SqlPath,
    [string]$DatabaseName,
    [string]$UserName,
    [string]$Password
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DefaultSqlPath = Join-Path $ProjectRoot "sql\mysql\001_create_tables.sql"
$EnvPath = Join-Path $ProjectRoot ".env"
$ComposeProfiles = @("--profile", "hadoop", "--profile", "hive", "--profile", "spark", "--profile", "tools")
[Environment]::SetEnvironmentVariable("COMPOSE_IGNORE_ORPHANS", "true", "Process")

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
    }

    return $values
}

function Get-ConfigValue {
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

function Assert-Identifier {
    param(
        [string]$Value,
        [string]$Label
    )

    if ($Value -notmatch "^[A-Za-z0-9_]+$") {
        throw "$Label 只能包含字母、数字和下划线：$Value"
    }
}

$envValues = Import-DotEnv -Path $EnvPath

if ([string]::IsNullOrWhiteSpace($SqlPath)) {
    $SqlPath = $DefaultSqlPath
}
if ([string]::IsNullOrWhiteSpace($DatabaseName)) {
    $DatabaseName = Get-ConfigValue -Values $envValues -Name "ZHIYUAN_DB_NAME" -Default "zhiyuan"
}
if ([string]::IsNullOrWhiteSpace($UserName)) {
    $UserName = Get-ConfigValue -Values $envValues -Name "ZHIYUAN_DB_USER" -Default "zhiyuan_app"
}
if ([string]::IsNullOrWhiteSpace($Password)) {
    $Password = Get-ConfigValue -Values $envValues -Name "ZHIYUAN_DB_PASSWORD" -Default ""
}

Assert-Identifier -Value $DatabaseName -Label "数据库名"
Assert-Identifier -Value $UserName -Label "数据库用户名"

if ([string]::IsNullOrWhiteSpace($Password)) {
    throw "数据库密码为空，请检查 .env 中的 ZHIYUAN_DB_PASSWORD。"
}

$resolvedSqlPath = Resolve-Path -LiteralPath $SqlPath
$sql = Get-Content -LiteralPath $resolvedSqlPath.Path -Raw -Encoding UTF8

Write-Host "开始初始化 MySQL 表结构：$($resolvedSqlPath.Path)" -ForegroundColor Cyan

$dockerArgs = @("compose") + $ComposeProfiles + @(
    "exec", "-T", "-e", "MYSQL_PWD=$Password", "mysql",
    "mysql", "--default-character-set=utf8mb4", "-u$UserName", $DatabaseName
)

$sql | & docker @dockerArgs
if ($LASTEXITCODE -ne 0) {
    throw "MySQL 表结构初始化失败。"
}

Write-Host "MySQL 表结构初始化完成。" -ForegroundColor Green
