param(
    [ValidateSet('Start', 'Refresh', 'Stop', 'Open')][string]$Action = 'Start',
    [string]$SourceDb,
    [string]$SourceLabel = '8795 candidate',
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
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Install the isolated tool environment from the runbook first.' }
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
New-Item -ItemType Directory -Path $toolDir -Force | Out-Null

function Get-OwnedProcess($saved) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($saved.pid)" -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    if (-not $proc.CommandLine -or -not $proc.CommandLine.Contains($scriptPath) -or -not $proc.CommandLine.Contains($saved.run_id)) {
        # Windows may reuse the saved PID after reboot. Never stop that process;
        # let Start create a new viewer only after a successful port-bind probe.
        Write-Warning 'Stale viewer PID belongs to another process; leaving it untouched.'
        return $null
    }
    return $proc
}

$saved = if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json } else { $null }
if ($saved -and $SourceDb -and ([IO.Path]::GetFullPath($SourceDb) -ne [IO.Path]::GetFullPath($saved.source_db))) {
    throw 'Snapshot belongs to another source database. Use its own StateDirectory.'
}
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
$candidatePorts = if ($Port) { @($Port) } else { @(8796,8797,18896,18897) }
$selectedPort = & $PythonPath $scriptPath choose-port @candidatePorts
if ($LASTEXITCODE -ne 0) { throw 'Viewer port unavailable or reserved; use an explicit -Port. Existing services retained.' }
$port = [int]$selectedPort
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
