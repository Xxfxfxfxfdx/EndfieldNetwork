"""程序入口：单实例 + 托盘 + 网络监听 + HUD 主循环。

    python -m net_hud                # 后台常驻（配合 pythonw.exe 即无控制台）
    python -m net_hud --preview      # 立刻播放一次当前状态
    python -m net_hud --state dhcp_failed --kind ethernet   # 播放指定状态
    python -m net_hud --demo         # 依次播放三种状态，检查 UI
    python -m net_hud --show-config  # 打印生效的配置

尺寸与时长默认读项目根目录的 `config.json`（首次运行自动生成），
命令行参数优先级更高。
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys
import time

from . import APP_NAME, __version__
from . import anim as A
from . import config as cfgmod
from . import content as C
from . import i18n
from .hud import Hud
from .watcher import DEFAULT_IGNORE, NetWatcher

log = logging.getLogger("net_hud")

ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
QUIT_EVENT_NAME = f"Local\\{APP_NAME}_Quit"

CMD_PREVIEW = 1001
CMD_CONNECTED = 1002
CMD_DISCONNECTED = 1003
CMD_DHCP_FAILED = 1004
CMD_OPEN_LOG = 1005
CMD_QUIT = 1099

def menu_items(lang: str = i18n.DEFAULT_LANG) -> tuple:
    """托盘菜单项（`None` 表示分隔线）；文字随 `config.json` 的 `lang` 变化。"""
    item = i18n.text(lang, "menu.preview_item")
    return (
        (CMD_PREVIEW, i18n.text(lang, "menu.preview_current")),
        None,
        (CMD_CONNECTED, item.format(title=C.title(C.STATE_CONNECTED, lang))),
        (CMD_DISCONNECTED, item.format(title=C.title(C.STATE_DISCONNECTED, lang))),
        (CMD_DHCP_FAILED, item.format(title=C.title(C.STATE_DHCP_FAILED, lang))),
        None,
        (CMD_OPEN_LOG, i18n.text(lang, "menu.open_log")),
        (CMD_QUIT, i18n.text(lang, "menu.exit")),
    )


def setup_logging(level: str = "INFO") -> str:
    log_dir = os.path.join(os.environ.get("TEMP", "."), "NetworkHUD")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"log-{time.strftime('%Y%m%d')}.txt")
    handlers: list[logging.Handler] = [logging.FileHandler(path, encoding="utf-8")]
    if sys.stderr is not None:
        try:
            handlers.append(logging.StreamHandler())
        except Exception:
            pass
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )
    return path


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = ctypes.c_void_p
    k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    k.CreateEventW.restype = ctypes.c_void_p
    k.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                               ctypes.c_wchar_p]
    k.OpenEventW.restype = ctypes.c_void_p
    k.OpenEventW.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_wchar_p]
    k.SetEvent.argtypes = [ctypes.c_void_p]
    k.WaitForSingleObject.restype = ctypes.c_uint
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    return k


def acquire_single_instance() -> bool:
    k = _kernel32()
    handle = k.CreateMutexW(None, False, f"Local\\{APP_NAME}_SingleInstance")
    if not handle:
        return True
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def signal_quit() -> bool:
    """通知正在运行的实例退出（另一个进程调用）。"""
    k = _kernel32()
    handle = k.OpenEventW(EVENT_MODIFY_STATE, False, QUIT_EVENT_NAME)
    if not handle:
        return False
    try:
        return bool(k.SetEvent(handle))
    finally:
        k.CloseHandle(handle)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="net_hud", description="网络状态监测 HUD")
    ap.add_argument("--config", default=None,
                    help="配置文件路径（默认：项目根目录 config.json）")
    ap.add_argument("--scale", type=float, default=None,
                    help="缩放倍率（1.0=默认；覆盖配置文件的 scale）")
    ap.add_argument("--label-hold", type=float, default=None,
                    help="SSID/适配器名称停留秒数，之后换成 IP（默认 3）")
    ap.add_argument("--total", type=float, default=None,
                    help="整个显示窗口的总时长秒数（默认 12）")
    ap.add_argument("--duration", type=float, default=None,
                    help="入场动画基线时长（默认 6，会被限制到 3~10）")
    ap.add_argument("--grace", type=float, default=None,
                    help="DHCP 宽限秒数（默认 10）")
    ap.add_argument("--poll", type=float, default=None,
                    help="兜底轮询间隔秒数（默认 2）")
    ap.add_argument("--ignore", default=None,
                    help="额外忽略的适配器关键字，逗号分隔")
    ap.add_argument("--prefer-ipv6", dest="prefer_ipv6", action="store_true",
                    default=None, help="同时有 IPv4/IPv6 时优先显示 IPv6")
    ap.add_argument("--no-prefer-ipv6", dest="prefer_ipv6", action="store_false",
                    default=None, help="优先显示 IPv4（默认）")
    ap.add_argument("--no-swap", dest="swap_to_ip", action="store_false",
                    default=None, help="关闭「名称 → IP」自动切换")
    ap.add_argument("--lang", default=None,
                    choices=list(i18n.LANGS),
                    help="界面语言：cn=简体中文 / en=English / jp=日本語（默认 cn）")
    ap.add_argument("--show-config", action="store_true", help="打印生效的配置后退出")
    ap.add_argument("--preview", action="store_true", help="启动时先播放一次")
    ap.add_argument("--state", choices=list(C.STATES), default="",
                    help="直接播放指定状态（不进入监听循环）")
    ap.add_argument("--kind", default="wifi",
                    choices=["wifi", "ethernet", "btpan", "usb_rndis"],
                    help="配合 --state 使用，选择示例适配器类型")
    ap.add_argument("--demo", action="store_true", help="依次播放三种状态后退出")
    ap.add_argument("--no-tray", action="store_true", help="不创建托盘图标")
    ap.add_argument("--quit", action="store_true", help="让正在运行的实例退出")
    ap.add_argument("--restart", action="store_true", help="先退出旧实例再启动")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    ap.add_argument("--log-level", default="INFO")
    return ap


def merge_args(cfg: cfgmod.Config, args) -> cfgmod.Config:
    """把命令行里显式给出的项覆盖到配置上。"""
    pairs = (
        ("scale", args.scale),
        ("label_hold", args.label_hold),
        ("total", args.total),
        ("duration", args.duration),
        ("grace", args.grace),
        ("poll", args.poll),
        ("prefer_ipv6", args.prefer_ipv6),
        ("swap_to_ip", args.swap_to_ip),
        ("lang", args.lang),
    )
    for key, value in pairs:
        if value is not None:
            setattr(cfg, key, value)
    if args.ignore:
        extra = [x.strip().lower() for x in args.ignore.split(",") if x.strip()]
        cfg.ignore = list(cfg.ignore) + extra
    return cfg.normalize()


def _mtime(path: str) -> float | None:
    """配置文件最后修改时间；取不到返回 None（此时每次都重读）。"""
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log_path = setup_logging(args.log_level)
    log.info("=" * 60)
    log.info("%s %s 启动（日志 %s）", APP_NAME, __version__, log_path)

    cfg, cfg_path = cfgmod.load(args.config)
    merge_args(cfg, args)
    log.info("配置：%s", cfgmod.describe(cfg))
    log.info("配置文件：%s", cfg_path)
    for note in cfg.notes():
        log.warning("%s", note)

    if args.show_config:
        print(f"配置文件：{cfg_path}")
        print(cfgmod.describe(cfg))
        return 0

    if args.quit:
        ok = signal_quit()
        log.info("已发送退出信号" if ok else "没有正在运行的实例")
        return 0 if ok else 1
    if args.restart and signal_quit():
        log.info("已通知旧实例退出，等待其释放单实例锁")
        time.sleep(1.5)

    ignore = tuple(cfg.ignore)

    if args.state or args.demo:
        return _run_oneshot(args, cfg)

    if not acquire_single_instance():
        log.warning("已有实例在运行，退出")
        return 0

    hud = Hud(
        duration=cfg.duration_clamped,
        dwell=cfg.dwell_seconds,
        scale=cfg.scale,
        label_hold=cfg.label_hold,
        swap=cfg.swap_to_ip,
    )
    log.info("HUD 窗口 %d×%d @ (%d, %d) dpi=%d scale=%g",
             hud.w, hud.h, hud.pos[0], hud.pos[1], hud.dpi, hud.scale)

    live = {"cfg": cfg, "mtime": _mtime(cfg_path)}

    def refresh_cfg() -> cfgmod.Config:
        """触发前重读配置文件 —— 改完 `config.json` 不必重启，缩放立刻生效。"""
        mt = _mtime(cfg_path)
        if mt is None or mt == live["mtime"]:
            return live["cfg"]
        live["mtime"] = mt
        fresh, _ = cfgmod.load(cfg_path, create=False)
        merge_args(fresh, args)
        old = live["cfg"]
        live["cfg"] = fresh
        for note in fresh.notes():
            log.warning("%s", note)
        for key in ("grace", "poll"):
            if abs(float(getattr(fresh, key)) - float(getattr(old, key))) > 1e-9:
                log.info("配置里的 %s 变为 %g，重启后生效", key, getattr(fresh, key))
        if list(fresh.ignore) != list(old.ignore):
            log.info("配置里的 ignore 已改变，重启后生效")
        if fresh.lang != old.lang:
            log.info("配置里的 lang 变为 %s（%s），界面文字已切换",
                     fresh.lang, i18n.LANG_NAMES.get(fresh.lang, fresh.lang))
            if tray is not None:
                tray.items = menu_items(fresh.lang)
                tray.set_tooltip(f"{i18n.app_title(fresh.lang)} — "
                                 f"{i18n.listening(fresh.lang)}")
        if hud.apply_options(
            duration=fresh.duration_clamped,
            dwell=fresh.dwell_seconds,
            label_hold=fresh.label_hold,
            swap=fresh.swap_to_ip,
            scale=fresh.scale,
        ):
            log.info("按新配置调整窗口 → %d×%d @ (%d, %d) scale=%g",
                     hud.w, hud.h, hud.pos[0], hud.pos[1], hud.scale)
        else:
            log.info("已重新载入配置（无需重启）")
        return fresh

    def on_event(event) -> None:
        c = refresh_cfg()
        content = C.build(event.state, event.adapter, event.wlan,
                          prefer_ipv6=c.prefer_ipv6, lang=c.lang)
        log.info("显示 %s：%s（%s）", content.state, content.line1, content.adapter_name)
        hud.play(content)
        if tray is not None:
            tray.set_tooltip(f"{i18n.app_title(c.lang)} — {content.title}")

    watcher = NetWatcher(
        on_event,
        grace=cfg.grace,
        poll_interval=cfg.poll,
        ignore=DEFAULT_IGNORE + ignore,
    )

    state = {"quit": False}

    def preview(state_name: str | None = None, adapter=None, kind: str | None = None):
        ad = adapter or watcher.interesting()
        st = state_name
        if ad is None:
            from tools.preview import demo_adapter  # type: ignore

            ad = demo_adapter(st or C.STATE_CONNECTED, kind or args.kind)
            st = st or C.STATE_CONNECTED
        if st is None:
            st = C.STATE_CONNECTED if ad.up else C.STATE_DISCONNECTED
        wlan = None
        if st == C.STATE_CONNECTED and ad.kind == "wifi":
            try:
                from . import wlaninfo

                wlan = wlaninfo.query(name=ad.name, description=ad.desc)
            except Exception:
                wlan = None
        c = refresh_cfg()
        hud.play(C.build(st, ad, wlan, prefer_ipv6=c.prefer_ipv6, lang=c.lang))

    tray = None
    if not args.no_tray:
        try:
            from .tray import TrayIcon

            tray = TrayIcon(
                tooltip=f"{i18n.app_title(cfg.lang)} — {i18n.listening(cfg.lang)}",
                items=menu_items(cfg.lang),
                handlers={
                    CMD_PREVIEW: lambda: preview(),
                    CMD_CONNECTED: lambda: preview(C.STATE_CONNECTED, kind="wifi"),
                    CMD_DISCONNECTED: lambda: preview(C.STATE_DISCONNECTED, kind="ethernet"),
                    CMD_DHCP_FAILED: lambda: preview(C.STATE_DHCP_FAILED, kind="wifi"),
                    CMD_OPEN_LOG: lambda: _open_log_dir(log_path),
                    CMD_QUIT: lambda: state.__setitem__("quit", True),
                },
                on_activate=lambda: preview(),
            )
            if tray.add():
                log.info("托盘图标已创建")
            else:
                log.warning("托盘图标创建失败（程序继续运行）")
        except Exception as exc:
            log.warning("托盘初始化失败：%s", exc)
            tray = None

    instant = watcher.start()
    log.info("开始监听网络状态（即时通知=%s，轮询 %.1fs，DHCP 宽限 %.0fs）",
             instant, cfg.poll, cfg.grace)
    if args.preview:
        preview()

    k32 = _kernel32()
    quit_event = k32.CreateEventW(None, True, False, QUIT_EVENT_NAME)
    try:
        while not state["quit"]:
            if not hud.pump():
                break
            if quit_event and k32.WaitForSingleObject(quit_event, 0) == WAIT_OBJECT_0:
                log.info("收到退出信号（--quit）")
                break
            watcher.poll()
            time.sleep(0.004)
    except KeyboardInterrupt:
        log.info("收到 Ctrl+C，退出")
    finally:
        watcher.stop()
        if quit_event:
            k32.CloseHandle(quit_event)
        if tray is not None:
            tray.destroy()
        hud.destroy()
        log.info("已退出")
    return 0


def _run_oneshot(args, cfg) -> int:
    """`--state` / `--demo`：不进入监听循环，播完即退。"""
    from tools.preview import demo_adapter

    def make(st: str):
        return C.build(st, demo_adapter(st, args.kind), None,
                       prefer_ipv6=cfg.prefer_ipv6, lang=cfg.lang)

    hud = Hud(
        duration=cfg.duration_clamped,
        dwell=cfg.dwell_seconds,
        scale=cfg.scale,
        label_hold=cfg.label_hold,
        swap=cfg.swap_to_ip,
    )
    if args.demo:
        for st in C.STATES:
            hud.play(C.build(st, demo_adapter(st, "wifi"), None,
                             prefer_ipv6=cfg.prefer_ipv6, lang=cfg.lang))
            while hud.busy:
                if not hud.pump():
                    hud.destroy()
                    return 0
                time.sleep(0.002)
        hud.destroy()
        return 0

    state_name = args.state or C.STATE_CONNECTED
    hud.play(make(state_name))
    while hud.busy:
        if not hud.pump():
            break
        time.sleep(0.002)
    hud.destroy()
    return 0


def _open_log_dir(log_path: str) -> None:
    try:
        os.startfile(os.path.dirname(log_path))  # noqa: S606
    except Exception as exc:
        log.warning("打开日志目录失败：%s", exc)


if __name__ == "__main__":
    raise SystemExit(main())
