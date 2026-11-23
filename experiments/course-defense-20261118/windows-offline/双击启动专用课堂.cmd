@echo off
setlocal
powershell.exe -NoProfile -File "%~dp0windows_bootstrap.ps1" -Action start %*
exit /b %errorlevel%
