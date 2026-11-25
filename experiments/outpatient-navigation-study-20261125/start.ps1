param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$packageName='MediListen_字段审核_Windows-x64_a2f6c31_r4.5.zip'
$release=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$package=(Join-Path $release ('软件\中文冲突提示试用\'+$packageName))
if (-not [IO.File]::Exists($package)) {
    $package=Join-Path $PSScriptRoot $packageName
    if (-not [IO.File]::Exists($package)) {$package=Join-Path (Split-Path $PSScriptRoot -Parent) $packageName}
}
if (-not [IO.File]::Exists($package)) {throw '请将未改名的 r4.5 Windows ZIP 放在此启动器旁，然后重新双击。'}
$expected='f77967711c459cfec818bc71176f64d52cef3cdcb84a43f2b2133b3680c240d6'
$env:PSModulePath=(Join-Path $PSHOME 'Modules')+';'+$env:PSModulePath
$sha=[Security.Cryptography.SHA256]::Create()
$payload=[IO.File]::OpenRead($package)
try {$actual=[BitConverter]::ToString($sha.ComputeHash($payload)).Replace('-','')} finally {$payload.Dispose();$sha.Dispose()}
if ($actual -ne $expected) {throw 'r4.5 冻结包校验未通过。'}
$workspace=Join-Path $release '..\..\.artifacts\20261124-release'
$python=Join-Path $workspace 'Windows-CPython314-专用\Scripts\python.exe'
if (-not [IO.File]::Exists($python)) {
    $envPath=Join-Path $env:LOCALAPPDATA 'MediListen课堂专用\Windows-CPython314-专用'
    $python=Join-Path $envPath 'Scripts\python.exe'
    $tempRoot=[IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $target=[IO.Path]::Combine($tempRoot,'MediListen-AD-runtime-'+[Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($target)
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive=[IO.Compression.ZipFile]::OpenRead($package)
        $prefix='MediListen_同就诊来源修订试用/软件/'
        try {
            foreach ($entry in $archive.Entries) {
                if (($entry.FullName.StartsWith($prefix+'专用环境/',[StringComparison]::Ordinal) -or $entry.FullName -eq ($prefix+'现场回放/运行源/runtime-sha256.json')) -and $entry.Name) {
                    $file=[IO.Path]::GetFullPath([IO.Path]::Combine($target,$entry.FullName.Substring($prefix.Length)))
                    if (-not $file.StartsWith($target+'\',[StringComparison]::OrdinalIgnoreCase)) {throw '环境条目路径无效。'}
                    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($file))
                    [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$file)
                }
            }
        } finally {$archive.Dispose()}
        & (Join-Path $target '专用环境/windows_bootstrap.ps1') -Action prepare -EnvPath $envPath
        if ($LASTEXITCODE -ne 0) {exit $LASTEXITCODE}
    } finally {
        $resolved=(Resolve-Path -LiteralPath $target).Path
        if ([string]::Equals($resolved,$target,[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($target) -match '^MediListen-AD-runtime-[0-9a-f]{32}$' -and [IO.Path]::GetDirectoryName($target).TrimEnd('\') -eq $tempRoot.TrimEnd('\')) {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
}
$params=@('-I','-B','-X','utf8',(Join-Path $PSScriptRoot 'study.py'),'--package',$package)
if ($NoBrowser) {$params+='--no-browser'}
& $python @params
exit $LASTEXITCODE
