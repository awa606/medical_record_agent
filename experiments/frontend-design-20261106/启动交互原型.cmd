@echo off
chcp 65001 >nul
cd /d "%~dp0"
python serve.py --open
if errorlevel 1 (
  echo 原型未启动，请检查 Python 或端口 23711 是否已被占用。
  pause
)
