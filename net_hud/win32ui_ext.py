"""Win32 分层窗口（UpdateLayeredWindow）——每帧直接推一张预乘 alpha 的 BGRA 位图。

不使用 tkinter：`-transparentcolor` 色键方案会有锯齿与毛边，而
`UpdateLayeredWindow` + `AC_SRC_ALPHA` 提供真正的逐像素 alpha。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

from PIL import Image

__all__ = ["LayeredWindow", "set_dpi_awareness", "system_dpi", "primary_work_area"]

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --- 常量 ---------------------------------------------------------------
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020

SW_SHOWNOACTIVATE = 4
SW_HIDE = 0
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_MOUSEACTIVATE = 0x0021
MA_NOACTIVATE = 3
PM_REMOVE = 0x0001

CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
IDC_ARROW = 32512

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm", wt.HICON),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class RGBQUAD(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", ctypes.c_ubyte),
        ("rgbGreen", ctypes.c_ubyte),
        ("rgbRed", ctypes.c_ubyte),
        ("rgbReserved", ctypes.c_ubyte),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 1)]


# --- 原型 ---------------------------------------------------------------
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterClassExW.restype = wt.WORD
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.UpdateLayeredWindow.restype = wt.BOOL
user32.UpdateLayeredWindow.argtypes = [
    wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE),
    wt.HDC, ctypes.POINTER(wt.POINT), wt.DWORD,
    ctypes.POINTER(BLENDFUNCTION), wt.DWORD,
]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
    ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD,
]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.SelectObject.restype = wt.HANDLE
gdi32.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
gdi32.DeleteObject.restype = wt.BOOL
gdi32.DeleteObject.argtypes = [wt.HANDLE]
gdi32.DeleteDC.restype = wt.BOOL
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.GetDeviceCaps.restype = ctypes.c_int
gdi32.GetDeviceCaps.argtypes = [wt.HDC, ctypes.c_int]

user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.LoadCursorW.restype = wt.HANDLE
user32.LoadCursorW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]
user32.ShowWindow.restype = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.DestroyWindow.restype = wt.BOOL
user32.DestroyWindow.argtypes = [wt.HWND]
user32.SetWindowPos.restype = wt.BOOL
user32.SetWindowPos.argtypes = [
    wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wt.UINT,
]
user32.PeekMessageW.restype = wt.BOOL
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT,
]
user32.TranslateMessage.restype = wt.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterClassExW.restype = wt.WORD
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]
user32.UpdateLayeredWindow.restype = wt.BOOL
user32.UpdateLayeredWindow.argtypes = [
    wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE),
    wt.HDC, ctypes.POINTER(wt.POINT), wt.DWORD,
    ctypes.POINTER(BLENDFUNCTION), wt.DWORD,
]
user32.MonitorFromPoint.restype = wt.HANDLE
user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
user32.GetMonitorInfoW.restype = wt.BOOL
user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.c_void_p]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetDpiForSystem.restype = wt.UINT
user32.GetDpiForSystem.argtypes = []
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]


def set_dpi_awareness() -> bool:
    """Per-Monitor v2 DPI 感知；失败时回退到 process/system 感知。"""
    try:
        if user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return True
    except (AttributeError, OSError):
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return True
    except (AttributeError, OSError):
        pass
    try:
        user32.SetProcessDPIAware()
        return True
    except (AttributeError, OSError):
        return False


def system_dpi() -> int:
    """主显示器 DPI（96 = 100%）。"""
    try:
        return int(user32.GetDpiForSystem())
    except (AttributeError, OSError):
        hdc = user32.GetDC(None)
        try:
            return int(gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
        finally:
            user32.ReleaseDC(None, hdc)


def primary_work_area() -> tuple[int, int, int, int]:
    """主显示器工作区 (left, top, right, bottom)，物理像素。"""

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long), ("top", ctypes.c_long),
            ("right", ctypes.c_long), ("bottom", ctypes.c_long),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wt.DWORD), ("rcMonitor", RECT),
            ("rcWork", RECT), ("dwFlags", wt.DWORD),
        ]

    MONITOR_DEFAULTTOPRIMARY = 1
    hmon = user32.MonitorFromPoint(wt.POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        r = mi.rcWork
        return r.left, r.top, r.right, r.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _to_premultiplied_bgra(img: Image.Image) -> bytes:
    """PIL 的 straight-alpha RGBA → UpdateLayeredWindow 需要的预乘 BGRA。"""
    data = img.tobytes("raw", "RGBA")
    n = len(data)
    buf = bytearray(n)
    mv = memoryview(data)
    for i in range(0, n, 4):
        a = mv[i + 3]
        if a == 255:
            buf[i] = mv[i + 2]
            buf[i + 1] = mv[i + 1]
            buf[i + 2] = mv[i]
            buf[i + 3] = 255
        elif a:
            buf[i] = (mv[i + 2] * a + 127) // 255
            buf[i + 1] = (mv[i + 1] * a + 127) // 255
            buf[i + 2] = (mv[i] * a + 127) // 255
            buf[i + 3] = a
    return bytes(buf)


def premultiplied_bgra_numpy(img: Image.Image):
    """同 `_to_premultiplied_bgra`，但走 numpy（快 ~10×）。"""
    import numpy as np

    arr = np.asarray(img, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] != 4:
        raise ValueError("需要 RGBA 图像")
    a = arr[:, :, 3].astype(np.uint16)
    out = np.empty(arr.shape, dtype=np.uint8)
    for src, dst in ((2, 0), (1, 1), (0, 2)):  # R→B, G→G, B→R
        out[:, :, dst] = ((arr[:, :, src].astype(np.uint16) * a + 127) // 255).astype(
            np.uint8
        )
    out[:, :, 3] = arr[:, :, 3]
    return np.ascontiguousarray(out)


class LayeredWindow:
    """无边框、置顶、不抢焦点的分层弹出窗口。

    `on_click` / `on_right_click` 在窗口收到对应消息时被调用（无参数）。
    """

    _class_seq = 0
    _wndproc_refs: list = []

    def __init__(self, width: int, height: int, *, title: str = "NetworkHUD",
                 on_click=None, on_right_click=None):
        self.width = int(width)
        self.height = int(height)
        self.on_click = on_click
        self.on_right_click = on_right_click
        self._visible = False
        self._memdc = None
        self._dib = None
        self._old_bitmap = None
        self._bits = ctypes.c_void_p()
        self._buf = None

        LayeredWindow._class_seq += 1
        self._class_name = f"NetHudLayeredWnd_{id(self):x}_{LayeredWindow._class_seq}"

        self._wndproc = WNDPROC(self._proc)
        LayeredWindow._wndproc_refs.append(self._wndproc)

        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = CS_HREDRAW | CS_VREDRAW
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, IDC_ARROW)
        wc.lpszClassName = self._class_name
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())

        ex_style = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = user32.CreateWindowExW(
            ex_style, self._class_name, title, WS_POPUP,
            0, 0, self.width, self.height,
            None, None, hinst, None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        self._create_dib()

    # -- DIB ------------------------------------------------------------
    def _create_dib(self) -> None:
        screen_dc = user32.GetDC(None)
        self._memdc = gdi32.CreateCompatibleDC(screen_dc)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = self.width
        bmi.bmiHeader.biHeight = -self.height  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        self._dib = gdi32.CreateDIBSection(
            screen_dc, ctypes.byref(bmi), DIB_RGB_COLORS,
            ctypes.byref(self._bits), None, 0,
        )
        user32.ReleaseDC(None, screen_dc)
        if not self._dib:
            raise ctypes.WinError(ctypes.get_last_error())
        self._old_bitmap = gdi32.SelectObject(self._memdc, self._dib)
        self._buf = (ctypes.c_char * (self.width * self.height * 4)).from_address(
            self._bits.value
        )

    def resize(self, width: int, height: int) -> None:
        width, height = int(width), int(height)
        if (width, height) == (self.width, self.height):
            return
        self._release_dib()
        self.width, self.height = width, height
        user32.SetWindowPos(
            self.hwnd, None, 0, 0, width, height,
            SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOZORDER,
        )
        self._create_dib()

    def _release_dib(self) -> None:
        if self._memdc and self._old_bitmap:
            gdi32.SelectObject(self._memdc, self._old_bitmap)
        if self._dib:
            gdi32.DeleteObject(self._dib)
        if self._memdc:
            gdi32.DeleteDC(self._memdc)
        self._memdc = self._dib = self._old_bitmap = None
        self._bits = ctypes.c_void_p()
        self._buf = None

    # -- 绘制 -----------------------------------------------------------
    def present(self, img: Image.Image, x: int, y: int) -> None:
        """把 RGBA 图像推到 (x, y)（屏幕物理像素）。"""
        w, h = img.size
        if (w, h) != (self.width, self.height):
            self.resize(w, h)
        data = premultiplied_bgra_numpy(img).tobytes()
        ctypes.memmove(self._buf, data, len(data))

        dst = wt.POINT(int(x), int(y))
        size = wt.SIZE(self.width, self.height)
        src = wt.POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        if not user32.UpdateLayeredWindow(
            self.hwnd, None, ctypes.byref(dst), ctypes.byref(size),
            self._memdc, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA,
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def move(self, x: int, y: int) -> None:
        user32.SetWindowPos(
            self.hwnd, HWND_TOPMOST, int(x), int(y), 0, 0,
            SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def show(self) -> None:
        if not self._visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self._visible = True

    def hide(self) -> None:
        if self._visible:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            self._visible = False

    @property
    def visible(self) -> bool:
        return self._visible

    def destroy(self) -> None:
        try:
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None
        finally:
            self._release_dib()

    # -- 消息 -----------------------------------------------------------
    def pump(self) -> bool:
        """处理所有待处理消息；收到 WM_QUIT 返回 False。"""
        msg = wt.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            if msg.message == 0x0012:  # WM_QUIT
                return False
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        return True

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_LBUTTONUP:
            if self.on_click:
                self.on_click()
            return 0
        if msg == WM_RBUTTONUP:
            if self.on_right_click:
                self.on_right_click()
            return 0
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_CLOSE:
            self.hide()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
