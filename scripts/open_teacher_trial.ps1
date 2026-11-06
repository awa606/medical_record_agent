[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PackDirectory,
    [ValidateSet('Home', 'Workspace')][string]$View = 'Home',
    [switch]$CheckOnly
)

# 只打开本机教师试用材料或8798；不启动、停止或切换任何服务。
$ErrorActionPreference = 'Stop'
try {
    $pack = (Resolve-Path -LiteralPath $PackDirectory).Path
    $settings = Get-Content -LiteralPath (Join-Path $pack 'trial-config.json') -Raw -Encoding utf8 | ConvertFrom-Json
    if ($settings.schema_version -ne 1 -or $settings.base_url -ne 'http://127.0.0.1:8798') {
        throw '试用入口配置不匹配。请由维护者重新整理8798教师试用包。'
    }
    $index = Join-Path $pack 'index.html'
    if (-not (Test-Path -LiteralPath $index -PathType Leaf)) {
        throw '未找到教师试用首页，请由维护者重新整理试用包。'
    }
    $edge = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft/Edge/Application/msedge.exe'),
        (Join-Path $env:ProgramFiles 'Microsoft/Edge/Application/msedge.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft/Edge/Application/msedge.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $edge) { throw '未找到Microsoft Edge，请联系现场维护者。' }

    $available = $false
    $versionMatches = $false
    $runtimeVersion = $null
    try {
        $health = Invoke-WebRequest -Uri ($settings.base_url + '/health') -TimeoutSec 5 -UseBasicParsing
        $deployment = Invoke-RestMethod -Uri ($settings.base_url + '/static/deployment.json') -TimeoutSec 5
        $available = $health.StatusCode -eq 200
        $runtimeVersion = [string]$deployment.version
        $versionMatches = $runtimeVersion -eq [string]$settings.app_git_sha
    } catch {
        # 帮助材料仍可离线打开。Workspace分支才阻止进入不可用的系统。
    }
    $profile = Join-Path (Split-Path -Parent $pack) 'teacher-browser-profile'
    $workspaceUrl = $settings.base_url + '/static/doctor.html?v=' + [Uri]::EscapeDataString([string]$settings.app_git_sha)
    if ($CheckOnly) {
        [pscustomobject]@{
            view = $View; web_available = $available; version_matches = $versionMatches
            runtime_version = $runtimeVersion; expected_version = $settings.app_git_sha
            workspace_url = $workspaceUrl
            profile_is_outside_pack = -not $profile.StartsWith($pack + [IO.Path]::DirectorySeparatorChar)
            home_available = $true; service_actions = 0; launcher_uses_credentials = $false
        } | ConvertTo-Json
        if ($View -eq 'Workspace' -and (-not $available -or -not $versionMatches)) { exit 1 }
        exit 0
    }
    if ($View -eq 'Workspace') {
        if (-not $available) { throw '8798暂时无法连接。请先请现场维护者启动服务；可继续打开教师操作指南。本入口不会重启或切换环境。' }
        if (-not $versionMatches) { throw '运行版本与本次试用资料不一致。请联系现场维护者核对版本后再开始，避免误用旧页面。' }
        $url = $workspaceUrl
    } else {
        $url = ([Uri]$index).AbsoluteUri
    }
    New-Item -ItemType Directory -Path $profile -Force | Out-Null
    $edgeArgs = @(('"--user-data-dir=' + $profile + '"'), '--no-first-run', ('"--app=' + $url + '"'))
    # 用户明确要求可见的教师独立窗口；启动器自身由快捷方式隐藏。
    Start-Process -FilePath $edge -ArgumentList $edgeArgs -WindowStyle Normal
} catch {
    if ($CheckOnly) { Write-Error $_.Exception.Message; exit 1 }
    Add-Type -AssemblyName PresentationFramework
    [void][System.Windows.MessageBox]::Show($_.Exception.Message, 'MediListen 教师现场试用', 'OK', 'Information')
    exit 1
}
