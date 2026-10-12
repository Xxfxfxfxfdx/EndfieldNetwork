"""开机自启动开关。

在 Windows 的「启动」文件夹里创建/删除一个指向本程序的快捷方式：

    %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\NetworkHUD.lnk

用快捷方式（而不是注册表 Run 项）的好处是：它就是一个普通文件，
在「任务管理器 → 启动」里能看到、能禁用，不想要时直接删掉即可。

命令行（一般由 install_autostart.bat / uninstall_autostart.bat 调用）：

    python tools\\autostart.py --install
    python tools\\autostart.py --uninstall
    python tools\\autostart.py --status
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LNK_NAME = "NetworkHUD.lnk"
ICON_NAME = "network_hud.ico"


def startup_dir() -> str:
    """当前用户的「启动」文件夹。"""
    base = os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming"
    )
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def shortcut_path() -> str:
    return os.path.join(startup_dir(), LNK_NAME)


def target_script() -> str:
    return os.path.join(ROOT, "run.pyw")


def pythonw() -> str:
    """优先用 pythonw.exe（无控制台窗口）；没有就退回当前解释器。"""
    for exe in (sys.executable, sys.executable.replace("python.exe", "pythonw.exe")):
        if exe and exe.lower().endswith("pythonw.exe") and os.path.isfile(exe):
            return exe
    cand = os.path.join(os.path.dirname(sys.executable or ""), "pythonw.exe")
    if os.path.isfile(cand):
        return cand
    return sys.executable or "pythonw.exe"


def icon_path() -> str | None:
    """生成并缓存一个托盘同款图标，给快捷方式用；失败就返回 None。"""
    try:
        from net_hud.tray import make_tray_icon

        path = os.path.join(ROOT, "assets", ICON_NAME)
        make_tray_icon(path)
        return path if os.path.isfile(path) else None
    except Exception:
        return None


def _shell():
    import win32com.client  # pywin32

    return win32com.client.Dispatch("WScript.Shell")


def install() -> int:
    lnk_path = shortcut_path()
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    script = target_script()
    if not os.path.isfile(script):
        print(f"[错误] 找不到 {script}")
        return 1
    exe = pythonw()
    if not exe.lower().endswith("pythonw.exe"):
        print(f"[提示] 没找到 pythonw.exe，将用 {exe}（启动时会闪一下控制台窗口）")

    shell = _shell()
    lnk = shell.CreateShortCut(lnk_path)
    lnk.TargetPath = exe
    lnk.Arguments = f'"{script}"'
    lnk.WorkingDirectory = ROOT
    lnk.Description = "Network HUD - 网络状态监测"
    icon = icon_path()
    lnk.IconLocation = f"{icon},0" if icon else f"{exe},0"
    lnk.save()

    if os.path.isfile(lnk_path):
        print("已添加开机自启动：")
        print(f"  {lnk_path}")
        print(f"  目标：{exe} \"{script}\"")
        print("  想关掉它：运行 uninstall_autostart.bat，")
        print("  或在「任务管理器 → 启动」里禁用它，或直接删掉上面这个快捷方式。")
        return 0
    print("[错误] 快捷方式创建失败")
    return 1


def uninstall() -> int:
    lnk_path = shortcut_path()
    if not os.path.isfile(lnk_path):
        print("开机自启动本来就没开启，无需操作。")
        return 0
    try:
        os.remove(lnk_path)
    except OSError as exc:
        print(f"[错误] 删除失败：{exc}")
        return 1
    print(f"已移除开机自启动：{lnk_path}")
    return 0


def status() -> int:
    lnk_path = shortcut_path()
    exists = os.path.isfile(lnk_path)
    print(f"快捷方式：{lnk_path}")
    print("状态：" + ("已启用" if exists else "未启用"))
    if exists:
        try:
            lnk = _shell().CreateShortCut(lnk_path)
            print(f"  目标：{lnk.TargetPath} {lnk.Arguments}")
            print(f"  工作目录：{lnk.WorkingDirectory}")
        except Exception as exc:
            print(f"  （无法读取快捷方式详情：{exc}）")
    print(f"解释器：{pythonw()}")
    print(f"入口脚本：{target_script()}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Network HUD 开机自启动开关")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--install", action="store_true", help="添加开机自启动")
    g.add_argument("--uninstall", action="store_true", help="移除开机自启动")
    g.add_argument("--status", action="store_true", help="查看当前状态")
    args = ap.parse_args(argv)

    if args.uninstall:
        return uninstall()
    if args.status:
        return status()
    return install()


if __name__ == "__main__":
    raise SystemExit(main())
