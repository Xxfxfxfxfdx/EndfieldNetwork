@echo off
setlocal
cd /d "%~dp0"
python -m net_hud --quit
if errorlevel 1 (
    echo 没有检测到正在运行的 NetworkHUD 实例。
    echo NetworkHUD Not Found.
    echo いま、運行中のNetworkHUDがありません。
) else (
    echo 已发送退出信号。
    echo Exit command sent.
    echo 終了しました。
)
ping -n 4 127.0.0.1 >nul
endlocal
