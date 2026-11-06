@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo MediListen 三套布局交互比较
echo 地址：http://127.0.0.1:23712/
echo 关闭此窗口即停止原型服务。
python "%~dp0serve.py" --port 23712 --open
pause
