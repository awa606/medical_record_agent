param(
    [ValidateSet('Start', 'Refresh', 'Stop', 'Open')][string]$Action = 'Start',
    [string]$SourceDb,
    [string]$SourceLabel = '8795 展示候选',
    [string]$PythonPath,
    [string]$StateDirectory,
    [string]$AllowlistPath,
    [ValidateRange(0,65535)][int]$Port = 0,
    [switch]$OpenBrowser
)
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$toolDir = if ($StateDirectory) { [IO.Path]::GetFullPath($StateDirectory) } else { Join-Path $repoDir '.artifacts/data-browser' }
$statePath = Join-Path $toolDir 'state.private.json'
$scriptPath = Join-Path $PSScriptRoot 'data_browser.py'
$policyPath = if ($AllowlistPath) { (Resolve-Path -LiteralPath $AllowlistPath).Path } else { Join-Path $repoDir 'tools/data-browser/synthetic-allowlist.json' }
if (-not $PythonPath) { $PythonPath = Join-Path $repoDir '.artifacts/alpha51-data-browser-20260928/venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw '查看器独立运行环境不存在，请按维护说明恢复后重试。' }
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
New-Item -ItemType Directory -Path $toolDir -Force | Out-Null

function Get-OwnedProcess($saved) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($saved.pid)" -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    if (-not $proc.CommandLine -or -not $proc.CommandLine.Contains($scriptPath) -or -not $proc.CommandLine.Contains($saved.run_id)) {
        # Windows may reuse the saved PID after reboot. Never stop that process;
        # let Start create a new viewer only after a successful port-bind probe.
        Write-Warning '旧查看器进程编号已被其他程序使用，已保留该程序。'
        return $null
    }
    return $proc
}

$saved = if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json } else { $null }
if ($saved -and $SourceDb -and ([IO.Path]::GetFullPath($SourceDb) -ne [IO.Path]::GetFullPath($saved.source_db))) {
    throw '快照属于另一数据环境，请使用该环境独立的状态目录（StateDirectory）。'
}
if ($Action -eq 'Stop') {
    if ($saved -and (Get-OwnedProcess $saved)) { Stop-Process -Id $saved.pid }
    Write-Output '数据与知识查看器已停止；快照和医生工作台均保留。'
    exit
}
if ($saved -and (Get-OwnedProcess $saved) -and $Action -ne 'Refresh') {
    if ($OpenBrowser -or $Action -eq 'Open') { & $PythonPath -X utf8 $scriptPath open --snapshot-dir $saved.snapshot_dir }
    Write-Output "查看器运行中： http://127.0.0.1:$($saved.port)/ （使用已授权的本机浏览器）"
    exit
}
if ($Action -eq 'Open') { throw '查看器未运行，请先点击启动。' }
if (-not $SourceDb -and $saved) { $SourceDb = $saved.source_db; $SourceLabel = $saved.source_label }
if (-not $SourceDb) { throw '请指定当前环境的实际数据库文件（SourceDb）。' }
$SourceDb = (Resolve-Path -LiteralPath $SourceDb).Path
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$snapshotDir = Join-Path $toolDir $stamp
& $PythonPath -X utf8 $scriptPath snapshot --source-db $SourceDb --output $snapshotDir --allowlist $policyPath --source-label $SourceLabel
if ($LASTEXITCODE -ne 0) { throw '生成快照失败，原查看器保留；请检查源库和匿名病例白名单。' }
$candidatePorts = if ($Port) { @($Port) } else { @(8796,8797,18896,18897) }
$selectedPort = & $PythonPath -X utf8 $scriptPath choose-port @candidatePorts
if ($LASTEXITCODE -ne 0) { throw '端口被占用或保留，请指定空闲端口（Port）；未停止其他服务。' }
$port = [int]$selectedPort
$runId = [guid]::NewGuid().ToString()
$argsLine = '-X utf8 "{0}" serve --snapshot-dir "{1}" --port {2} --run-id {3}' -f $scriptPath, $snapshotDir, $port, $runId
$proc = Start-Process -FilePath $PythonPath -ArgumentList $argsLine -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $snapshotDir 'stdout.private.log') `
    -RedirectStandardError (Join-Path $snapshotDir 'stderr.private.log')
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ($proc.HasExited) { break }
    try {
        $response = Invoke-WebRequest "http://127.0.0.1:$port/" -SkipHttpErrorCheck -TimeoutSec 1
        if ($response.StatusCode -eq 403 -and (Test-Path -LiteralPath (Join-Path $snapshotDir 'login.private.json'))) { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 300
}
if (-not $ready) {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id }
    throw "新查看器启动失败，原查看器保留。日志目录：$snapshotDir"
}
if ($saved -and (Get-OwnedProcess $saved)) { Stop-Process -Id $saved.pid }
@{ pid=$proc.Id; run_id=$runId; port=$port; snapshot_dir=$snapshotDir; source_db=$SourceDb; source_label=$SourceLabel } |
    ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
if ($OpenBrowser) { & $PythonPath -X utf8 $scriptPath open --snapshot-dir $snapshotDir }
Write-Output "查看器已就绪： http://127.0.0.1:$port/；快照目录：$snapshotDir"
