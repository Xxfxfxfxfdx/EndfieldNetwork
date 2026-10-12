@echo off
setlocal
cd /d "%~dp0"
set "DIR=%~dp0"
set "PYW=pythonw.exe"
where %PYW% >nul 2>nul
if errorlevel 1 set "PYW=python.exe"
start "" "%PYW%" "%DIR%run.pyw" %*
echo.
echo NetworkHUD 已在后台启动（无控制台窗口）。
echo 托盘图标位于通知区域，右键可选择「退出」。
echo 需要停止时，也可双击 stop.bat。
echo NetworkHUD has started（without cmd console window）。
echo Icon has been created in system tray，right-click and click「Exit」 to quit.
echo To stop, you also can run stop.bat
echo NetworkHUD プログラムはバックグラウンドで実行されます（コマンドラインがありません）
echo アイコンはシステムトレイに表示され、右クリックで終了またはプレビューできます
echo プログラムを停止する必要がある場合は、stop.batを実行することもできます
echo.
ping -n 5 127.0.0.1 >nul
endlocal
