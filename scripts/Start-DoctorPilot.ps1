param([Parameter(Mandatory=$true)][string]$Config,
      [string]$Python = 'python', [switch]$InstallShortcut, [switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$configPath = (Resolve-Path -LiteralPath $Config).Path
$pythonPath = (Get-Command $Python).Source
$controller = Join-Path $PSScriptRoot 'doctor_pilot.py'
$documents = Join-Path $root 'docs\pilot\doctor-v1'
$iconPath = Join-Path $root 'static\brand\medilisten-v1.ico'

if ($InstallShortcut) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $link = Join-Path $desktop 'MediListen 医生试用入口.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($link)
    $shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $shortcut.Arguments = '-NoProfile -STA -WindowStyle Hidden -File "' + $PSCommandPath + '" -Config "' + $configPath + '" -Python "' + $pythonPath + '"'
    $shortcut.WorkingDirectory = $root
    $shortcut.Description = '本机候选版：启动、工作台、操作手册与试用反馈'
    if (Test-Path -LiteralPath $iconPath) { $shortcut.IconLocation = "$iconPath,0" }
    $shortcut.Save()
    Write-Output $link
    exit
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = 'MediListen · 医生试用入口'
if (Test-Path -LiteralPath $iconPath) { $form.Icon = New-Object System.Drawing.Icon($iconPath) }
$form.Size = New-Object System.Drawing.Size(800,590)
$form.MinimumSize = New-Object System.Drawing.Size(780,570)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object System.Drawing.Font('Microsoft YaHei UI',11)
$form.BackColor = [System.Drawing.Color]::White
$layout = New-Object System.Windows.Forms.TableLayoutPanel
$layout.Dock = 'Fill'; $layout.Padding = New-Object System.Windows.Forms.Padding(24)
$layout.ColumnCount=1; $layout.RowCount=5
@(65,65,115,70) | ForEach-Object { [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle('Absolute',$_))) }
[void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle('Percent',100)))
$form.Controls.Add($layout)
$title = New-Object System.Windows.Forms.Label
$title.Text = 'MediListen  医生试用'; $title.Dock='Fill'
$title.Font=New-Object System.Drawing.Font('Microsoft YaHei UI',19,[System.Drawing.FontStyle]::Bold)
$layout.Controls.Add($title,0,0)
$version = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($version.handbook_dir -and (Test-Path -LiteralPath $version.handbook_dir)) { $documents=$version.handbook_dir }
$context = New-Object System.Windows.Forms.Label
$context.Dock='Fill'
$context.Text = "内部候选 · 尚未放行独立医生试用`r`n应用版本 $($version.app_git_sha.Substring(0,12)) · 仅合成病例／模拟问诊"
$layout.Controls.Add($context,0,1)
$actions = New-Object System.Windows.Forms.FlowLayoutPanel; $actions.Dock='Fill'
$layout.Controls.Add($actions,0,2)
$help = New-Object System.Windows.Forms.FlowLayoutPanel; $help.Dock='Fill'
$layout.Controls.Add($help,0,3)
$status = New-Object System.Windows.Forms.TextBox
$status.Multiline=$true; $status.ReadOnly=$true; $status.Dock='Fill'; $status.ScrollBars='Vertical'
$status.Text="请点击启动服务。关闭此窗口不会停止服务或删除数据。`r`n停止服务前，请结束录音并保存病历。"
$layout.Controls.Add($status,0,4)
$script:worker=$null; $script:logPath=$null; $script:errPath=$null
$script:buttons = @()

function Add-ActionButton($panel,$text,$handler) {
    $button=New-Object System.Windows.Forms.Button
    $button.Text=$text; $button.AutoSize=$true; $button.Height=42
    $button.Padding=New-Object System.Windows.Forms.Padding(10,4,10,4)
    $button.Margin=New-Object System.Windows.Forms.Padding(0,0,10,8)
    $button.Add_Click($handler); $panel.Controls.Add($button)
    return $button
}

function Invoke-Pilot($action) {
    if ($script:worker -and -not $script:worker.HasExited) { return }
    $stamp=[Guid]::NewGuid().ToString('N')
    $script:logPath=Join-Path ([IO.Path]::GetDirectoryName($configPath)) ("launch-$stamp.jsonl")
    $script:errPath=Join-Path ([IO.Path]::GetDirectoryName($configPath)) ("launch-$stamp.error.log")
    $args='-X utf8 "'+$controller+'" '+$action+' --config "'+$configPath+'"'
    $script:worker=Start-Process -FilePath $pythonPath -ArgumentList $args -PassThru -WindowStyle Hidden -RedirectStandardOutput $script:logPath -RedirectStandardError $script:errPath
    foreach($b in $script:buttons){$b.Enabled=$false}
    $status.Text='正在检查登记版本与本地服务，请稍候……'
}

