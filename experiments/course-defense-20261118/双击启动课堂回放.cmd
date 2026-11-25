@echo off
chcp 65001 > nul
cd /d "%~dp0"
if exist "C:\Anaconda\python.exe" (
  "C:\Anaconda\python.exe" -B -X utf8 "课堂启动.py"
) else (
  python -B -X utf8 "课堂启动.py"
)
if errorlevel 1 pause