"""wlaninfo 解析自测（不依赖真实网卡）。

重点覆盖 SSID 的编码问题：802.11 的 SSID 是裸字节，`netsh wlan show interfaces`
只要遇到非可打印 ASCII 字节就会把它打印成十六进制（如中文 SSID `创新实验室` →
`E5889BE696B0E5AE9EE9AA8CE5AEA4`），而这些字节的字符编码又取决于路由器固件
（多数是 UTF-8，老设备可能是 GBK）。

用法（项目根目录）：
    python tools/test_wlaninfo.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from net_hud import wlaninfo as W  # noqa: E402

PASS = 0
FAIL = 0


def check(label: str, got, want) -> None:
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"OK   {label}")
    else:
        FAIL += 1
        print(f"FAIL {label}\n      得到 {got!r}\n      期望 {want!r}")


# --- 各种 netsh 原始输出（原文，含 \r\n 与中文标签） ------------------------------

#: 中文标签 + 十六进制 SSID（GBK 编码的 netsh 输出，最常见的真实情形）
CN_HEX = """\r
系统上有 1 个接口: \r
\r
    名称                   : WLAN\r
    说明                   : Intel(R) Wi-Fi 6 AX201 160MHz\r
    GUID                   : d7d59a1b-64de-40ee-ac1b-f047fd50e287\r
    物理地址               : 0a:da:42:03:70:19\r
    界面类型               : 主要\r
    状态                   : 已连接\r
    SSID                   : E5889BE696B0E5AE9EE9AA8CE5AEA4\r
    BSSID                  : 42:c2:8a:c2:30:af\r
    网络类型               : 结构\r
    无线电类型             : 802.11ax\r
    身份验证               : WPA2 - 个人\r
    密码                   : CCMP\r
    连接模式               : 配置文件\r
    频带                   : 5 GHz  \r
    通道                   : 40\r
    接收速率(Mbps)         : 2402\r
    传输速率 (Mbps)        : 1201\r
    信号                   : 93%\r
    配置文件               : 创新实验室 \r
\r
    承载网络状态           : 不可用\r
\r
""".encode("gbk")

#: 英文标签 + 纯 ASCII SSID
EN_ASCII = """\r
There is 1 interface on the system: \r
\r
    Name                   : WLAN\r
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz\r
    State                  : connected\r
    SSID                   : 229028\r
    Band                   : 5 GHz\r
    Channel                : 157\r
    Receive rate (Mbps)    : 1081\r
    Transmit rate (Mbps)   : 1201\r
    Signal                 : 92%\r
    Profile                : 229028 \r
\r
""".encode("utf-8")

#: 未连接：SSID 为空且没有 Profile 行
EN_DOWN = """\r
There is 1 interface on the system: \r
\r
    Name                   : WLAN\r
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz\r
    State                  : disconnected\r
    Radio type             : 802.11ax\r
\r
""".encode("utf-8")

#: 十六进制 SSID 无法按 UTF-8/GBK 解出可读文本（模拟固件写入的乱码字节）
EN_BAD_HEX = """\r
There is 1 interface on the system: \r
\r
    Name                   : WLAN\r
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz\r
    State                  : connected\r
    SSID                   : 01FF80FE\r
    Profile                : fallback-name \r
    Signal                 : 50%\r
\r
""".encode("utf-8")

#: GBK 字节的 SSID（老路由器把 GBK 写进 SSID）
CN_GBK_SSID = """\r
There is 1 interface on the system: \r
\r
    Name                   : WLAN\r
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz\r
    State                  : connected\r
    SSID                   : D6D0CEC4\r
    Profile                : 中文 \r
    Signal                 : 70%\r
\r
""".encode("gbk")

#: 两个接口（验证分块）
TWO_IFACES = """\r
There are 2 interfaces on the system: \r
\r
    Name                   : WLAN\r
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz\r
    State                  : connected\r
    SSID                   : 229028\r
    Profile                : 229028 \r
\r
    Name                   : WLAN 2\r
    Description            : USB WLAN\r
    State                  : disconnected\r
\r
""".encode("utf-8")


def with_raw(raw: bytes, fn):
    """把 `_run()` 临时替换成返回固定原文。"""
    old = W._run
    W._run = lambda: raw.decode("utf-8", "replace") if _utf8_ok(raw) else raw.decode("gbk")
    try:
        return fn()
    finally:
        W._run = old


def _utf8_ok(raw: bytes) -> bool:
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def main() -> int:
    print("--- 中文标签 + 十六进制 SSID（GBK 输出）---")
    info = with_raw(CN_HEX, W.query)
    assert info is not None
    check("ssid 还原", info.ssid, "创新实验室")
    check("profile", info.profile, "创新实验室")
    check("name", info.name, "WLAN")
    check("description", info.description, "Intel(R) Wi-Fi 6 AX201 160MHz")
    check("state", info.state, "已连接")
    check("connected", info.connected, True)
    check("frequency_mhz", info.frequency_mhz, 5200)
    check("dbm", info.dbm, -54)
    check("rate_mbps", info.rate_mbps, 2402.0)

    print("--- 英文标签 + ASCII SSID（UTF-8 输出）---")
    info = with_raw(EN_ASCII, W.query)
    assert info is not None
    check("ssid 保持原样", info.ssid, "229028")
    check("channel", info.channel, 157)
    check("frequency_mhz", info.frequency_mhz, 5785)
    check("dbm", info.dbm, -54)

    print("--- 未连接：SSID 为空，不得用 Profile 顶上 ---")
    info = with_raw(EN_DOWN, W.query)
    assert info is not None
    check("ssid 为空", info.ssid, "")
    check("connected", info.connected, False)

    print("--- 十六进制 SSID 解不出文本时回退到 Profile ---")
    info = with_raw(EN_BAD_HEX, W.query)
    assert info is not None
    check("ssid 回退", info.ssid, "fallback-name")

    print("--- SSID 是 GBK 字节 ---")
    info = with_raw(CN_GBK_SSID, W.query)
    assert info is not None
    check("ssid 按 GBK 还原", info.ssid, "中文")

    print("--- 两个接口分块 ---")
    items = with_raw(TWO_IFACES, W.query_all)
    check("接口数", len(items), 2)
    check("第 1 个 name", items[0].name, "WLAN")
    check("第 1 个 ssid", items[0].ssid, "229028")
    check("第 2 个 name", items[1].name, "WLAN 2")
    check("第 2 个 ssid 为空", items[1].ssid, "")
    check("第 2 个 state", items[1].state, "disconnected")

    print("--- decode_ssid 边界 ---")
    check("纯 ASCII 偶数长度十六进制串不被误解码", W.decode_ssid("41424344"), "41424344")
    check("奇数长度十六进制串", W.decode_ssid("1919810"), "1919810")
    check("含非十六进制字符", W.decode_ssid("XHD 5F"), "XHD 5F")
    check("空值 + 回退", W.decode_ssid("", "fallback"), "fallback")
    check("emoji SSID", W.decode_ssid("F09F9880"), "\U0001f600")

    print()
    if FAIL:
        print(f"{PASS} 项通过，{FAIL} 项失败")
        return 1
    print(f"全部通过（{PASS} 项）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
