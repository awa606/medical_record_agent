@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo MediListen 接诊工作台设计原型
echo 地址：http://127.0.0.1:23713/
echo 关闭此窗口即停止原型服务。
python "%~dp0serve.py" --port 23713 --open
pause