$script:buttons += Add-ActionButton $actions '启动服务' { Invoke-Pilot 'start' }
$openButton = Add-ActionButton $actions '打开工作台' {
    if ($script:worker -and -not $script:worker.HasExited) {
        $args='-X utf8 "'+$controller+'" open --config "'+$configPath+'"'
        Start-Process -FilePath $pythonPath -ArgumentList $args -WindowStyle Hidden
    } else { Invoke-Pilot 'open' }
}
$script:buttons += $openButton
$script:buttons += Add-ActionButton $actions '知识管理（管理员）' { Invoke-Pilot 'open-knowledge' }
$script:buttons += Add-ActionButton $actions '数据／知识浏览器' { Invoke-Pilot 'open-data' }
$script:buttons += Add-ActionButton $actions '检查状态' { Invoke-Pilot 'status' }
$script:buttons += Add-ActionButton $actions '停止服务' {
    $answer=[System.Windows.Forms.MessageBox]::Show('请确认已经停止录音、等待任务结束并保存病历。只停止本版本，数据保留。','停止MediListen','YesNo','Warning')
    if($answer -eq 'Yes'){Invoke-Pilot 'stop'}
}
[void](Add-ActionButton $help '快速开始／操作手册' { Start-Process (Join-Path $documents 'manual.html') })
[void](Add-ActionButton $help '填写试用反馈' { Start-Process (Join-Path $documents 'feedback.html') })
[void](Add-ActionButton $help '维护说明' { Start-Process (Join-Path $documents 'maintenance.html') })
$timer=New-Object System.Windows.Forms.Timer; $timer.Interval=1000
$timer.Add_Tick({
    if(-not $script:worker){return}
    if(Test-Path -LiteralPath $script:logPath){
        $lines=@(Get-Content -LiteralPath $script:logPath -Encoding UTF8 -ErrorAction SilentlyContinue)
        $readable=@()
        foreach($line in $lines){
            try {
                $s=$line | ConvertFrom-Json
                $label=switch($s.phase){'READY'{'运行就绪：可以打开工作台；模型质量和医生试用尚未放行。'} 'VIEWER_READY'{'只读数据浏览器已打开，需使用本机认证。'} 'MODEL_NOT_READY'{'网页可用，真实模型预热中；生成保持阻断。'} 'WEB_STARTING'{'服务启动中。'} 'STOPPED'{'服务已停止，数据保留。'} 'ERROR'{$s.message} default {$s.phase}}
                $readable += $label
                if($s.entrypoints){
                    foreach($key in @('doctor','knowledge','data_browser','manual')){
                        $entry=$s.entrypoints.$key
                        if($entry){
                            $name=switch($key){'doctor'{'医生工作台'} 'knowledge'{'知识管理（需管理员登录）'} 'data_browser'{'数据浏览器（只读快照）'} 'manual'{'操作手册'}}
                            $availability=if($entry.available){'入口可用'}else{'尚不可用'}
                            $readable += "$name · $availability"
                            if($entry.url){$readable += "地址：$($entry.url)"}
                            if($entry.snapshot_at){$readable += "快照时间：$($entry.snapshot_at)；来源：$($entry.source_label)"}
                        }
                    }
                }
                if($s.web_available){$openButton.Enabled=$true}
            }catch{}
        }
        if($readable.Count){$status.Text=($readable -join "`r`n")}
    }
    if($script:worker.HasExited){
        foreach($b in $script:buttons){$b.Enabled=$true}
        if($script:worker.ExitCode -ne 0 -and $status.Text -notmatch 'MISMATCH|FAILED|TIMEOUT|ERROR|请|不存在'){
            $status.AppendText("`r`n操作失败，请维护人员查看本地启动日志。")
        }
        $script:worker.Dispose(); $script:worker=$null
    }
})
$timer.Start()
$form.Add_FormClosed({$timer.Stop();$timer.Dispose()})
if ($SmokeTest) {
    $result=@{title=$form.Text; icon_path=$iconPath; custom_icon=(Test-Path -LiteralPath $iconPath); action_buttons=@($actions.Controls | ForEach-Object {$_.Text}); help_buttons=@($help.Controls | ForEach-Object {$_.Text}); document_directory=$documents}
    $timer.Stop();$timer.Dispose();$form.Dispose()
    $result | ConvertTo-Json -Compress
    exit
}
[void]$form.ShowDialog()
