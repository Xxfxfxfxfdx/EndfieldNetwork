"""WLAN 详情（SSID / 频率 / 速率 / 信号）—— 解析 `netsh wlan show interfaces`。

同时兼容英文与中文标签（英文：Name/Description/State/SSID/Band/Channel/
Receive rate (Mbps)/Signal；中文：名称/描述/状态/SSID/频带/通道/接收速率(Mbps)/信号）。
"""

from __future__ import annotations

import ctypes
import re
import subprocess
from dataclasses import dataclass

__all__ = ["WlanInfo", "query", "query_all", "frequency_mhz", "signal_to_dbm", "decode_ssid"]

_LINE_RE = re.compile(r"^\s*(?P<key>[^:：]+?)\s*[:：]\s*(?P<val>.*?)\s*$")
_GHZ_RE = re.compile(r"([\d.]+)\s*GHz", re.IGNORECASE)
_PCT_RE = re.compile(r"(-?\d+)\s*%")
_NUM_RE = re.compile(r"(-?\d+(?:\.\d+)?)")
_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")

def _norm(key: str) -> str:
    """归一化标签：去掉所有空白、全角括号转半角、转小写。"""
    s = key.replace("\u3000", "").replace("\uff08", "(").replace("\uff09", ")")
    return re.sub(r"\s+", "", s).lower()


#: 标签（归一化后）→ 字段名（精确匹配，避免 ssid/bssid、status/state 混淆）
_KEYS: dict[str, str] = {
    k: v
    for k, v in (
        ("name", "name"),
        ("名称", "name"),
        ("description", "description"),
        ("描述", "description"),
        ("说明", "description"),
        ("state", "state"),
        ("状态", "state"),
        ("ssid", "ssid"),
        ("profile", "profile"),
        ("配置文件", "profile"),
        ("profile name", "profile"),
        ("band", "band"),
        ("频带", "band"),
        ("频段", "band"),
        ("channel", "channel"),
        ("通道", "channel"),
        ("信道", "channel"),
        ("signal", "signal"),
        ("信号", "signal"),
        ("receive rate (mbps)", "rx"),
        ("receive rate", "rx"),
        ("接收速率(mbps)", "rx"),
        ("接收速率", "rx"),
        ("transmit rate (mbps)", "tx"),
        ("transmit rate", "tx"),
        ("传输速率(mbps)", "tx"),
        ("传输速率", "tx"),
        ("radio type", "radio"),
        ("无线电类型", "radio"),
        ("interface type", "iftype"),
        ("界面类型", "iftype"),
        ("接口类型", "iftype"),
    )
}
_KEYS = {_norm(k): v for k, v in _KEYS.items()}


def _oem_encoding() -> str:
    try:
        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except Exception:  # pragma: no cover
        return "mbcs"


@dataclass
class WlanInfo:
    name: str = ""
    description: str = ""
    state: str = ""
    ssid: str = ""
    profile: str = ""
    rx_mbps: float = 0.0
    tx_mbps: float = 0.0
    signal_pct: int = -1
    band: str = ""
    channel: int = 0
    radio: str = ""

    @property
    def connected(self) -> bool:
        st = self.state.strip().lower()
        return st in ("connected", "已连接") or bool(self.ssid)

    @property
    def frequency_mhz(self) -> int:
        return frequency_mhz(self.band, self.channel)

    @property
    def dbm(self) -> int | None:
        if self.signal_pct < 0:
            return None
        return signal_to_dbm(self.signal_pct)

    @property
    def rate_mbps(self) -> float:
        return self.rx_mbps or self.tx_mbps


def signal_to_dbm(pct: int) -> int:
    """信号百分比 → dBm 近似值（92% → -54 dBm）。"""
    return int(round(pct / 2.0 - 100.0))


def frequency_mhz(band: str, channel: int) -> int:
    """(频带, 信道) → 中心频率 MHz。2.4G: 2407+5ch；5G: 5000+5ch；6G: 5950+5ch。"""
    if channel <= 0:
        return 0
    m = _GHZ_RE.search(band or "")
    ghz = float(m.group(1)) if m else 0.0
    if ghz:
        if ghz < 3.0:
            return 2407 + 5 * channel
        if ghz < 6.0:
            return 5000 + 5 * channel
        return 5950 + 5 * channel
    if channel <= 14:
        return 2407 + 5 * channel
    if channel < 181:
        return 5000 + 5 * channel
    return 5950 + 5 * channel


