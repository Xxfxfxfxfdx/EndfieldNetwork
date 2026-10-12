"""网络适配器状态监听。

* 即时事件：`NotifyIpInterfaceChange`（iphlpapi）在任何接口/地址变化时回调；
* 兜底轮询：每 `poll_interval` 秒全量 `snapshot()` 一次（对应原项目的 2s 轮询）；
* DHCP 宽限：断开→已连接时若 IP 仍为 169.254，最多等 `grace` 秒，
  期间一拿到真实 IP 就立刻报 `connected`，超时则报 `dhcp_failed`。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import time
from dataclasses import dataclass, field

from . import content as C
from . import netinfo, wlaninfo

log = logging.getLogger("net_hud.watcher")

__all__ = ["NetWatcher", "AdapterEvent"]

#: 默认忽略的虚拟适配器（名称或描述命中即忽略，全部小写）
DEFAULT_IGNORE: tuple[str, ...] = (
    "microsoft wi-fi direct virtual adapter",
    "wi-fi direct",
)

AF_UNSPEC = 0

_CALLBACK = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)

_iphlpapi = ctypes.WinDLL("iphlpapi")
_iphlpapi.NotifyIpInterfaceChange.restype = wt.DWORD
_iphlpapi.NotifyIpInterfaceChange.argtypes = [
    ctypes.c_int, _CALLBACK, ctypes.c_void_p, ctypes.c_ubyte,
    ctypes.POINTER(ctypes.c_void_p),
]
_iphlpapi.CancelMibChangeNotify2.restype = wt.DWORD
_iphlpapi.CancelMibChangeNotify2.argtypes = [ctypes.c_void_p]


@dataclass
class AdapterEvent:
    """一次状态变化。"""

    state: str
    adapter: object
    wlan: object = None
    at: float = field(default_factory=time.time)

    @property
    def kind(self) -> str:
        return getattr(self.adapter, "kind", "other")


@dataclass
class _Pending:
    adapter: object
    deadline: float


class NetWatcher:
    def __init__(
        self,
        on_event,
        *,
        grace: float = 10.0,
        poll_interval: float = 2.0,
        ignore: tuple[str, ...] = DEFAULT_IGNORE,
        min_scan_gap: float = 0.25,
    ) -> None:
        self.on_event = on_event
        self.grace = max(0.0, float(grace))
        self.poll_interval = max(0.3, float(poll_interval))
        self.ignore = tuple(p.lower() for p in ignore)
        self.min_scan_gap = max(0.0, float(min_scan_gap))

        self._prev: dict | None = None
        self._pending: dict[str, _Pending] = {}
        self._handle = ctypes.c_void_p()
        self._cb = None
        self._last_scan = 0.0
        self._last_poll = 0.0
        self._dirty = True
        self._changes = 0

    # ------------------------------------------------------------ 生命周期

    def start(self) -> bool:
        self._prev = netinfo.snapshot()
        try:
            self._cb = _CALLBACK(self._on_notify)
            if _iphlpapi.NotifyIpInterfaceChange(
                AF_UNSPEC, self._cb, None, False, ctypes.byref(self._handle)
            ) == 0:
                log.info("已注册 NotifyIpInterfaceChange 即时通知")
                return True
        except Exception as exc:  # pragma: no cover
            log.warning("NotifyIpInterfaceChange 注册失败：%s", exc)
        self._cb = None
        log.info("使用纯轮询模式（%.1fs）", self.poll_interval)
        return False

    def stop(self) -> None:
        if self._handle:
            try:
                _iphlpapi.CancelMibChangeNotify2(self._handle)
            except Exception:
                pass
            self._handle = ctypes.c_void_p()
        self._cb = None

    # ------------------------------------------------------------ 回调

    def _on_notify(self, _ctx, _row, _type) -> None:  # 系统线程
        self._dirty = True

    # ------------------------------------------------------------ 主循环

    def poll(self) -> None:
        now = time.monotonic()
        want = self._dirty or (now - self._last_poll) >= self.poll_interval
        if want and (now - self._last_scan) >= self.min_scan_gap:
            self._dirty = False
            self._last_poll = now
            self._last_scan = now
            self._scan(now)
        self._check_pending(time.monotonic())

    # ------------------------------------------------------------ 扫描

    def _scan(self, now: float) -> None:
        try:
            cur = netinfo.snapshot()
        except Exception as exc:  # pragma: no cover
            log.warning("snapshot 失败：%s", exc)
            return
        prev, self._prev = self._prev, cur
        if prev is None:
            return
        for name, adapter in cur.items():
            if self._ignored(adapter):
                continue
            old = prev.get(name)
            was_up = bool(old and old.up)
            if adapter.up and not was_up:
                log.info("适配器上线：%s (%s)", name, adapter.desc)
                self._handle_connect(adapter, now)
            elif was_up and not adapter.up:
                log.info("适配器下线：%s (%s)", name, adapter.desc)
                self._pending.pop(name, None)
                self._emit(C.STATE_DISCONNECTED, adapter)

    def _ignored(self, adapter) -> bool:
        hay = f"{getattr(adapter, 'name', '')} {getattr(adapter, 'desc', '')}".lower()
        return any(p in hay for p in self.ignore)

    # ------------------------------------------------------ DHCP 宽限

    def _handle_connect(self, adapter, now: float) -> None:
        if adapter.has_real_ip:
            self._emit(C.STATE_CONNECTED, adapter)
            return
        self._pending[adapter.name] = _Pending(adapter, now + self.grace)
        log.info(
            "%s 已连接但 IP 仍为 %s，%.0fs 内等待 DHCP",
            adapter.name, adapter.primary_ipv4 or "(无)", self.grace,
        )

    def _check_pending(self, now: float) -> None:
        if not self._pending:
            return
        latest = None
        if self._pending:
            try:
                latest = netinfo.snapshot()
            except Exception:
                latest = None
        for name, pend in list(self._pending.items()):
            adapter = (latest or {}).get(name, pend.adapter)
            if not adapter.up:
                del self._pending[name]
                continue
            if adapter.has_real_ip:
                del self._pending[name]
                log.info("%s 在宽限期内拿到 IP %s", name, adapter.primary_ipv4)
                self._emit(C.STATE_CONNECTED, adapter)
            elif now >= pend.deadline:
                del self._pending[name]
                log.info("%s 宽限期结束仍是 169.254", name)
                self._emit(C.STATE_DHCP_FAILED, adapter)
        if latest is not None:
            self._prev = latest

    # ------------------------------------------------------------ 事件

    def _emit(self, state: str, adapter) -> None:
        self._changes += 1
        wlan = None
        if state == C.STATE_CONNECTED and getattr(adapter, "kind", "") == "wifi":
            try:
                wlan = wlaninfo.query(
                    name=getattr(adapter, "name", ""),
                    description=getattr(adapter, "desc", ""),
                )
            except Exception as exc:
                log.warning("读取 WLAN 详情失败：%s", exc)
        event = AdapterEvent(state=state, adapter=adapter, wlan=wlan)
        try:
            self.on_event(event)
        except Exception:  # pragma: no cover
            log.exception("处理网络事件时出错")

    # ------------------------------------------------------------ 查询

    @property
    def changes(self) -> int:
        return self._changes

    def current(self) -> dict:
        """当前快照（必要时刷新）。"""
        try:
            self._prev = netinfo.snapshot()
        except Exception:
            pass
        return self._prev or {}

    def interesting(self):
        """挑一个最能代表当前状态的适配器：优先已连接的、按优先级排序。"""
        snap = self.current()
        order = {"wifi": 0, "ethernet": 1, "usb_rndis": 2, "btpan": 3, "other": 4}
        up = [a for a in snap.values() if a.up and not self._ignored(a)]
        up.sort(key=lambda a: (order.get(a.kind, 9), a.name))
        if up:
            return up[0]
        rest = [a for a in snap.values() if not self._ignored(a)]
        rest.sort(key=lambda a: (order.get(a.kind, 9), a.name))
        return rest[0] if rest else None
