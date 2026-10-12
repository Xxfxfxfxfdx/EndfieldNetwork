"""真机冒烟测试：把 HUD 真的显示在屏幕上，并在若干时刻截屏保存。

截屏包含桌面背景，因此可以同时验证：
* 分层窗口的逐像素透明是否正确（胶囊圆角外应能看到桌面）；
* 动画各阶段的真实像素效果与位置（是否贴在工作区顶部居中）。

用法（项目根目录）：
    python tools/smoke.py --state connected --kind wifi
    python tools/smoke.py --state disconnected --kind ethernet --dwell 3
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import ImageGrab  # noqa: E402

from net_hud import anim as A  # noqa: E402
from net_hud import content as C  # noqa: E402
from net_hud import i18n  # noqa: E402
from tools.preview import build_content  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Network HUD 真机冒烟测试")
    ap.add_argument("--state", default=C.STATE_CONNECTED,
                    choices=[C.STATE_CONNECTED, C.STATE_DISCONNECTED, C.STATE_DHCP_FAILED])
    ap.add_argument("--kind", default="wifi",
                    choices=["wifi", "ethernet", "btpan", "usb_rndis"])
    ap.add_argument("--cues", default="0.10,0.20,0.30,0.42")
    ap.add_argument("--duration", type=float, default=A.BASELINE_SECONDS)
    ap.add_argument("--dwell", type=float, default=3.0)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--long", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="缩放倍率，含义与 config.json 的 scale 相同")
    ap.add_argument("--label-hold", type=float, default=3.0,
                    help="SSID / 适配器名称停留秒数，之后换成 IP")
    ap.add_argument("--lang", default=i18n.DEFAULT_LANG, choices=list(i18n.LANGS),
                    help="界面语言：cn / en / jp（默认 cn）")
    ap.add_argument("--ipv6", action="store_true", help="示例数据使用 IPv6 长地址")
    ap.add_argument("--out-dir", default="out/smoke")
    args = ap.parse_args(argv)

    from net_hud.hud import Hud

    content, adapter = build_content(args)
    hud = Hud(duration=args.duration, dwell=args.dwell, scale=args.scale,
              label_hold=args.label_hold)

    print(f"[smoke] state={content.state} logo={content.logo} "
          f"{hud.w}×{hud.h} @ ({hud.pos[0]}, {hud.pos[1]}) dpi={hud.dpi}")
    print(f"[smoke] line1={content.line1!r} value={content.value!r}{content.unit}")

    os.makedirs(args.out_dir, exist_ok=True)
    hud.play(content)
    anim = hud._anim
    assert anim is not None

    grabs = [
        (f"cue{c:0.2f}", A._map_cue(args.duration, c) * args.duration)
        for c in (float(x) for x in args.cues.split(",") if x.strip())
    ]
    grabs.append(("dwell", anim.dwell_start + min(1.0, args.dwell * 0.5)))
    grabs.sort(key=lambda kv: kv[1])

    pad = 24
    bbox = (
        max(0, hud.pos[0] - pad), max(0, hud.pos[1] - pad),
        min(hud.pos[0] + hud.w + pad, hud.area[2]),
        min(hud.pos[1] + hud.h + pad, hud.area[3]),
    )

    shots = 0
    t0 = hud._t0
    deadline = time.perf_counter() + args.duration + args.dwell + 3.0
    while grab := (grabs[0] if grabs else None):
        if not hud.pump():
            break
        if hud.phase == "idle" and not grabs:
            break
        now = time.perf_counter()
        if now - t0 >= grab[1]:
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
            path = os.path.join(args.out_dir, f"{grab[0]}.png")
            img.save(path)
            print(f"[smoke] {grab[0]} @ {now - t0:.3f}s → {path} {img.size}")
            grabs.pop(0)
            shots += 1
        if now > deadline:
            print("[smoke] 超时")
            break
        time.sleep(0.002)

    while hud.busy:
        hud.pump()
        time.sleep(0.002)
    hud.destroy()
    print(f"[smoke] 完成，共 {shots} 张截屏 → {args.out_dir}")
    return 0 if shots else 1


if __name__ == "__main__":
    raise SystemExit(main())
