[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ComposeProfiles = @("--profile", "hadoop", "--profile", "hive", "--profile", "spark", "--profile", "tools")
[Environment]::SetEnvironmentVariable("COMPOSE_IGNORE_ORPHANS", "true", "Process")

Set-Location -LiteralPath $ProjectRoot

Write-Host "停止 Docker 开发环境，不删除数据目录和 volume。" -ForegroundColor Cyan
$dockerArgs = @("compose") + $ComposeProfiles + @("down")
& docker @dockerArgs
if ($LASTEXITCODE -ne 0) {
    throw "停止 Docker 开发环境失败。"
}

Write-Host "Docker 开发环境已停止。" -ForegroundColor Green