def _printable(text: str) -> bool:
    return bool(text) and all(ch.isprintable() for ch in text)


def decode_ssid(value: str, fallback: str = "") -> str:
    """还原 netsh 打印成十六进制的 SSID。

    802.11 的 SSID 是**裸字节数组**而非字符串：只要其中有任何非可打印 ASCII 字节，
    `netsh wlan show interfaces` 就不按文本打印，而是打印这些字节的十六进制，
    例如中文 SSID `创新实验室` 会变成 `E5889BE696B0E5AE9EE9AA8CE5AEA4`
    （即它 UTF-8 编码后的字节）。这里把这种十六进制还原回文本。

    纯 ASCII 的 SSID 永远不会被 netsh 十六进制化，所以只在「解码结果确实含有非 ASCII
    可打印字符」时才采用还原值，避免把名为 `41424344` 这类恰好是十六进制的 SSID 改错。
    """
    v = (value or "").strip()
    if len(v) < 2 or len(v) % 2 or not _HEX_RE.match(v):
        return v or fallback
    try:
        raw = bytes.fromhex(v)
    except ValueError:
        return v or fallback
    for enc in ("utf-8", _oem_encoding(), "latin-1"):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if _printable(text) and any(ord(ch) > 127 for ch in text):
            return text
    # 十六进制解不出可读文本：宁可显示 Profile 名（通常就等于 SSID），也别给用户一串编码
    return fallback or v


def _run() -> str:
    try:
        proc = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            timeout=8,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    raw = proc.stdout or b""
    # 先按 UTF-8 严格解码：netsh 跟随控制台代码页输出，控制台为 65001 时是 UTF-8；
    # GBK 文本几乎不可能是合法 UTF-8，失败后自然落到 OEM 代码页。
    for enc in ("utf-8", _oem_encoding(), "mbcs"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def query_all() -> list[WlanInfo]:
    """返回所有 WLAN 接口的信息块（未连接时 ssid 为空）。"""
    blocks: list[WlanInfo] = []
    cur: dict[str, str] | None = None
    for line in _run().splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        field = _KEYS.get(_norm(m.group("key")))
        if field is None:
            continue
        if field == "name" and cur is not None and cur:
            blocks.append(cur)  # 新接口
            cur = None
        if cur is None:
            cur = {}
        cur[field] = m.group("val")
    if cur:
        blocks.append(cur)
    return [_to_info(b) for b in blocks]


def _to_info(b: dict[str, str]) -> WlanInfo:
    raw_ssid = b.get("ssid", "").strip()
    profile = b.get("profile", "").strip()
    info = WlanInfo(
        name=b.get("name", ""),
        description=b.get("description", ""),
        state=b.get("state", ""),
        # SSID 为空说明未连接，此时不要拿 Profile 顶上
        ssid=decode_ssid(raw_ssid, profile if raw_ssid else ""),
        profile=profile,
        band=b.get("band", ""),
        radio=b.get("radio", ""),
    )
    for src, attr in (("rx", "rx_mbps"), ("tx", "tx_mbps")):
        m = _NUM_RE.search(b.get(src, ""))
        if m:
            setattr(info, attr, float(m.group(1)))
    m = _PCT_RE.search(b.get("signal", ""))
    if m:
        info.signal_pct = int(m.group(1))
    m = _NUM_RE.search(b.get("channel", ""))
    if m:
        info.channel = int(float(m.group(1)))
    return info


def query(name: str = "", description: str = "") -> WlanInfo | None:
    """按接口名或网卡描述匹配一个已连接的 WLAN 接口。"""
    items = query_all()
    if not items:
        return None
    if name:
        for it in items:
            if it.name == name:
                return it
    if description:
        for it in items:
            if it.description == description:
                return it
    for it in items:
        if it.connected:
            return it
    return items[0]


if __name__ == "__main__":  # pragma: no cover - 手工核对用
    import json

    for it in query_all():
        print(json.dumps(it.__dict__, ensure_ascii=False))
        print("  freq =", it.frequency_mhz, "dBm =", it.dbm, "rate =", it.rate_mbps)
