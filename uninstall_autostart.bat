@echo off
setlocal
chcp 936 >nul
title Network HUD - 移除开机自启动
set "DIR=%~dp0"
cd /d "%DIR%"

set "PY=python"
where python >nul 2>nul || set "PY=py -3"

%PY% "%DIR%tools\autostart.py" --uninstall
echo.
pause
