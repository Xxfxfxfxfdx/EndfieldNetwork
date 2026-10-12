"""`net_hud/netinfo.py` 的地址解析单测（含 IPv6 的合成用例）。

本机各适配器都没有绑定 IPv6，所以 IPv6 分支无法靠真机覆盖，
这里直接构造 `IP_ADAPTER_UNICAST_ADDRESS` 链表来验证
`_unicast_lists()` 的地址族分派、`SOCKADDR_IN6` 结构布局与文本格式。

    python tools/test_netinfo.py
"""

from __future__ import annotations

import ctypes
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from net_hud import netinfo as N  # noqa: E402

FAILS: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")


def _unicast(family: int, raw: bytes, dad: int = 3):
    """构造一条 `IP_ADAPTER_UNICAST_ADDRESS`（返回保持内存存活的元组）。"""
    if family == N.AF_INET:
        sock = N.SOCKADDR_IN()
        sock.sin_family = family
        sock.sin_addr = (ctypes.c_ubyte * 4).from_buffer_copy(raw)
    elif family == N.AF_INET6:
        sock = N.SOCKADDR_IN6()
        sock.sin6_family = family
        sock.sin6_addr = (ctypes.c_ubyte * 16).from_buffer_copy(raw)
    else:
        raise ValueError(family)

    ptr = ctypes.cast(ctypes.byref(sock), ctypes.c_void_p)
    sa = N.SOCKET_ADDRESS(lpSockaddr=ptr, iSockaddrLength=ctypes.sizeof(sock))
    ua = N.IP_ADAPTER_UNICAST_ADDRESS()
    ua.Address = sa
    ua.DadState = dad
    ua.Next = None
    return sock, ua  # 保持 sock 存活，避免被 GC


def _img(addr6: str) -> bytes:
    return socket.inet_pton(socket.AF_INET6, addr6)


def test_ipv6_format() -> None:
    raw = _img("2408:8214:5B3A:001F:0000:0000:0000:00A1")
    sock, ua = _unicast(N.AF_INET6, raw)
    v4, v6 = N._unicast_lists(ctypes.pointer(ua))
    assert sock is not None
    check("IPv6 列表", v6, ("2408:8214:5b3a:1f::a1",))
    check("IPv4 列表为空", v4, ())
    check("小写十六进制", v6[0], v6[0].lower())


def test_ipv6_dad_filter() -> None:
    raw = _img("2001:db8::1")
    _s, ua = _unicast(N.AF_INET6, raw, dad=N.DAD_TENTATIVE)
    check("DadState=Tentative 被过滤", N._unicast_lists(ctypes.pointer(ua))[1], ())
    _s, ua2 = _unicast(N.AF_INET6, raw, dad=N.DAD_FAILED)
    check("DadState=DadFailed 被过滤", N._unicast_lists(ctypes.pointer(ua2))[1], ())


def test_ipv4_still_ok() -> None:
    sock, ua = _unicast(N.AF_INET, bytes([192, 168, 1, 7]))
    assert sock is not None
    v4, v6 = N._unicast_lists(ctypes.pointer(ua))
    check("IPv4 点分十进制", v4, ("192.168.1.7",))
    check("IPv4 时无 IPv6", v6, ())


def test_display_ip_and_rank() -> None:
    base = dict(name="X", desc="X", if_index=1, if_type=6, oper_status=1)
    only_v6 = N.Adapter(**base, ipv6=("2408:8214:5b3a:1f::a1", "fe80::1"))
    check("优先 IPv4（无 IPv4 时回退 IPv6）", only_v6.display_ip(), "2408:8214:5b3a:1f::a1")
    check("prefer_ipv6 选全局而非链路本地", only_v6.display_ip(True), "2408:8214:5b3a:1f::a1")
    check("链路本地不算真实地址", only_v6.has_real_ip, True)

    link_only = N.Adapter(**base, ipv6=("fe80::abcd",))
    check("只有链路本地 → 无真实地址", link_only.has_real_ip, False)
    check("只有链路本地仍可显示", link_only.display_ip(), "fe80::abcd")

    apipa_v6 = N.Adapter(**base, ipv4=("169.254.1.2",), ipv6=("2408::5",))
    check("APIPA IPv4 + 全局 IPv6 → 显示 IPv6", apipa_v6.display_ip(), "2408::5")
    check("APIPA IPv4 + 全局 IPv6 → has_real_ip", apipa_v6.has_real_ip, True)
    check("prefer_ipv6=True", apipa_v6.display_ip(True), "2408::5")

    both = N.Adapter(**base, ipv4=("192.168.3.51", "169.254.1.2"), ipv6=("2408::5",))
    check("默认优先 IPv4 且跳过 APIPA", both.display_ip(), "192.168.3.51")
    check("prefer_ipv6=True 时选 IPv6", both.display_ip(True), "2408::5")

    apipa = N.Adapter(**base, ipv4=("169.254.38.21",))
    check("只有 APIPA 时仍显示它", apipa.display_ip(), "169.254.38.21")
    check("只有 APIPA → has_real_ip False", apipa.has_real_ip, False)
    check("无地址 → 空串", N.Adapter(**base).display_ip(), "")


def test_live_snapshot() -> None:
    snap = N.snapshot()
    print(f"      （本机适配器 {len(snap)} 个）")
    for name, ad in snap.items():
        print(f"      {name:>16} v4={ad.ipv4} v6={ad.ipv6} show={ad.display_ip()!r}")


def main() -> int:
    test_ipv6_format()
    test_ipv6_dad_filter()
    test_ipv4_still_ok()
    test_display_ip_and_rank()
    test_live_snapshot()
    print()
    if FAILS:
        print(f"{len(FAILS)} 项失败：")
        for f in FAILS:
            print("  -", f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
