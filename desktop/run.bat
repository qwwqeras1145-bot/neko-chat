@echo off
chcp 65001 >nul
title 喵酱 Chat
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python server.py
) else (
  echo [错误] 未找到 Python，请先安装: https://www.python.org/downloads/
  pause
)
