"""真机端到端测试：真实断开/重连 WLAN，验证「状态变化 → HUD 弹出」整条链路。

    python tools/live_test.py --profile 229028 --out-dir out/live

会在事件发生后按固定偏移自动截图（相对事件时刻 +0.2/+0.9/+1.7/+2.6/+3.5/+5.0/+6.5s），
结束后把所有帧拼成接触印样 contact_*.png 便于快速查看。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont

from net_hud import content as C
from net_hud import i18n
from net_hud import wlaninfo
from net_hud.hud import Hud
from net_hud.watcher import NetWatcher
from net_hud.win32ui_ext import set_dpi_awareness

OFFSETS = (0.2, 0.9, 1.7, 2.6, 3.5, 5.0, 6.5)


def netsh(*args: str) -> str:
    try:
        p = subprocess.run(["netsh", "wlan", *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=20)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as exc:
        return f"[netsh 失败] {exc}"


def wait_connected(profile: str, limit: float = 45.0) -> bool:
    deadline = time.monotonic() + limit
    attempt = 0
    while time.monotonic() < deadline:
        info = wlaninfo.query()
        if info is not None and info.ssid:
            print(f"  [t={time.monotonic() - T0:5.1f}] 已重连：SSID={info.ssid} "
                  f"rate={info.rate_mbps:.0f}Mbps signal={info.dbm}dBm")
            return True
        attempt += 1
        if attempt % 6 == 0:
            print(f"  [t={time.monotonic() - T0:5.1f}] 重试连接 {profile} …")
            netsh("connect", f"name={profile}", f"ssid={profile}")
        time.sleep(1.0)
    return False


def montage(paths: list[tuple[str, str]], out: str, cols: int = 3) -> str:
    imgs = [(label, Image.open(p).convert("RGB")) for label, p in paths if os.path.exists(p)]
    if not imgs:
        return ""
    w = max(i.width for _, i in imgs)
    h = max(i.height for _, i in imgs)
    rows = (len(imgs) + cols - 1) // cols
    pad, cap = 8, 22
    sheet = Image.new("RGB", (cols * (w + pad) + pad, rows * (h + cap + pad) + pad), (24, 24, 26))
    d = ImageDraw.Draw(sheet)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15)
    except Exception:
        f = ImageFont.load_default()
    for n, (label, im) in enumerate(imgs):
        cx = pad + (n % cols) * (w + pad)
        cy = pad + (n // cols) * (h + cap + pad)
        sheet.paste(im, (cx, cy))
        d.text((cx + 4, cy + im.height + 2), label, font=f, fill=(220, 220, 220))
    sheet.save(out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="229028")
    ap.add_argument("--out-dir", default="out/live")
    ap.add_argument("--dwell", type=float, default=6.0)
    ap.add_argument("--scale", type=float, default=1.0, help="缩放倍率（同 config.json）")
    ap.add_argument("--label-hold", type=float, default=3.0,
                    help="SSID / 适配器名称停留秒数，之后换成 IP")
    ap.add_argument("--ipv6", action="store_true", help="IP 优先取 IPv6")
    ap.add_argument("--no-swap", action="store_true", help="关闭「名称 → IP」切换")
    ap.add_argument("--lang", default=i18n.DEFAULT_LANG, choices=list(i18n.LANGS),
                    help="界面语言：cn / en / jp（默认 cn）")
    ap.add_argument("--grace", type=float, default=10.0)
    ap.add_argument("--down-at", type=float, default=4.0)
    ap.add_argument("--up-at", type=float, default=10.0)
    ap.add_argument("--total", type=float, default=30.0)
    ap.add_argument("--no-toggle", action="store_true", help="只跑监听，不动 WLAN")
    args = ap.parse_args(argv)

    set_dpi_awareness()
    os.makedirs(args.out_dir, exist_ok=True)
    global T0
    T0 = time.monotonic()

    hud = Hud(dwell=args.dwell, scale=args.scale, label_hold=args.label_hold,
              swap=not args.no_swap)
    print(f"HUD {hud.w}×{hud.h} @ {hud.pos} dpi={hud.dpi}")

    shots: list[tuple[float, str]] = []
    labels: dict[str, str] = {}
    events: list[tuple[float, str, str]] = []

    def on_event(ev) -> None:
        t = time.monotonic() - T0
        events.append((round(t, 2), ev.state, ev.adapter.name))
        print(f"  [t={t:5.1f}] 事件 {ev.state:<13} {ev.adapter.name} ({ev.adapter.kind})"
              + (f" ssid={ev.wlan.ssid}" if ev.wlan else ""))
        hud.play(C.build(ev.state, ev.adapter, ev.wlan, prefer_ipv6=args.ipv6,
                         lang=args.lang))
        for off in OFFSETS:
            p = os.path.join(args.out_dir, f"{ev.state}_{len(events):02d}_{off:.1f}.png")
            shots.append((t + off, p))
            labels[p] = f"#{len(events)} {ev.state} t+{off:.1f}s"

    watcher = NetWatcher(on_event, grace=args.grace, poll_interval=2.0)
    instant = watcher.start()
    print(f"即时通知={'已注册' if instant else '不可用（纯轮询）'}")

    def toggler() -> None:
        time.sleep(args.down_at)
        if args.no_toggle:
            return
        print(f"  [t={time.monotonic() - T0:5.1f}] netsh wlan disconnect")
        print("   " + netsh("disconnect").strip().replace("\n", " ")[:120])
        time.sleep(max(0.0, args.up_at - args.down_at))
        print(f"  [t={time.monotonic() - T0:5.1f}] netsh wlan connect name={args.profile}")
        print("   " + netsh("connect", f"name={args.profile}", f"ssid={args.profile}")
              .strip().replace("\n", " ")[:120])
        if not wait_connected(args.profile):
            print("  !! 重连失败，强制再试 60s")
            wait_connected(args.profile, 60.0)

    th = threading.Thread(target=toggler, daemon=True)
    th.start()

    box = (hud.pos[0] - 24, max(0, hud.pos[1] - 40), hud.pos[0] + hud.w + 24, hud.pos[1] + hud.h + 24)
    taken: set[str] = set()
    shot_ok = 0
    try:
        while time.monotonic() - T0 < args.total:
            now = time.monotonic() - T0
            hud.pump()
            watcher.poll()
            for when, path in list(shots):
                if path in taken or now < when:
                    continue
                taken.add(path)
                try:
                    from PIL import ImageGrab

                    ImageGrab.grab(bbox=box, all_screens=True).save(path)
                    shot_ok += 1
                except Exception as exc:
                    print("  截图失败：", exc)
            if not th.is_alive() and len(taken) >= len(shots):
                break
            time.sleep(0.005)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        hud.destroy()

    print(f"\n事件时间线（{len(events)} 个）：")
    for e in events:
        print("   ", e)
    print(f"截图 {shot_ok} 张 → {args.out_dir}")

    for state in C.STATES:
        group = [(labels[p], p) for _, p in shots
                 if os.path.basename(p).startswith(state + "_")]
        if group:
            out = os.path.join(args.out_dir, f"contact_{state}.png")
            montage(group, out)
            print("  ", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
