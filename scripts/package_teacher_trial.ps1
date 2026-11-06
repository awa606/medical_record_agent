[CmdletBinding()]
param(
    [string]$SourceDirectory,
    [string]$PackDirectory,
    [string]$LauncherConfig,
    [switch]$NoDesktop
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $SourceDirectory) { $SourceDirectory = Join-Path $repo 'docs/pilot/teacher-onsite-20261020' }
if (-not $PackDirectory) { $PackDirectory = Join-Path $repo '.artifacts/teacher-onsite-20261020/pack' }
if (-not $LauncherConfig) { $LauncherConfig = Join-Path $repo '.artifacts/online-demo-20261019/deploy-9af10d7/launcher-8798.json' }
$source = (Resolve-Path -LiteralPath $SourceDirectory).Path
$config = Get-Content -LiteralPath $LauncherConfig -Raw -Encoding utf8 | ConvertFrom-Json
if ($config.port -ne 8798 -or $config.provider_profile -ne 'online_deepseek') {
    throw '必须使用既有8798在线审核候选配置；本脚本不会替换、启动或切换服务。'
}
if ([string]$config.app_git_sha -notmatch '^[0-9a-f]{40}$') { throw '8798配置缺少完整运行版本SHA。' }
# 内容构建器先输出到PackDirectory。包装阶段只复制明确入口资源，不覆盖PDF/反馈。
$sourceFiles = @('index.html', 'facilitator.html')
$generatedFiles = @(
    'guide.html', 'cases.html', 'recording.html', 'feedback.html',
    'guide.pdf', 'cases.pdf', 'recording.pdf', 'feedback.pdf',
    'trial.css', 'trial.js', 'case-T01.txt', 'case-T02.txt'
)
foreach ($name in $sourceFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $name) -PathType Leaf)) { throw "缺少试用材料：$name" }
}
foreach ($name in $generatedFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $PackDirectory $name) -PathType Leaf)) {
        throw "缺少已生成材料：$name。请先运行build_materials.py --out 指向本试用包目录。"
    }
}
if (-not (Get-Content -LiteralPath (Join-Path $source 'index.html') -Raw -Encoding utf8).Contains($config.app_git_sha.Substring(0, 8))) {
    throw '试用首页的版本标识与8798配置不同；先更新并核对材料，不自动覆盖版本说明。'
}
New-Item -ItemType Directory -Path $PackDirectory -Force | Out-Null
$pack = (Resolve-Path -LiteralPath $PackDirectory).Path
foreach ($name in $sourceFiles) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $pack $name) -Force
}
$assets = Join-Path $pack 'assets'
New-Item -ItemType Directory -Path $assets -Force | Out-Null
foreach ($name in @('medilisten-v1.png', 'medilisten-v1.ico')) {
    Copy-Item -LiteralPath (Join-Path $repo "static/brand/$name") -Destination (Join-Path $assets $name) -Force
}
# 本机Windows PowerShell无需额外安装。保存BOM，避免5.1把中文错误解码为ANSI。
$launcherText = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'open_teacher_trial.ps1') -Raw -Encoding utf8
[IO.File]::WriteAllText((Join-Path $pack 'open_teacher_trial.ps1'), $launcherText, [Text.UTF8Encoding]::new($true))
# 不复制canonical配置。包内仅保存公开入口和版本，没有密码、密钥或会话。
[ordered]@{
    schema_version = 1; base_url = 'http://127.0.0.1:8798'
    app_git_sha = $config.app_git_sha
    label = 'MediListen 教师现场试用（受控审核候选）'
    materials_date = '2026-10-20'; credentials_included = $false
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $pack 'trial-config.json') -Encoding utf8

$powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
if (-not (Test-Path -LiteralPath $powershell -PathType Leaf)) { throw '缺少Windows PowerShell，无法创建当前Windows平台的桌面入口。' }
$shell = New-Object -ComObject WScript.Shell
$shortcuts = @()
function Set-TrialShortcut([string]$Path, [string]$View, [string]$Description) {
    if (Test-Path -LiteralPath $Path) {
        $existing = $shell.CreateShortcut($Path)
        if ($existing.TargetPath -ne $powershell -or -not $existing.Arguments.Contains($pack)) {
            throw "入口已存在且不属于本试用包，未覆盖：$Path"
        }
    }
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = '-NoProfile -STA -WindowStyle Hidden -File "' + (Join-Path $pack 'open_teacher_trial.ps1') + '" -PackDirectory "' + $pack + '" -View ' + $View
    $shortcut.WorkingDirectory = $pack
    $shortcut.IconLocation = (Join-Path $assets 'medilisten-v1.ico') + ',0'
    $shortcut.Description = $Description
    $shortcut.Save()
}
$startShortcut = Join-Path $pack '开始体验（医生工作台）.lnk'
Set-TrialShortcut $startShortcut 'Workspace' '使用独立教师窗口打开8798；不启动、停止或切换服务。'
$shortcuts += $startShortcut
if (-not $NoDesktop) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $homeShortcut = Join-Path $desktop 'MediListen 教师现场试用.lnk'
    Set-TrialShortcut $homeShortcut 'Home' '先看操作指南、测试病例与录音稿，再开始体验。'
    $shortcuts += $homeShortcut
    # 文件夹快捷方式便于拿到离线材料和专用“开始体验”入口，不复制整套运行数据。
    $folderShortcut = Join-Path $desktop 'MediListen 教师试用材料.lnk'
    if (Test-Path -LiteralPath $folderShortcut) {
        $existing = $shell.CreateShortcut($folderShortcut)
        if ($existing.TargetPath -ne $pack) { throw "材料入口已存在且指向其他目录，未覆盖：$folderShortcut" }
    }
    $folder = $shell.CreateShortcut($folderShortcut)
    $folder.TargetPath = $pack
    $folder.IconLocation = (Join-Path $assets 'medilisten-v1.ico') + ',0'
    $folder.Description = '教师操作指南、测试病例、录音稿和反馈表；不包含运行凭据。'
    $folder.Save()
    $shortcuts += $folderShortcut
}
[pscustomobject]@{
    pack_directory = $pack; shortcuts = $shortcuts
    app_git_sha = $config.app_git_sha; service_actions = 0
    copied_files = @($sourceFiles + @('assets/medilisten-v1.png', 'assets/medilisten-v1.ico', 'open_teacher_trial.ps1', 'trial-config.json'))
    verified_materials = $generatedFiles
    note = '未删除包内已有PDF或其他生成材料；未复制浏览器profile或登录凭据。'
} | ConvertTo-Json -Depth 4
