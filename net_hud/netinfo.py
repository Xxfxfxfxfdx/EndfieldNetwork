"""网络适配器枚举与分类（IP Helper API，无子进程）。

分类规则（用户指定）：
* 名称/描述含 WLAN / Wi-Fi / 802.11 / 无线 → `wifi`
* 含 Bluetooth / 蓝牙 → `btpan`
* 名称含「以太网」且同时含 `NDIS` → `usb_rndis`；含 `NDIS` 的其它情况同样按 RNDIS
* 其余含 Ethernet / 以太网 / GbE → `ethernet`
"""

from __future__ import annotations

import ctypes
import ipaddress
import socket
from ctypes import wintypes
from dataclasses import dataclass

__all__ = ["Adapter", "snapshot", "KIND_LABELS", "KIND_LOGO"]

AF_UNSPEC = 0
AF_INET = 2
AF_INET6 = 23
GAA_FLAG_SKIP_ANYCAST = 0x0002
GAA_FLAG_SKIP_MULTICAST = 0x0004
GAA_FLAG_SKIP_DNS_SERVER = 0x0008
GAA_FLAG_INCLUDE_PREFIX = 0x0010
ERROR_BUFFER_OVERFLOW = 111

IF_OPER_STATUS_UP = 1
IF_TYPE_SOFTWARE_LOOPBACK = 24
IF_TYPE_IEEE80211 = 71
IF_TYPE_TUNNEL = 131

#: `IP_ADAPTER_UNICAST_ADDRESS.DadState`
DAD_TENTATIVE = 1
DAD_FAILED = 4

KIND_LABELS = {
    "wifi": "WLAN",
    "ethernet": "以太网",
    "btpan": "蓝牙 PAN",
    "usb_rndis": "USB RNDIS",
    "other": "其它",
}

KIND_LOGO = {
    "wifi": "wifi",
    "ethernet": "ethernet",
    "btpan": "btpan",
    "usb_rndis": "usb_rndis",
    "other": "nointernet",
}

APIPA_PREFIX = "169.254."


class SOCKET_ADDRESS(ctypes.Structure):
    _fields_ = [("lpSockaddr", ctypes.c_void_p), ("iSockaddrLength", ctypes.c_int)]


class IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
    pass


