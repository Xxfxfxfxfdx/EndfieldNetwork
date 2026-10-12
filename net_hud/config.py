"""配置文件 —— 缩放倍率、名称停留时长、窗口总时长等。

配置文件默认放在项目根目录的 `config.json`（与 `net_hud/` 同级），
首次运行时自动生成一份带中文注释的默认配置。
整个文件中以 `//` 或 `#` **开头的整行**会被当作注释忽略，因此可以直接
在生成的文件里写注释；解析失败时只记一条警告并退回默认值，不会让程序崩溃。

命令行参数优先级高于配置文件。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field

from . import anim as A
from . import i18n

log = logging.getLogger("net_hud.config")

__all__ = ["Config", "default_path", "load", "describe"]

CONFIG_NAME = "config.json"

#: 项目根目录（`net_hud/` 的上一层）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 缩放倍率的合法区间
SCALE_MIN, SCALE_MAX = 0.35, 4.0


def default_path() -> str:
    return os.path.join(_ROOT, CONFIG_NAME)


@dataclass
class Config:
    """全部可配置项（单位：秒，除 `scale` 外）。"""

    #: 缩放倍率：1.0 = 原项目默认大小；窗口始终在屏幕顶部水平居中
    scale: float = 1.0
    #: SSID / 适配器名称显示多久，之后换成适配器 IP
    label_hold: float = 3.0
    #: 整个显示窗口的总时长（入场动画 + 停留 + 收尾）
    total: float = 12.0
    #: 入场动画基线时长（3~10），越小动画越快
    duration: float = A.BASELINE_SECONDS
    #: 断开→连接后 IP 仍是 169.254 时最多等待多少秒
    grace: float = 10.0
    #: 兜底轮询间隔
    poll: float = 2.0
    #: 忽略的适配器关键字（子串匹配，不区分大小写）
    ignore: list[str] = field(default_factory=list)
    #: 同时有 IPv4/IPv6 时是否优先显示 IPv6
    prefer_ipv6: bool = False
    #: 是否启用「名称 → IP」自动切换
    swap_to_ip: bool = True
    #: 界面语言："cn"（简体中文）/"en"（English）/"jp"（日本語）
    lang: str = i18n.DEFAULT_LANG

    # ---------------------------------------------------------------- 推导

    @property
    def duration_clamped(self) -> float:
        return A.clamp_duration(self.duration)

    @property
    def intro_seconds(self) -> float:
        """入场动画时长（= 信息页出现的时刻）。"""
        return A.cue_seconds(self.duration_clamped, A.T_HOLD_C)

    @property
    def close_seconds(self) -> float:
        d = self.duration_clamped
        return d * (A.T_CLOSE - A.T_HOLD_C)

    @property
    def dwell_seconds(self) -> float:
        """信息页续住停留的秒数（由 `total` 反推）。"""
        return max(0.2, float(self.total) - self.intro_seconds - self.close_seconds)

    @property
    def effective_total(self) -> float:
        return self.intro_seconds + self.dwell_seconds + self.close_seconds

    @property
    def swap_seconds(self) -> float:
        """信息页出现后多久把名称换成 IP（绝对秒数）。"""
        return (
            A.cue_seconds(self.duration_clamped, A.T_NUM_READY)
            + max(0.0, float(self.label_hold))
        )

    # ---------------------------------------------------------------- 校验

    def normalize(self) -> "Config":
        def num(value, low, high, fallback):
            try:
                v = float(value)
            except (TypeError, ValueError):
                return fallback
            if v != v:  # NaN
                return fallback
            return min(high, max(low, v))

        self.scale = num(self.scale, SCALE_MIN, SCALE_MAX, 1.0)
        self.label_hold = num(self.label_hold, 0.0, 600.0, 3.0)
        self.total = num(self.total, 1.0, 600.0, 12.0)
        self.duration = A.clamp_duration(num(self.duration, 3.0, 10.0, 6.0))
        self.grace = num(self.grace, 0.0, 300.0, 10.0)
        self.poll = num(self.poll, 0.3, 60.0, 2.0)
        self.ignore = [str(x).strip().lower() for x in (self.ignore or []) if str(x).strip()]
        self.prefer_ipv6 = bool(self.prefer_ipv6)
        self.swap_to_ip = bool(self.swap_to_ip)

        raw_lang = str(self.lang or "").strip()
        self.lang = i18n.normalize(raw_lang)
        if self.lang != raw_lang.lower():
            log.warning(
                "配置文件里的 lang=%r 无法识别，已改用默认的 %s（可选：%s）",
                raw_lang, self.lang, " / ".join(i18n.LANGS),
            )
        return self

    def notes(self) -> list[str]:
        """不合常理但能运行的组合，返回提示语。"""
        out: list[str] = []
        floor = self.intro_seconds + self.close_seconds + 0.2
        if float(self.total) < floor:
            out.append(
                f"total={self.total:g}s 小于入场+收尾所需的 {floor:.2f}s，"
                f"已按下限 {self.effective_total:.2f}s 播放"
            )
        if self.swap_to_ip and self.swap_seconds > self.effective_total - 0.05:
            out.append(
                f"label_hold={self.label_hold:g}s 使换 IP 的时刻（{self.swap_seconds:.2f}s）"
                f"晚于窗口结束（{self.effective_total:.2f}s），本次不会显示 IP；"
                f"想让 IP 至少露 1 秒，可把 total 调大或把 label_hold 调小"
            )
        return out


# -------------------------------------------------------------------- 注释

_HEADER = """\
// Network HUD 配置文件（UTF-8）
// 以 // 或 # 开头的整行是注释，可随意增删；改完保存即可，下次触发时生效。
// 命令行参数（如 --scale）优先级高于本文件。
"""


def _template(cfg: Config) -> str:
    def b(v: bool) -> str:
        return "true" if v else "false"

    return _HEADER + """\
{
  // ---------------- 显示尺寸 ----------------
  // 缩放倍率：1.0 = 默认大小，0.5 = 一半，2.0 = 两倍（允许 0.35 ~ 4.0）。
  // 无论多大，窗口始终贴在屏幕工作区顶部并水平居中。
  "scale": %(scale)g,

  // ---------------- 时间（秒） ----------------
  // SSID / 适配器名称 显示多久；之后该区域换成适配器 IP，直到窗口关闭。
  // 计时从「信息页出现」开始算，包含入场动画的剩余部分。
  "label_hold": %(label_hold)g,

  // 整个显示窗口的总时长：从胶囊出现到完全消失。
  // 信息页停留时间 = total - 入场动画 - 收尾动画，自动推算。
  "total": %(total)g,

  // 入场动画基线时长（原项目 6.0，允许 3 ~ 10）。越小动作越快。
  "duration": %(duration)g,

  // ---------------- 触发与监听 ----------------
  // 断开→连接后 IP 仍为 169.254.x.x 时，最多等待多少秒 DHCP。
  "grace": %(grace)g,

  // 兜底轮询间隔；正常情况下由系统即时通知触发，改大也不影响灵敏度。
  "poll": %(poll)g,

  // 追加忽略的适配器关键字（子串匹配，不区分大小写）。
  // 程序已默认忽略 "Microsoft Wi-Fi Direct Virtual Adapter"。
  "ignore": [],

  // ---------------- 其它 ----------------
  // 同时有 IPv4 与 IPv6 时优先显示哪个（默认优先 IPv4）。
  "prefer_ipv6": %(prefer_ipv6)s,

  // 是否启用「名称 → IP」自动切换。
  "swap_to_ip": %(swap_to_ip)s,

  // ---------------- 语言 ----------------
  // 界面语言："cn" = 简体中文，"en" = English，"jp" = 日本語。默认 cn。
  "lang": "%(lang)s"
}
""" % {
        "scale": cfg.scale,
        "label_hold": cfg.label_hold,
        "total": cfg.total,
        "duration": cfg.duration,
        "grace": cfg.grace,
        "poll": cfg.poll,
        "prefer_ipv6": b(cfg.prefer_ipv6),
        "swap_to_ip": b(cfg.swap_to_ip),
        "lang": cfg.lang,
    }


# -------------------------------------------------------------------- 读写


def _strip_comments(text: str) -> str:
    keep = []
    for line in text.splitlines():
        head = line.lstrip()
        if head.startswith("//") or head.startswith("#"):
            continue
        keep.append(line)
    return "\n".join(keep)


def _read(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as fh:
        raw = fh.read()
    data = json.loads(_strip_comments(raw))
    if not isinstance(data, dict):
        raise ValueError("配置文件的顶层必须是一个 JSON 对象")
    return data


def _apply(cfg: Config, data: dict) -> Config:
    known = set(asdict(cfg))
    for key, value in data.items():
        if key.startswith("_"):  # 允许 "_说明" 之类的备注键
            continue
        if key not in known:
            log.warning("配置文件里的未知项已忽略：%s", key)
            continue
        setattr(cfg, key, value)
    return cfg.normalize()


def load(path: str | None = None, *, create: bool = True) -> tuple[Config, str]:
    """读取配置；文件不存在时生成默认文件。返回 `(配置, 实际路径)`。"""
    p = os.path.abspath(path) if path else default_path()
    cfg = Config().normalize()
    if not os.path.isfile(p):
        if create and not path:
            try:
                with open(p, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(_template(cfg))
                log.info("已生成默认配置文件：%s", p)
            except OSError as exc:
                log.warning("无法写入默认配置文件 %s：%s", p, exc)
        return cfg, p
    try:
        cfg = _apply(cfg, _read(p))
        log.info("已载入配置文件 %s", p)
    except Exception as exc:
        log.warning("配置文件解析失败，使用默认值：%s（%s）", p, exc)
        cfg = Config().normalize()
    for note in cfg.notes():
        log.warning("%s", note)
    return cfg, p


def describe(cfg: Config) -> str:
    return (
        f"scale={cfg.scale:g} total={cfg.total:g}s "
        f"(入场 {cfg.intro_seconds:.2f}s + 停留 {cfg.dwell_seconds:.2f}s + "
        f"收尾 {cfg.close_seconds:.2f}s = {cfg.effective_total:.2f}s) "
        f"label_hold={cfg.label_hold:g}s 换IP@{cfg.swap_seconds:.2f}s "
        f"duration={cfg.duration_clamped:g}s grace={cfg.grace:g}s poll={cfg.poll:g}s "
        f"prefer_ipv6={cfg.prefer_ipv6} swap={cfg.swap_to_ip} "
        f"lang={cfg.lang}（{i18n.LANG_NAMES.get(cfg.lang, cfg.lang)}）"
    )
