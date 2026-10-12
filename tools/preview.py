"""静态预览工具：把 HUD 动画的若干时刻渲染成一张拼图，用于肉眼核对 UI。

用法（在项目根目录）：
    python tools/preview.py                       # 连接成功 + WLAN，全部关键帧
    python tools/preview.py --state disconnected
    python tools/preview.py --state dhcp_failed --zoom 2
    python tools/preview.py --live                # 用本机真实适配器信息
    python tools/preview.py --long                # 超长 SSID，检查省略号裁切
    python tools/preview.py --out-dir out         # 同时导出每一帧
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

from net_hud import anim  # noqa: E402
from net_hud import content as C  # noqa: E402
from net_hud import i18n  # noqa: E402
from net_hud import netinfo, theme as T, wlaninfo  # noqa: E402
from net_hud.renderer import Renderer  # noqa: E402

#: 默认采样时刻（归一化 cue，即原项目时间常量所在的坐标系）
DEFAULT_CUES = (
    0.00, 0.04, 0.05, 0.07, 0.09, 0.10, 0.12, 0.14,
    0.17, 0.20, 0.25, 0.30, 0.33, 0.36, 0.38, 0.42,
    0.50, 0.65, 0.86, 0.89, 0.92, 0.96,
)

CHECKER = 12


@dataclass
class FakeAdapter:
    name: str = "以太网"
    desc: str = "Realtek PCIe GbE Family Controller"
    kind: str = "ethernet"
    receive_bps: int = 0
    transmit_bps: int = 0
    ipv4: tuple = ()
    ipv6: tuple = ()
    if_type: int = 6
    oper_status: int = 0
    if_index: int = 0
    mac: str = ""

    @property
    def up(self) -> bool:
        return self.oper_status == netinfo.IF_OPER_STATUS_UP

    @property
    def primary_ipv4(self) -> str:
        return self.ipv4[0] if self.ipv4 else ""

    @property
    def apipa(self) -> bool:
        return bool(self.ipv4) and all(
            ip.startswith(netinfo.APIPA_PREFIX) for ip in self.ipv4
        )

    def display_ip(self, prefer_ipv6: bool = False) -> str:
        real4 = [ip for ip in self.ipv4 if not ip.startswith(netinfo.APIPA_PREFIX)]
        v6 = self.ipv6[0] if self.ipv6 else ""
        v4 = real4[0] if real4 else ""
        if prefer_ipv6:
            return v6 or v4 or (self.ipv4[0] if self.ipv4 else "")
        return v4 or v6 or (self.ipv4[0] if self.ipv4 else "")


@dataclass
class FakeWlan:
    ssid: str = "229028"
    description: str = "Intel(R) Wi-Fi 6 AX201 160MHz"
    rx_mbps: float = 1081.0
    tx_mbps: float = 1201.0
    signal_pct: int = 92
    band: str = "5 GHz"
    channel: int = 157

    @property
    def frequency_mhz(self) -> int:
        return wlaninfo.frequency_mhz(self.band, self.channel)

    @property
    def dbm(self):
        return wlaninfo.signal_to_dbm(self.signal_pct)

    @property
    def rate_mbps(self) -> float:
        return self.rx_mbps


def demo_adapter(state: str, kind: str, ipv6: bool = False) -> FakeAdapter:
    if kind == "wifi":
        a = FakeAdapter(
            name="WLAN", desc="Intel(R) Wi-Fi 6 AX201 160MHz", kind="wifi",
            if_type=netinfo.IF_TYPE_IEEE80211, receive_bps=1_201_000_000,
        )
    elif kind == "btpan":
        a = FakeAdapter(
            name="蓝牙网络连接", desc="Bluetooth Device (Personal Area Network)",
            kind="btpan", receive_bps=3_000_000,
        )
    elif kind == "usb_rndis":
        a = FakeAdapter(
            name="以太网 2", desc="Remote NDIS based Internet Sharing Device",
            kind="usb_rndis", receive_bps=425_000_000,
        )
    else:
        a = FakeAdapter(
            name="以太网", desc="Realtek PCIe GbE Family Controller",
            kind="ethernet", receive_bps=1_000_000_000,
        )
    if state == C.STATE_CONNECTED:
        a.oper_status = netinfo.IF_OPER_STATUS_UP
        a.ipv4 = ("192.168.3.51",)
    elif state == C.STATE_DHCP_FAILED:
        a.oper_status = netinfo.IF_OPER_STATUS_UP
        a.ipv4 = ("169.254.38.21",)
        a.receive_bps = 0
    else:
        a.oper_status = 0
        a.ipv4 = ("169.254.158.20",)
        a.receive_bps = 0
    if ipv6:
        a.ipv6 = ("2408:8214:5b3a:1f00:1a2b:3c4d:5e6f:7a8b",)
    return a


def live_adapter(kind: str):
    try:
        snap = netinfo.snapshot()
    except Exception as exc:  # pragma: no cover
        print(f"[preview] 读取本机适配器失败：{exc}", file=sys.stderr)
        return None
    items = [a for a in snap.values() if a.kind == kind]
    for a in items:
        if a.up:
            return a
    return items[0] if items else None


def build_content(args) -> tuple[C.HudContent, object]:
    state = args.state
    if args.live:
        adapter = live_adapter(args.kind)
        if adapter is None:
            print(f"[preview] 本机没有 {args.kind} 适配器，退回示例数据", file=sys.stderr)
            adapter = demo_adapter(state, args.kind, args.ipv6)
    else:
        adapter = demo_adapter(state, args.kind, args.ipv6)

    wlan = None
    if args.long:
        wlan = FakeWlan(
            ssid="ChinaNet-VeryLongSSIDName-5G-Extended-229028",
            description="Intel(R) Wi-Fi 6 AX201 160MHz",
        )
    elif args.kind == "wifi" and state == C.STATE_CONNECTED:
        wlan = FakeWlan() if not args.live else wlaninfo.query(
            name=getattr(adapter, "name", ""), description=getattr(adapter, "desc", "")
        )
        if wlan is None:
            wlan = FakeWlan()
    return C.build(state, adapter, wlan, prefer_ipv6=args.ipv6,
                   lang=getattr(args, "lang", i18n.DEFAULT_LANG)), adapter


def checkerboard(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), (150, 150, 150))
    d = ImageDraw.Draw(img)
    for y in range(0, h, CHECKER):
        for x in range(0, w, CHECKER):
            if ((x // CHECKER) + (y // CHECKER)) % 2:
                d.rectangle([x, y, x + CHECKER - 1, y + CHECKER - 1], fill=(178, 178, 178))
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Network HUD 静态预览")
    ap.add_argument("--state", default=C.STATE_CONNECTED,
                    choices=[C.STATE_CONNECTED, C.STATE_DISCONNECTED, C.STATE_DHCP_FAILED])
    ap.add_argument("--kind", default="wifi",
                    choices=["wifi", "ethernet", "btpan", "usb_rndis"])
    ap.add_argument("--cues", default="", help="逗号分隔的归一化 cue 列表")
    ap.add_argument("--duration", type=float, default=anim.BASELINE_SECONDS)
    ap.add_argument("--zoom", type=float, default=2.0, help="在 0.8 基础上再放大")
    ap.add_argument("--scale", type=float, default=1.0, help="配置里的缩放倍率")
    ap.add_argument("--label-hold", type=float, default=3.0,
                    help="SSID/适配器名称停留秒数，之后换成 IP")
    ap.add_argument("--ipv6", action="store_true", help="示例数据用 IPv6 长地址")
    ap.add_argument("--lang", default=i18n.DEFAULT_LANG, choices=list(i18n.LANGS),
                    help="界面语言：cn / en / jp（默认 cn）")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--live", action="store_true", help="使用本机真实适配器信息")
    ap.add_argument("--long", action="store_true", help="使用超长 SSID 检查省略号")
    ap.add_argument("--out", default="", help="拼图输出路径")
    ap.add_argument("--out-dir", default="", help="逐帧导出目录")
    args = ap.parse_args(argv)

    cues = (
        tuple(float(x) for x in args.cues.split(",") if x.strip())
        if args.cues else DEFAULT_CUES
    )
    hud_content, adapter = build_content(args)
    base_scale = T.GLOBAL_SCALE * args.zoom * args.scale
    rd = Renderer(hud_content, base_scale)
    a = anim.HudAnimation(args.duration, outward=hud_content.outward)

    # 名称 → IP 的切换时刻（与实际 Hud 一致：从信息页出现开始计时）
    alt = hud_content.swapped()
    swap_at = None
    if alt is not hud_content and args.label_hold > 0:
        swap_at = (
            anim.cue_seconds(args.duration, anim.T_NUM_READY) + args.label_hold
        )

    print(f"[preview] state={hud_content.state} logo={hud_content.logo} "
          f"outward={hud_content.outward}")
    print(f"[preview] line1={hud_content.line1!r} line2={hud_content.line2!r} "
          f"value={hud_content.value!r}{hud_content.unit} sub={hud_content.sub!r}")
    print(f"[preview] adapter={getattr(adapter, 'name', '')} / "
          f"{getattr(adapter, 'desc', '')} kind={getattr(adapter, 'kind', '')}")
    if swap_at is None:
        print("[preview] 无 IP 切换")
    else:
        print(f"[preview] {swap_at:.2f}s 后 line1 → {alt.line1!r}")
    print(f"[preview] 帧尺寸 {rd.w}×{rd.h} (base_scale={base_scale})")

    frames = []
    for cue in cues:
        secs = anim.cue_seconds(args.duration, cue)
        st = a.state_at(secs)
        c = alt if (swap_at is not None and secs >= swap_at) else hud_content
        img = rd.render(st, c)
        frames.append((cue, secs, img))

    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)
        for cue, secs, img in frames:
            img.save(os.path.join(args.out_dir, f"cue{cue:0.2f}.png"))
        print(f"[preview] 已导出 {len(frames)} 帧 → {args.out_dir}")

    w, h = rd.w, rd.h
    pad, cap = 10, 22
    cols = max(1, args.cols)
    rows = (len(frames) + cols - 1) // cols
    cw, ch = w + pad * 2, h + cap + pad * 2
    sheet = Image.new("RGB", (cw * cols, ch * rows), (46, 46, 48))
    sd = ImageDraw.Draw(sheet)
    cap_font = T.font("num", 15)

    for i, (cue, secs, img) in enumerate(frames):
        cx, cy = (i % cols) * cw, (i // cols) * ch
        sd.text((cx + pad, cy + 4), f"cue {cue:.2f}  ({secs:.3f}s)",
                fill=(200, 200, 200), font=cap_font)
        bg = checkerboard(w, h)
        bg.paste(img, (0, 0), img)
        sheet.paste(bg, (cx + pad, cy + cap))

    out = args.out or os.path.join(
        "out", f"preview_{hud_content.state}_{args.kind}.png"
    )
    d = os.path.dirname(out)
    if d:
        os.makedirs(d, exist_ok=True)
    sheet.save(out)
    print(f"[preview] 拼图 {sheet.width}×{sheet.height} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
