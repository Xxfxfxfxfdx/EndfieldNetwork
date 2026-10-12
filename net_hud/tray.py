"""任务栏托盘图标 + 右键菜单（pywin32 `Shell_NotifyIcon`）。

用一个 message-only 窗口接收托盘回调消息；左键单击 = 播放一次预览动画，
右键 = 弹出菜单（预览 / 打开日志 / 重新加载 / 退出）。
"""

from __future__ import annotations

import ctypes
import os

from .win32ui_ext import (
    CS_HREDRAW,
    CS_VREDRAW,
    IDC_ARROW,
    WNDCLASSEXW,
    WNDPROC,
    kernel32,
    user32,
)

__all__ = ["TrayIcon", "make_tray_icon"]

WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_COMMAND = 0x0111
WM_NULL = 0x0000

HWND_MESSAGE = ctypes.c_void_p(-3)

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203


def make_tray_icon(path: str | None = None, size: int = 32) -> str:
    """用 assets 里的 wifi logo 生成一个托盘 .ico，返回路径。

    配色沿用主题：强调色底 + 深色字形，浅色/深色任务栏都能看清。
    """
    from PIL import Image, ImageDraw

    from . import theme as T
    from .logos import load_mask

    if path is None:
        path = os.path.join(
            os.environ.get("TEMP", "."), "NetworkHUD", "tray.ico"
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)

    images = []
    for px in sorted({16, 20, 24, 32, 48, 64}):
        ss = 8
        side = px * ss
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle(
            (0, 0, side - 1, side - 1), radius=int(side * 0.22),
            fill=T.ACCENT + (255,),
        )
        box = int(side * 0.60)
        mask = load_mask("wifi")
        mw, mh = mask.size
        sc = min(box / mw, box / mh)
        nw, nh = max(1, int(mw * sc)), max(1, int(mh * sc))
        glyph = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
        glyph.putalpha(mask.resize((nw, nh), Image.LANCZOS))
        tinted = Image.new("RGBA", (nw, nh), T.PLATE + (0,))
        tinted.putalpha(glyph.getchannel("A"))
        canvas.alpha_composite(tinted, ((side - nw) // 2, (side - nh) // 2))
        images.append(canvas.resize((px, px), Image.LANCZOS))

    images[0].save(path, format="ICO", sizes=[im.size for im in images])
    return path


class TrayIcon:
    """托盘图标。`items` 为 (命令 id, 菜单文字) 列表，None 表示分隔线。"""

    _seq = 0
    _refs: list = []

    def __init__(
        self,
        *,
        tooltip: str = "网络状态监测 HUD",
        icon_path: str | None = None,
        items: tuple = (),
        handlers: dict | None = None,
        on_activate=None,
    ) -> None:
        self.tooltip = tooltip[:127]
        self.items = items
        self.handlers = handlers or {}
        self.on_activate = on_activate
        self._added = False
        self._hicon = None
        self.icon_path = icon_path or make_tray_icon()

        TrayIcon._seq += 1
        self._class_name = f"NetHudTray_{id(self):x}_{TrayIcon._seq}"
        self._proc_ref = WNDPROC(self._proc)
        TrayIcon._refs.append(self._proc_ref)

        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = CS_HREDRAW | CS_VREDRAW
        wc.lpfnWndProc = self._proc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, IDC_ARROW)
        wc.lpszClassName = self._class_name
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd = user32.CreateWindowExW(
            0, self._class_name, "NetworkHUD Tray", 0,
            0, 0, 0, 0, HWND_MESSAGE, None, hinst, None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

    # ------------------------------------------------------------ 图标

    def add(self) -> bool:
        if self._added:
            return True
        try:
            import win32con
            import win32gui

            self._hicon = win32gui.LoadImage(
                0, self.icon_path, win32con.IMAGE_ICON, 0, 0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
            )
            nid = (
                self.hwnd, 1, NIF_MESSAGE | NIF_ICON | NIF_TIP,
                WM_TRAYICON, self._hicon, self.tooltip,
            )
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
            self._added = True
        except Exception:
            self._added = False
        return self._added

    def set_tooltip(self, text: str) -> None:
        self.tooltip = text[:127]
        if not self._added:
            return
        try:
            import win32gui

            win32gui.Shell_NotifyIcon(
                win32gui.NIM_MODIFY,
                (self.hwnd, 1, NIF_TIP, WM_TRAYICON, self._hicon, self.tooltip),
            )
        except Exception:
            pass

    def remove(self) -> None:
        if not self._added:
            return
        try:
            import win32gui

            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 1))
        except Exception:
            pass
        self._added = False

    def destroy(self) -> None:
        self.remove()
        try:
            if self._hicon:
                import win32gui

                win32gui.DestroyIcon(self._hicon)
                self._hicon = None
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None
        except Exception:
            pass

    # ------------------------------------------------------------ 菜单

    def _popup(self) -> None:
        try:
            import win32con
            import win32gui
        except Exception:
            return
        menu = win32gui.CreatePopupMenu()
        for entry in self.items:
            if entry is None:
                win32gui.AppendMenu(menu, MF_SEPARATOR, 0, "")
            else:
                cmd, label = entry
                win32gui.AppendMenu(menu, MF_STRING, cmd, label)
        x, y = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        cmd = win32gui.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, x, y, 0, self.hwnd, None
        )
        win32gui.PostMessage(self.hwnd, WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)
        if cmd:
            self.invoke(cmd)

    def invoke(self, cmd: int) -> None:
        fn = self.handlers.get(cmd)
        if fn:
            fn()

    # ------------------------------------------------------------ 消息

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam in (WM_RBUTTONUP, WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                if lparam == WM_RBUTTONUP:
                    self._popup()
                elif self.on_activate:
                    self.on_activate()
            return 0
        if msg == WM_COMMAND:
            self.invoke(wparam & 0xFFFF)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
