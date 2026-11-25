@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo MediListen 文档接诊工作台 - 合成演示
echo http://127.0.0.1:23714/
set "MRA_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%MRA_PYTHON%" (
  "%MRA_PYTHON%" "%~dp0serve.py" --port 23714 --open
) else (
  python "%~dp0serve.py" --port 23714 --open
)
pause
