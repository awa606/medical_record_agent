param(
    [ValidateSet('prepare','start')][string]$Action='start',
    [string]$HostRoot, [string]$EnvPath, [string]$DataRoot,
    [ValidateRange(1024,65535)][int]$Port=26428, [switch]$NoBrowser, [switch]$Online
)
$ErrorActionPreference = 'Stop'
$release = $null
$layout = [IO.Path]::Combine('output','20261124_企业与结课验收','软件','专用环境')
if ($PSScriptRoot.EndsWith(('\' + $layout),[StringComparison]::OrdinalIgnoreCase)) {
    $release = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..\.artifacts\20261124-release'))
}
$workspaceLayout = $false
if ($release) {
    $marker = [IO.Path]::Combine($release,'.medilisten-workspace-root.txt')
    $projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
    if ([IO.File]::Exists($marker)) {
        $workspaceLayout = [string]::Equals([IO.File]::ReadAllText($marker).Trim(),$projectRoot,[StringComparison]::OrdinalIgnoreCase)
    }
}
$appData = Join-Path $env:LOCALAPPDATA 'MediListen课堂专用'
if (-not $HostRoot) {
    if ($workspaceLayout) {
        $HostRoot = Join-Path $release 'Windows主宿主-3.14.10'
    } else {
        $HostRoot = Join-Path $appData 'CPython-3.14.10-amd64'
    }
}
$HostRoot = [IO.Path]::GetFullPath($HostRoot)
if (-not $EnvPath) {
    if ($workspaceLayout) {
        $EnvPath = Join-Path $release 'Windows-CPython314-专用'
    } else {
        $EnvPath = Join-Path $appData 'Windows-CPython314-专用'
    }
}
$EnvPath = [IO.Path]::GetFullPath($EnvPath)
$pythonExe = Join-Path $HostRoot 'python.exe'
function Get-LocalSha256([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Assert-HostFiles([string]$Folder) {
    $expected = @{
        'python.exe' = 'd718435b892db4ad5b547d12fec61be7baa7faf7a58d857ea58053be24c7a000'
        'python314.dll' = 'd8a06cc6ca3348925ea29e343e1c5c5895fe0bb433ff913e1cee44caf358aa6a'
        'python3.dll' = '7bb0a7df2d5cb829319dd8d122039843e2a762361bb5a61bb5d24ca34f4040b5'
    }
    foreach ($name in $expected.Keys) {
        if ((Get-LocalSha256 (Join-Path $Folder $name)) -ne $expected[$name]) {
            throw "解释器文件校验失败：$name"
        }
    }
}
if (-not (Test-Path -LiteralPath $HostRoot)) {
    $archive = Join-Path $PSScriptRoot 'python-3.14.10-amd64.zip'
    if ((Get-LocalSha256 $archive) -ne 'cc28026a650970cc1570bb127312f1f9634eb67abfe157ae6ca1acbbc627d091') {
        throw '官方解释器 ZIP 校验失败。'
    }
    $parent = Split-Path -Parent $HostRoot
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    $staging = Join-Path $parent ('CPython-解压-' + [Guid]::NewGuid().ToString('N'))
    [void][Reflection.Assembly]::Load('System.IO.Compression.FileSystem, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089')
    [IO.Compression.ZipFile]::ExtractToDirectory($archive,$staging)
    Assert-HostFiles $staging
    [IO.Directory]::Move($staging,$HostRoot)
}
Assert-HostFiles $HostRoot
$runtime = Join-Path $PSScriptRoot 'windows_runtime.py'
if ($Action -eq 'prepare' -or -not (Test-Path -LiteralPath (Join-Path $EnvPath 'Scripts\python.exe')) -or (Test-Path -LiteralPath (Join-Path $EnvPath '.medilisten-preparing.json'))) {
    $params = @('prepare','--env-path',$EnvPath)
    if (-not $Online) { $params += @('--wheel-dir',(Join-Path $PSScriptRoot 'wheels-win314-x64')) }
    & $pythonExe -I -B -X utf8 $runtime @params
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Action -eq 'start') {
    $params = @('start','--env-path',$EnvPath,'--port',$Port)
    if ($DataRoot) { $params += @('--data-root',$DataRoot) }
    if ($NoBrowser) { $params += '--no-browser' }
    & $pythonExe -I -B -X utf8 $runtime @params
    exit $LASTEXITCODE
}