IP_ADAPTER_UNICAST_ADDRESS._fields_ = [
    ("Length", wintypes.ULONG),
    ("Flags", wintypes.DWORD),
    ("Next", ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
    ("Address", SOCKET_ADDRESS),
    ("PrefixOrigin", ctypes.c_int),
    ("SuffixOrigin", ctypes.c_int),
    ("DadState", ctypes.c_int),
    ("ValidLifetime", wintypes.ULONG),
    ("PreferredLifetime", wintypes.ULONG),
    ("LeaseLifetime", wintypes.ULONG),
    ("OnLinkPrefixLength", ctypes.c_ubyte),
]


class IP_ADAPTER_ADDRESSES(ctypes.Structure):
    pass


IP_ADAPTER_ADDRESSES._fields_ = [
    ("Length", wintypes.ULONG),
    ("IfIndex", wintypes.DWORD),
    ("Next", ctypes.POINTER(IP_ADAPTER_ADDRESSES)),
    ("AdapterName", ctypes.c_char_p),
    ("FirstUnicastAddress", ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
    ("FirstAnycastAddress", ctypes.c_void_p),
    ("FirstMulticastAddress", ctypes.c_void_p),
    ("FirstDnsServerAddress", ctypes.c_void_p),
    ("DnsSuffix", wintypes.LPWSTR),
    ("Description", wintypes.LPWSTR),
    ("FriendlyName", wintypes.LPWSTR),
    ("PhysicalAddress", ctypes.c_ubyte * 8),
    ("PhysicalAddressLength", wintypes.DWORD),
    ("Flags", wintypes.DWORD),
    ("Mtu", wintypes.DWORD),
    ("IfType", wintypes.DWORD),
    ("OperStatus", ctypes.c_int),
    ("Ipv6IfIndex", wintypes.DWORD),
    ("ZoneIndices", wintypes.DWORD * 16),
    ("FirstPrefix", ctypes.c_void_p),
    ("TransmitLinkSpeed", ctypes.c_ulonglong),
    ("ReceiveLinkSpeed", ctypes.c_ulonglong),
]


class SOCKADDR_IN(ctypes.Structure):
    _fields_ = [
        ("sin_family", ctypes.c_ushort),
        ("sin_port", ctypes.c_ushort),
        ("sin_addr", ctypes.c_ubyte * 4),
        ("sin_zero", ctypes.c_ubyte * 8),
    ]


class SOCKADDR_IN6(ctypes.Structure):
    _fields_ = [
        ("sin6_family", ctypes.c_ushort),
        ("sin6_port", ctypes.c_ushort),
        ("sin6_flowinfo", ctypes.c_ulong),
        ("sin6_addr", ctypes.c_ubyte * 16),
        ("sin6_scope_id", ctypes.c_ulong),
    ]


_iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
_iphlpapi.GetAdaptersAddresses.restype = wintypes.ULONG


@dataclass(frozen=True)
class Adapter:
    name: str
    desc: str
    if_index: int
    if_type: int
    oper_status: int
    mac: str = ""
    ipv4: tuple[str, ...] = ()
    receive_bps: int = 0
    transmit_bps: int = 0
    ipv6: tuple[str, ...] = ()

    @property
    def up(self) -> bool:
        return self.oper_status == IF_OPER_STATUS_UP

    @property
    def kind(self) -> str:
        return classify(self.name, self.desc, self.if_type)

    @property
    def apipa(self) -> bool:
        """是否只有 169.254.x.x（DHCP 未拿到地址）。"""
        return bool(self.ipv4) and all(ip.startswith(APIPA_PREFIX) for ip in self.ipv4)

    @property
    def real_ipv4(self) -> tuple[str, ...]:
        return tuple(ip for ip in self.ipv4 if not ip.startswith(APIPA_PREFIX))

    @property
    def has_real_ip(self) -> bool:
        """是否有可用地址（非 APIPA 的 IPv4，或非链路本地的 IPv6）。"""
        if self.real_ipv4:
            return True
        return any(_ipv6_rank(ip) < 2 for ip in self.ipv6)

    @property
    def primary_ipv4(self) -> str:
        for ip in self.ipv4:
            if not ip.startswith(APIPA_PREFIX):
                return ip
        return self.ipv4[0] if self.ipv4 else ""

    @property
    def primary_ipv6(self) -> str:
        """最有代表性的 IPv6：全局/ULA 优先，其次链路本地。"""
        if not self.ipv6:
            return ""
        return min(self.ipv6, key=lambda ip: (_ipv6_rank(ip), len(ip)))

    def display_ip(self, prefer_ipv6: bool = False) -> str:
        """用于显示的 IP 地址文本。

        不带 "IP" 前缀；IPv4 为点分十进制，IPv6 为**小写**冒号十六进制
        （由 `socket.inet_ntop` 给出，已去掉 `%scope` 后缀）。
        """
        real4 = self.real_ipv4
        v6 = self.primary_ipv6
        v4 = real4[0] if real4 else ""
        if prefer_ipv6:
            return v6 or v4 or (self.ipv4[0] if self.ipv4 else "")
        return v4 or v6 or (self.ipv4[0] if self.ipv4 else "")


def _ipv6_rank(ip: str) -> int:
    """IPv6 优先级：0 全局，1 ULA/其它，2 链路本地，3 不可用。"""
    try:
        a = ipaddress.IPv6Address(ip.split("%")[0])
    except ValueError:
        return 3
    if a.is_link_local:
        return 2
    if a.is_loopback or a.is_multicast or a.is_unspecified:
        return 3
    return 0 if a.is_global else 1


def classify(name: str, desc: str, if_type: int = 0) -> str:
    text = f"{name} {desc}"
    low = text.lower()
    if if_type == IF_TYPE_IEEE80211:
        return "wifi"
    if any(k in low for k in ("wlan", "wi-fi", "wifi", "wireless", "802.11")) or "无线" in text:
        return "wifi"
    if "bluetooth" in low or "蓝牙" in text:
        return "btpan"
    # 用户规则：名称含「以太网」且含 NDIS → RNDIS；含 NDIS 的其它设备同理
    if "ndis" in low:
        return "usb_rndis"
    if any(k in low for k in ("ethernet", "gbe", "802.3")) or "以太网" in text:
        return "ethernet"
    return "other"


def _unicast_lists(first) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """返回 `(IPv4 列表, IPv6 列表)`。"""
    v4: list[str] = []
    v6: list[str] = []
    node = first
    while node:
        addr = node.contents
        sa = addr.Address
        if sa.lpSockaddr:
            fam = ctypes.cast(sa.lpSockaddr, ctypes.POINTER(ctypes.c_ushort))[0]
            if fam == AF_INET:
                sin = ctypes.cast(sa.lpSockaddr, ctypes.POINTER(SOCKADDR_IN)).contents
                v4.append(socket.inet_ntoa(bytes(sin.sin_addr)))
            elif fam == AF_INET6 and int(addr.DadState) not in (DAD_TENTATIVE, DAD_FAILED):
                sin6 = ctypes.cast(sa.lpSockaddr, ctypes.POINTER(SOCKADDR_IN6)).contents
                try:
                    txt = socket.inet_ntop(socket.AF_INET6, bytes(sin6.sin6_addr))
                except (OSError, ValueError):
                    txt = ""
                if txt:
                    v6.append(txt.lower().split("%")[0])
        node = addr.Next
    return tuple(v4), tuple(v6)


def snapshot() -> dict[str, Adapter]:
    """枚举全部适配器，按 FriendlyName 索引。"""
    flags = (
        GAA_FLAG_INCLUDE_PREFIX
        | GAA_FLAG_SKIP_ANYCAST
        | GAA_FLAG_SKIP_MULTICAST
        | GAA_FLAG_SKIP_DNS_SERVER
    )
    size = wintypes.ULONG(16 * 1024)
    buf = ctypes.create_string_buffer(size.value)
    ret = _iphlpapi.GetAdaptersAddresses(AF_UNSPEC, flags, None, buf, ctypes.byref(size))
    if ret == ERROR_BUFFER_OVERFLOW:
        buf = ctypes.create_string_buffer(size.value)
        ret = _iphlpapi.GetAdaptersAddresses(AF_UNSPEC, flags, None, buf, ctypes.byref(size))
    if ret != 0:
        raise OSError(f"GetAdaptersAddresses failed: {ret}")

    result: dict[str, Adapter] = {}
    node = ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES))
    while node:
        a = node.contents
        name = a.FriendlyName or ""
        desc = a.Description or ""
        if a.IfType in (IF_TYPE_SOFTWARE_LOOPBACK, IF_TYPE_TUNNEL):
            node = a.Next
            continue
        mac = ":".join(f"{b:02X}" for b in a.PhysicalAddress[: a.PhysicalAddressLength])
        addrs4, addrs6 = _unicast_lists(a.FirstUnicastAddress)
        result[name] = Adapter(
            name=name,
            desc=desc,
            if_index=int(a.IfIndex),
            if_type=int(a.IfType),
            oper_status=int(a.OperStatus),
            mac=mac,
            ipv4=addrs4,
            receive_bps=int(a.ReceiveLinkSpeed),
            transmit_bps=int(a.TransmitLinkSpeed),
            ipv6=addrs6,
        )
        node = a.Next
    return result


def format_speed(bps: int) -> tuple[str, str]:
    """链路速率 → (数值, 单位)。"""
    if bps <= 0 or bps > 10**15:  # 无效速率为 0xFFFFFFFFFFFFFFFF
        return "-", "Mbps"
    mbps = bps / 1_000_000.0
    if mbps >= 1000.0:
        return f"{mbps / 1000.0:.1f}", "Gbps"
    if mbps >= 100.0:
        return f"{mbps:.0f}", "Mbps"
    return f"{mbps:.1f}", "Mbps"


if __name__ == "__main__":  # pragma: no cover - 手工核对用
    for ad in snapshot().values():
        print(
            f"{ad.name!r:32} up={ad.up!s:5} kind={ad.kind:9} "
            f"ifType={ad.if_type:3} ipv4={ad.ipv4} ipv6={ad.ipv6} "
            f"show={ad.display_ip()!r} speed={format_speed(ad.receive_bps)} "
            f"desc={ad.desc!r}"
        )
