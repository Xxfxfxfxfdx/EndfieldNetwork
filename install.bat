@echo off
setlocal
chcp 936 >nul
title Network HUD - 安装依赖
set "DIR=%~dp0"
cd /d "%DIR%"

echo ============================================
echo   Network HUD - 安装依赖库
echo ============================================
echo.

set "PY=python"
where python >nul 2>nul || set "PY=py -3"

%PY% -c "import sys;print('Python',sys.version.split()[0],sys.executable)" 2>nul
if errorlevel 1 (
  echo [错误] 没有找到 Python。请先安装 Python 3.9 或更高版本，
  echo        安装时记得勾选 Add python.exe to PATH。
  echo        下载地址：https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

echo.
echo 正在安装 Pillow / numpy / pywin32 ...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r "%DIR%requirements.txt"
if errorlevel 1 (
  echo.
  echo [错误] 依赖安装失败。如果是下载太慢，可以改用国内镜像重试：
  echo        %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  echo.
  pause
  exit /b 1
)

echo.
echo 依赖安装完成。双击 start.bat 即可运行。
echo.
pause
