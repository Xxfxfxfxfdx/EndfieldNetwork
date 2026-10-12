"""NetWatcher 状态机自测：用伪造快照驱动，覆盖 上线/下线/DHCP宽限/忽略 四条路径。

    python tools/test_watcher.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from net_hud import content as C
from net_hud import netinfo
from net_hud import watcher as W

UP = netinfo.IF_OPER_STATUS_UP
DOWN = 2  # IF_OPER_STATUS_DOWN

WIFI_DESC = "Intel(R) Wi-Fi 6 AX201 160MHz"
ETH_DESC = "Realtek PCIe GbE Family Controller"


def ad(name, desc, up, if_type=6, ipv4=()):
    return netinfo.Adapter(
        name=name, desc=desc, if_index=1, if_type=if_type,
        oper_status=UP if up else DOWN, ipv4=tuple(ipv4),
    )


WIFI_DOWN = ad("WLAN", WIFI_DESC, False)
WIFI_APIPA = ad("WLAN", WIFI_DESC, True, netinfo.IF_TYPE_IEEE80211, ("169.254.13.7",))
WIFI_OK = ad("WLAN", WIFI_DESC, True, netinfo.IF_TYPE_IEEE80211, ("192.168.1.7",))
ETH_APIPA = ad("以太网", ETH_DESC, True, 6, ("169.254.9.1",))
ETH_DOWN = ad("以太网", ETH_DESC, False)
WFD = ad("Microsoft Wi-Fi Direct Virtual Adapter", "Microsoft Wi-Fi Direct Virtual Adapter",
         True, netinfo.IF_TYPE_IEEE80211, ("192.168.137.1",))

events: list[tuple] = []
T0 = time.monotonic()
state = {"snap": {}}
failures: list[str] = []


def on_event(ev):
    events.append((round(time.monotonic() - T0, 2), ev.state, ev.adapter.name, ev.adapter.kind))
    content = C.build(ev.state, ev.adapter, ev.wlan)
    # 顺带验证 content 构建不会炸
    assert content.title, "title 为空"


# 用假数据替换真实查询
netinfo.snapshot = lambda: dict(state["snap"])
W.netinfo.snapshot = netinfo.snapshot
W.wlaninfo.query = lambda name="", description="": type(
    "F", (), {"ssid": "TEST", "description": WIFI_DESC, "rx_mbps": 1201.0,
              "frequency_mhz": 5785, "dbm": -54, "rate_mbps": 1201.0}
)()

watcher = W.NetWatcher(on_event, grace=0.8, poll_interval=0.05, min_scan_gap=0.0, ignore=W.DEFAULT_IGNORE)
watcher._prev = {}
watcher._dirty = False


def drive(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        watcher.poll()
        time.sleep(0.01)


def step(label: str, snap: dict, wait: float) -> None:
    state["snap"] = snap
    watcher._dirty = True
    drive(wait)
    print(f"  · {label:<38} poll 后事件数 = {len(events)}")


def expect(label: str, want: list[str]) -> None:
    got = [e[1] for e in events]
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got}" + ("" if ok else f"  期望 {want}"))
    if not ok:
        failures.append(label)


print("NetWatcher 状态机测试（伪造快照）")
step("初始：全部未连接", {"WLAN": WIFI_DOWN, "以太网": ETH_DOWN}, 0.1)
expect("无事件", [])

step("适配器上线但仍是 169.254", {"WLAN": WIFI_APIPA, "以太网": ETH_DOWN}, 0.3)
expect("宽限期内不触发", [])

step("宽限期内拿到真实 IP", {"WLAN": WIFI_OK, "以太网": ETH_DOWN}, 0.3)
expect("连接成功", [C.STATE_CONNECTED])

step("WiFi 掉线", {"WLAN": WIFI_DOWN, "以太网": ETH_DOWN}, 0.3)
expect("断开连接", [C.STATE_CONNECTED, C.STATE_DISCONNECTED])

step("网线上线（169.254）后等到宽限期结束", {"WLAN": WIFI_DOWN, "以太网": ETH_APIPA}, 1.4)
expect("DHCP 异常", [C.STATE_CONNECTED, C.STATE_DISCONNECTED, C.STATE_DHCP_FAILED])

step("网线拔出", {"WLAN": WIFI_DOWN, "以太网": ETH_DOWN}, 0.3)
expect("断开连接", [C.STATE_CONNECTED, C.STATE_DISCONNECTED, C.STATE_DHCP_FAILED, C.STATE_DISCONNECTED])

step("Wi-Fi Direct 虚拟网卡上线（应被忽略）",
     {"WLAN": WIFI_DOWN, "以太网": ETH_DOWN, "wfd": WFD}, 0.4)
expect("忽略虚拟网卡", [C.STATE_CONNECTED, C.STATE_DISCONNECTED, C.STATE_DHCP_FAILED, C.STATE_DISCONNECTED])

step("WiFi 直接上线并已有 IP", {"WLAN": WIFI_OK, "以太网": ETH_DOWN, "wfd": WFD}, 0.3)
expect("连接成功（带 WLAN 详情）",
       [C.STATE_CONNECTED, C.STATE_DISCONNECTED, C.STATE_DHCP_FAILED, C.STATE_DISCONNECTED,
        C.STATE_CONNECTED])

last = events[-1]
print(f"  最后事件携带 wlan={last[3]}")
content = C.build(C.STATE_CONNECTED, WIFI_OK, watcher._prev and None)
print()
print("事件时间线：")
for e in events:
    print("   ", e)
print()
if failures:
    print(f"FAILED: {failures}")
    raise SystemExit(1)
print("全部通过")
