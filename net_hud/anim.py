"""动画时间线 —— `Animations/HudAnimations.cs` 的逐条复刻。

基线 6.0s；入场段（cue ≤ 0.42）固定占 0.42×6 = 2.52s，与时长设置无关，
剩余时间全给"停留 + 退出"线性分配（见 _map_cue）。

所有 cue 在构建时就用 _mc() 换算成**秒**，Track.sample(seconds) 直接按秒取值。
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .easing import KS_IN, KS_INOUT, KS_OUT, KS_SMOOTH, KeySpline, back_out

__all__ = [
    "Track",
    "HudAnimation",
    "BASELINE_SECONDS",
    "INTRO_END_CUE",
    "PILL_RADIUS_A",
    "PILL_RADIUS_B",
    "PILL_HEIGHT_A",
    "PILL_HEIGHT_B",
    "ICON_OFFSET_B",
    "ICON_OFFSET_C",
    "RIPPLE_SPECS",
    "clamp_duration",
    "cue_seconds",
]

BASELINE_SECONDS = 6.0
INTRO_END_CUE = 0.42

T_START = 0.04
T_APPEAR = 0.07
T_PILL_OUT = 0.09
T_BOLT_POP = 0.10
T_EXPAND = 0.12
T_MOVE = 0.20
T_TITLE = 0.25
T_HOLD_B = 0.30
T_CONTRACT = 0.36
T_HOLD_C = 0.86
T_CLOSE = 0.89
T_NUM_IN = 0.38
T_NUM_READY = 0.42

PILL_RADIUS_A = 30.0
PILL_RADIUS_B = 18.0
PILL_HEIGHT_A = 60.0
PILL_HEIGHT_B = 90.0
ICON_OFFSET_B = -179.0
ICON_OFFSET_C = -245.0

#: 三圈波纹：(endScale, peakOpacity)
RIPPLE_SPECS: tuple[tuple[float, float], ...] = ((1.5, 0.50), (2.0, 0.50), (2.5, 0.60))


def clamp_duration(seconds: float) -> float:
    return min(10.0, max(3.0, float(seconds)))


def _map_cue(duration: float, cue: float) -> float:
    """基线 cue → 归一化时间比例 [0,1]（MapCue）。"""
    d = clamp_duration(duration)
    intro_frac = INTRO_END_CUE * BASELINE_SECONDS / d
    if cue <= INTRO_END_CUE:
        return cue / INTRO_END_CUE * intro_frac
    return intro_frac + (cue - INTRO_END_CUE) / (1.0 - INTRO_END_CUE) * (1.0 - intro_frac)


def cue_seconds(duration: float, cue: float) -> float:
    """cue 在给定动画时长下的**绝对秒数**（供上层排期用，如「信息页出现时刻」）。"""
    return _map_cue(duration, cue) * clamp_duration(duration)


class Track:
    """一条关键帧轨道；缓动挂在**段的结束关键帧**上（与 Avalonia 一致）。"""

    __slots__ = ("duration", "frames", "keys")

    def __init__(
        self,
        duration: float,
        frames: Sequence[tuple[float, KeySpline | None, dict[str, float]]],
    ) -> None:
        self.duration = duration
        self.frames = [(float(c), s, dict(v)) for c, s, v in frames]
        self.keys = tuple(self.frames[0][2].keys())

    def sample(self, seconds: float) -> dict[str, float]:
        frames = self.frames
        if seconds <= frames[0][0]:
            return dict(frames[0][2])
        if seconds >= frames[-1][0]:
            return dict(frames[-1][2])
        for i in range(len(frames) - 1):
            c0 = frames[i][0]
            c1 = frames[i + 1][0]
            if c0 <= seconds <= c1:
                span = c1 - c0
                local = 0.0 if span <= 0.0 else (seconds - c0) / span
                spline = frames[i + 1][1]
                e = local if spline is None else spline(local)
                a = frames[i][2]
                b = frames[i + 1][2]
                return {k: a[k] + (b[k] - a[k]) * e for k in a}
        return dict(frames[-1][2])


def _ripple_frames(
    m, outward: bool, end_scale: float, peak_op: float, spread: float, intensity: float
) -> list[tuple[float, KeySpline | None, dict[str, float]]]:
    target = end_scale * spread
    peak = min(1.0, peak_op * intensity)
    if outward:
        return [
            (m(0.0), None, {"op": 0.0, "sx": 0.0, "sy": 0.0}),
            (m(T_EXPAND), KS_IN, {"op": 0.0, "sx": 0.0, "sy": 0.0}),
            (m(T_EXPAND + 0.02), KS_OUT, {"op": peak, "sx": 0.05, "sy": 0.05}),
            (m(T_HOLD_B), KS_OUT, {"op": peak, "sx": target, "sy": target}),
            (m(T_CONTRACT), KS_INOUT, {"op": 0.0, "sx": target, "sy": target}),
        ]
    inner = 0.10 + end_scale * 0.032  # 1.5→0.148 / 2.0→0.164 / 2.5→0.180
    return [
        (m(0.0), None, {"op": 0.0, "sx": target, "sy": target}),
        (m(T_EXPAND), KS_OUT, {"op": 0.0, "sx": target, "sy": target}),
        (m(T_EXPAND + 0.07), KS_IN, {"op": peak, "sx": target * 0.86, "sy": target * 0.86}),
        (m(T_HOLD_B), KS_INOUT, {"op": peak, "sx": inner, "sy": inner}),
        (m(T_CONTRACT), KS_INOUT, {"op": 0.0, "sx": inner * 0.30, "sy": inner * 0.30}),
    ]


class HudAnimation:
    """一次完整播放（三态：A 圆胶囊 → B 标题高矩形 → C 信息圆胶囊 → 缩小收回）。"""

    def __init__(
        self,
        duration: float = BASELINE_SECONDS,
        *,
        outward: bool = True,
        ripple_spread: float = 1.0,
        ripple_intensity: float = 1.0,
        bounce: float = 0.275,
    ) -> None:
        d = clamp_duration(duration)
        self.duration = d
        self.outward = outward
        bo = back_out(bounce)
        m = lambda cue: _map_cue(d, cue) * d  # noqa: E731  cue → 秒

        self._m_hold_c = m(T_HOLD_C)
        self._m_close = m(T_CLOSE)

        spread = min(1.5, max(0.5, float(ripple_spread)))
        intensity = min(2.0, max(0.0, float(ripple_intensity)))

        tr: dict[str, Track] = {}
        tr["pill_corner"] = Track(d, [
            (m(0.0), None, {"cr": PILL_RADIUS_A}),
            (m(T_APPEAR), KS_IN, {"cr": PILL_RADIUS_A}),
            (m(T_EXPAND), KS_INOUT, {"cr": PILL_RADIUS_B}),
            (m(T_HOLD_B), KS_IN, {"cr": PILL_RADIUS_B}),
            (m(T_CONTRACT), KS_INOUT, {"cr": PILL_RADIUS_A}),
        ])
        tr["pill_appear"] = Track(d, [
            (m(0.0), None, {"op": 0.0, "sx": 0.6, "sy": 0.6}),
            (m(T_START), KS_IN, {"op": 0.0, "sx": 0.6, "sy": 0.6}),
            (m(T_APPEAR), KS_IN, {"op": 0.0, "sx": 0.6, "sy": 0.6}),
            (m(T_PILL_OUT), bo, {"op": 1.0, "sx": 1.0, "sy": 1.0}),
            (m(T_HOLD_C), KS_IN, {"op": 1.0, "sx": 1.0, "sy": 1.0}),
        ])
        tr["pill_height"] = Track(d, [
            (m(0.0), None, {"h": PILL_HEIGHT_A}),
            (m(T_APPEAR), KS_IN, {"h": PILL_HEIGHT_A}),
            (m(T_EXPAND), bo, {"h": PILL_HEIGHT_B}),
            (m(T_HOLD_B), KS_IN, {"h": PILL_HEIGHT_B}),
            (m(T_CONTRACT), KS_INOUT, {"h": PILL_HEIGHT_A}),
            (m(T_HOLD_C), KS_IN, {"h": PILL_HEIGHT_A}),
        ])
        tr["scale_out"] = Track(d, [
            (m(0.0), None, {"sx": 1.0, "sy": 1.0}),
            (m(T_HOLD_C), KS_IN, {"sx": 1.0, "sy": 1.0}),
            (m(T_CLOSE), KS_IN, {"sx": 0.0, "sy": 0.0}),
        ])
        tr["bolt"] = Track(d, [
            (m(0.00), None, {"op": 0.0, "sx": 0.4, "sy": 0.4, "tx": 0.0}),
            (m(T_START), KS_IN, {"op": 0.0, "sx": 0.4, "sy": 0.4, "tx": 0.0}),
            (m(T_BOLT_POP), bo, {"op": 1.0, "sx": 1.12, "sy": 1.12, "tx": 0.0}),
            (m(T_EXPAND), KS_OUT, {"op": 1.0, "sx": 1.0, "sy": 1.0, "tx": 0.0}),
            (m(T_MOVE), KS_SMOOTH, {"op": 1.0, "sx": 1.0, "sy": 1.0, "tx": ICON_OFFSET_B}),
            (m(T_HOLD_B), KS_IN, {"op": 1.0, "sx": 1.0, "sy": 1.0, "tx": ICON_OFFSET_B}),
            (m(T_CONTRACT), KS_SMOOTH, {"op": 1.0, "sx": 1.0, "sy": 1.0, "tx": ICON_OFFSET_C}),
            (m(T_HOLD_C), KS_IN, {"op": 1.0, "sx": 1.0, "sy": 1.0, "tx": ICON_OFFSET_C}),
        ])
        tr["ripple_host"] = Track(d, [
            (m(0.0), None, {"tx": 0.0}),
            (m(T_EXPAND), KS_IN, {"tx": 0.0}),
            (m(T_MOVE), KS_SMOOTH, {"tx": ICON_OFFSET_B}),
            (m(T_HOLD_B), KS_IN, {"tx": ICON_OFFSET_B}),
            (m(T_CONTRACT), KS_SMOOTH, {"tx": ICON_OFFSET_C}),
        ])
        tr["circle"] = Track(d, [
            (m(0.0), None, {"op": 0.0}),
            (m(T_START), KS_IN, {"op": 0.0}),
            (m(T_APPEAR), KS_OUT, {"op": 1.0}),
            (m(T_HOLD_B), KS_IN, {"op": 1.0}),
            (m(T_CONTRACT), KS_INOUT, {"op": 0.0}),
        ])
        tr["square"] = Track(d, [
            (m(0.0), None, {"op": 0.0}),
            (m(T_HOLD_B), KS_IN, {"op": 0.0}),
            (m(T_CONTRACT), KS_INOUT, {"op": 1.0}),
        ])
        tr["title"] = Track(d, [
            (m(0.0), None, {"op": 0.0}),
            (m(T_MOVE), KS_IN, {"op": 0.0}),
            (m(T_TITLE), KS_OUT, {"op": 1.0}),
            (m(T_HOLD_B), KS_IN, {"op": 1.0}),
            (m(T_CONTRACT), KS_INOUT, {"op": 0.0}),
        ])
        tr["num"] = Track(d, [
            (m(0.0), None, {"op": 0.0}),
            (m(T_CONTRACT), KS_IN, {"op": 0.0}),
            (m(T_NUM_IN), KS_IN, {"op": 0.0}),
            (m(T_NUM_READY), KS_OUT, {"op": 1.0}),
            (m(T_HOLD_C), KS_IN, {"op": 1.0}),
        ])
        tr["ripple_rise"] = Track(d, [
            (m(0.0), None, {"ty": 16.0}),
            (m(T_EXPAND), KS_IN, {"ty": 16.0}),
            (m(T_EXPAND + 0.02), KS_OUT, {"ty": 16.0}),
            (m(T_HOLD_B), KS_OUT, {"ty": 0.0}),
            (m(T_CONTRACT), KS_INOUT, {"ty": 0.0}),
        ])
        for idx, (es, po) in enumerate(RIPPLE_SPECS):
            tr[f"ripple{idx}"] = Track(
                d, _ripple_frames(m, outward, es, po, spread, intensity)
            )
        self.tracks = tr

    # --------------------------------------------------------------- 取值

    @property
    def close_start(self) -> float:
        """整体开始缩小的绝对时刻（秒）。"""
        return self._m_close

    @property
    def dwell_start(self) -> float:
        """C 态停留开始（= THoldC）的绝对时刻（秒）。"""
        return self._m_hold_c

    def state_at(self, seconds: float) -> dict[str, float]:
        out: dict[str, float] = {}
        for name, track in self.tracks.items():
            for key, value in track.sample(seconds).items():
                out[name + "." + key] = value
        return out

    def c_state(self) -> dict[str, float]:
        """钉死的 C 态（全部轨道按 THoldC 时刻取值）。"""
        return self.state_at(self._m_hold_c)

    # ------------------------------------------------------- 「续住 C 态」

    def dwell_tail(self, hold: float | None = None) -> tuple[float, Track]:
        """「续住 C 态」轨道 + 总时长（秒）。

        `hold` 为 C 态额外停留的秒数；None 表示沿用原项目按基线时长推出的
        `THoldC - IntroEnd`（6s 基线 → 2.64s）。
        """
        if hold is None:
            hold = self._m_hold_c - INTRO_END_CUE * BASELINE_SECONDS
        hold = max(0.0, float(hold))
        close = self.duration * (T_CLOSE - T_HOLD_C)
        total = max(0.05, hold + close)
        track = Track(total, [
            (0.0, None, {"sx": 1.0, "sy": 1.0}),
            (min(0.99, max(0.0, hold / total)), KS_IN, {"sx": 1.0, "sy": 1.0}),
            (1.0, KS_IN, {"sx": 0.0, "sy": 0.0}),
        ])
        return total, track

    def dwell_tail_state(self, elapsed: float, track: Track) -> dict[str, float]:
        """播放中再次唤起时使用：画面保持不动，只把收尾重跑一遍。"""
        state = self.c_state()
        values = track.sample(elapsed)
        state["scale_out.sx"] = values["sx"]
        state["scale_out.sy"] = values["sy"]
        return state
