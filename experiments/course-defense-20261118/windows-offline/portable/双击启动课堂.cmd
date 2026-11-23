@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0专用环境" || exit /b 1
powershell.exe -NoProfile -File ".\windows_bootstrap.ps1" -Action start %*
set "classroomExit=%errorlevel%"
popd
exit /b %classroomExit%
