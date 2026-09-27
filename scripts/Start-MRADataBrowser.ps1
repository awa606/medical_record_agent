param(
    [ValidateSet('Start', 'Refresh', 'Stop', 'Open')][string]$Action = 'Start',
    [string]$SourceDb,
    [string]$SourceLabel = '8795 candidate',
    [string]$PythonPath,
    [switch]$OpenBrowser
)
$ErrorActionPreference = 'Stop'
$repoDir = Split-Path -Parent $PSScriptRoot
$toolDir = Join-Path $repoDir '.artifacts/data-browser'
$statePath = Join-Path $toolDir 'state.private.json'
$scriptPath = Join-Path $PSScriptRoot 'data_browser.py'
$policyPath = Join-Path $repoDir 'tools/data-browser/synthetic-allowlist.json'
if (-not $PythonPath) { $PythonPath = Join-Path $repoDir '.artifacts/alpha51-data-browser-20260928/venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Install the isolated tool environment from the runbook first.' }
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
New-Item -ItemType Directory -Path $toolDir -Force | Out-Null

function Get-OwnedProcess($saved) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($saved.pid)" -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    if (-not $proc.CommandLine -or -not $proc.CommandLine.Contains($scriptPath) -or -not $proc.CommandLine.Contains($saved.run_id)) {
        throw 'Saved PID belongs to a different process; refusing to stop or reuse it.'
    }
    return $proc
}

$saved = if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json } else { $null }
if ($Action -eq 'Stop') {
    if ($saved -and (Get-OwnedProcess $saved)) { Stop-Process -Id $saved.pid }
    Write-Output 'Data browser stopped; snapshots and 8795 preserved.'
    exit
}
if ($saved -and (Get-OwnedProcess $saved) -and $Action -ne 'Refresh') {
    if ($OpenBrowser -or $Action -eq 'Open') { & $PythonPath $scriptPath open --snapshot-dir $saved.snapshot_dir }
    Write-Output "Running: http://127.0.0.1:$($saved.port)/ (local authenticated browser profile)"
    exit
}
if ($Action -eq 'Open') { throw 'Browser is stopped; use Start first.' }
if (-not $SourceDb -and $saved) { $SourceDb = $saved.source_db; $SourceLabel = $saved.source_label }
if (-not $SourceDb) { throw '-SourceDb must name the actual 8795 SQLite file.' }
$SourceDb = (Resolve-Path -LiteralPath $SourceDb).Path
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$snapshotDir = Join-Path $toolDir $stamp
& $PythonPath $scriptPath snapshot --source-db $SourceDb --output $snapshotDir --allowlist $policyPath --source-label $SourceLabel
if ($LASTEXITCODE -ne 0) { throw 'Snapshot failed; existing browser retained.' }
$usedPorts = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalPort)
$port = @(8796,8797 | Where-Object { $_ -notin $usedPorts } | Select-Object -First 1)
if ($port.Count -eq 0) { throw '8796 and 8797 occupied; existing services retained.' }
$port = [int]$port[0]
$runId = [guid]::NewGuid().ToString()
$argsLine = '"{0}" serve --snapshot-dir "{1}" --port {2} --run-id {3}' -f $scriptPath, $snapshotDir, $port, $runId
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
    throw "New viewer failed; existing viewer retained. See $snapshotDir"
}
if ($saved -and (Get-OwnedProcess $saved)) { Stop-Process -Id $saved.pid }
@{ pid=$proc.Id; run_id=$runId; port=$port; snapshot_dir=$snapshotDir; source_db=$SourceDb; source_label=$SourceLabel } |
    ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
if ($OpenBrowser) { & $PythonPath $scriptPath open --snapshot-dir $snapshotDir }
Write-Output "Ready: http://127.0.0.1:$port/ ; snapshot: $snapshotDir"
