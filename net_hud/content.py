"""HUD 内容模型 —— 三种状态与两页文案。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from . import i18n
from . import theme as T

__all__ = [
    "STATE_CONNECTED",
    "STATE_DISCONNECTED",
    "STATE_DHCP_FAILED",
    "STATES",
    "TITLES",
    "TAGLINES",
    "title",
    "HudContent",
]

STATE_CONNECTED = "connected"
STATE_DISCONNECTED = "disconnected"
STATE_DHCP_FAILED = "dhcp_failed"

STATES = (STATE_CONNECTED, STATE_DISCONNECTED, STATE_DHCP_FAILED)


def title(state: str, lang: str = i18n.DEFAULT_LANG) -> str:
    """第一页主标题（替换原项目的「超充模式」），按语言取自 `i18n`。"""
    return i18n.title(state, lang)


#: 第一页主标题的**简体中文**表（保留给老代码与测试用；带语言请用 `title()`）
TITLES = {state: i18n.title(state, "cn") for state in STATES}

#: 第一页副标题（替换原项目的 `/// SUPER CHARGE MODE`）
TAGLINES = {
    STATE_CONNECTED: "/// NETWORK ONLINE",
    STATE_DISCONNECTED: "/// LINK DOWN",
    STATE_DHCP_FAILED: "/// DHCP FAILED",
}

#: 副标题颜色：连接成功用主题唯一彩色，异常用警报红
TAG_COLORS = {
    STATE_CONNECTED: T.ACCENT,
    STATE_DISCONNECTED: T.DANGER,
    STATE_DHCP_FAILED: T.DANGER,
}

#: 波纹方向：连接=由内向外扩散；断开/DHCP 异常=由外向内收拢（对应原项目"拔电"）
OUTWARD = {
    STATE_CONNECTED: True,
    STATE_DISCONNECTED: False,
    STATE_DHCP_FAILED: False,
}


@dataclass
class HudContent:
    """一次播放要显示的全部文案与图标。"""

    state: str = STATE_CONNECTED
    logo: str = "nointernet"

    title: str = ""
    tagline: str = ""
    tag_color: tuple[int, int, int] = T.ACCENT

    # 第二页（信息页）
    line1: str = ""                      # WiFi: SSID；其它: 适配器名称
    line2: str | None = None             # WiFi 才有：网卡名称 · 频率
    value: str = ""                      # 链接速率数字
    unit: str = "Mbps"                   # 速率单位
    sub: str | None = None               # WiFi 才有：信号强度 dBm

    #: 名称停留结束后替换 `line1` 的文本（适配器 IP；None 表示不切换）
    swap_text: str | None = None
    #: `line1` 当前是否是 IP 文本（渲染时自动缩字号以便放下长 IPv6）
    line1_is_ip: bool = False

    adapter_name: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def outward(self) -> bool:
        return OUTWARD.get(self.state, True)

    def swapped(self) -> "HudContent":
        """把 `line1` 换成 IP 的副本（`swap_text` 为空时返回自身）。"""
        if not self.swap_text or self.swap_text == self.line1:
            return self
        clone = replace(self, line1=self.swap_text, line1_is_ip=True)
        return clone

    @classmethod
    def for_state(cls, state: str, logo: str, lang: str = i18n.DEFAULT_LANG,
                  **kw) -> "HudContent":
        return cls(
            state=state,
            logo=logo,
            title=title(state, lang),
            tagline=TAGLINES.get(state, ""),
            tag_color=TAG_COLORS.get(state, T.ACCENT),
            **kw,
        )


def build(
    state: str,
    adapter,
    wlan=None,
    *,
    prefer_ipv6: bool = False,
    lang: str = i18n.DEFAULT_LANG,
) -> HudContent:
    """由适配器状态 + WLAN 详情构造 HUD 内容。

    - `connected` 且为 WLAN 且有详情：左侧 SSID / 网卡名·频率，右侧速率 + dBm；
    - `connected` 其它：左侧适配器名称，右侧链接速率；
    - `disconnected` / `dhcp_failed`：`nointernet` logo，左侧适配器名称。

    `connected` 时额外写入 `swap_text`（适配器 IP），由 `Hud` 在名称停留
    `label_hold` 秒后替换 `line1`。IP 文本不带 "IP" 前缀。
    """
    from .netinfo import KIND_LOGO, format_speed

    kind = getattr(adapter, "kind", "other")
    desc = getattr(adapter, "desc", "") or getattr(adapter, "name", "")
    speed_txt, speed_unit = format_speed(getattr(adapter, "receive_bps", 0) or 0)
    ip_text = ""
    if hasattr(adapter, "display_ip"):
        try:
            ip_text = adapter.display_ip(prefer_ipv6) or ""
        except Exception:
            ip_text = ""

    if state == STATE_CONNECTED:
        logo = KIND_LOGO.get(kind, "nointernet")
        swap = ip_text or None
        if kind == "wifi" and wlan is not None:
            ssid = (getattr(wlan, "ssid", "") or "").strip() or desc
            nic = (getattr(wlan, "description", "") or "").strip() or desc
            freq = getattr(wlan, "frequency_mhz", 0) or 0
            line2 = f"{nic} · {freq}MHz" if freq else nic
            rate = getattr(wlan, "rate_mbps", 0.0) or 0.0
            dbm = getattr(wlan, "dbm", None)
            return HudContent.for_state(
                state, logo, lang=lang,
                line1=ssid,
                line2=line2,
                value=f"{rate:.0f}" if rate else speed_txt,
                unit="Mbps" if rate else speed_unit,
                sub=f"{dbm} dBm" if dbm is not None else None,
                swap_text=swap,
                adapter_name=desc,
            )
        return HudContent.for_state(
            state, logo, lang=lang,
            line1=desc, line2=None,
            value=speed_txt, unit=speed_unit, sub=None,
            swap_text=swap,
            adapter_name=desc,
        )

    # 断开连接 / DHCP 异常 —— 一律用 nointernet logo
    # DHCP 异常时左下行直接给出地址（不加 "IP" 前缀）
    extra = ip_text if state == STATE_DHCP_FAILED and ip_text else None
    no_link = speed_txt == "-"
    return HudContent.for_state(
        state, "nointernet", lang=lang,
        line1=desc, line2=extra,
        value="—" if no_link else speed_txt,
        unit="" if no_link else speed_unit,
        sub=None,
        adapter_name=desc,
    )
