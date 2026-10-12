"""HUD 控制器：动画时钟 + 帧循环 + 分层窗口呈现。

时间线（与原项目 `ShowAndPlayAsync` + `DwellTail` 一致）：
1. **入场** `0 → dwell_start`：完整三态动画（电标弹出 → 胶囊撑高显示标题 →
   收成圆胶囊显示信息），`state_at()` 直接取值；
2. **续住 C 态** `0 → dwell`：画面钉死在 C 态，只有 `scale_out` 保持 1；
3. **收尾** `dwell → total`：`scale_out` 1 → 0，整体缩小消失。
点击窗口立即跳到收尾。
"""

from __future__ import annotations

import time

from . import anim as A
from . import theme as T
from .content import HudContent
from .renderer import Renderer
from .win32ui_ext import (
    LayeredWindow,
    primary_work_area,
    set_dpi_awareness,
    system_dpi,
)

__all__ = ["Hud"]

FRAME_INTERVAL = 1.0 / 60.0

#: 胶囊顶边距屏幕工作区顶部的**逻辑像素**（不随缩放倍率变化，
#: 因此无论多大都贴在屏幕顶部；等价于原项目 `area.Y + 4` + 窗口内偏移）
TOP_MARGIN = 48.0

#: C 态默认停留秒数（足够读完 SSID / 速率）
DEFAULT_DWELL = 6.0

#: SSID / 适配器名称默认停留秒数（之后换成 IP）
DEFAULT_LABEL_HOLD = 3.0


class Hud:
    """一次只播放一个内容；播放中再次 `play()` 会先收尾再播新的。"""

    def __init__(
        self,
        *,
        duration: float = A.BASELINE_SECONDS,
        dwell: float = DEFAULT_DWELL,
        scale: float = 1.0,
        label_hold: float = DEFAULT_LABEL_HOLD,
        swap: bool = True,
        on_closed=None,
    ) -> None:
        set_dpi_awareness()
        self.dpi = system_dpi()
        self.ui_scale = max(1.0, self.dpi / 96.0)
        self.scale = min(4.0, max(0.35, float(scale)))
        self.base_scale = T.GLOBAL_SCALE * self.ui_scale * self.scale
        self.w = max(4, int(round(T.PILL_WIDTH * self.base_scale)))
        self.h = max(4, int(round(T.PILL_HEIGHT_MAX * self.base_scale)))
        self.duration = A.clamp_duration(duration)
        self.dwell = max(0.2, float(dwell))
        self.label_hold = max(0.0, float(label_hold))
        self.swap = bool(swap)
        self.on_closed = on_closed

        self.win = LayeredWindow(self.w, self.h, on_click=self.dismiss)
        self.area = primary_work_area()
        self.pos = self._calc_pos()

        self.content: HudContent | None = None
        self._renderer: Renderer | None = None
        self._anim: A.HudAnimation | None = None
        self._tail_total = 0.0
        self._tail_close = 0.0
        self._tail_track: A.Track | None = None

        self._phase = "idle"
        self._t0 = 0.0
        self._tail_t0 = 0.0
        self._last_frame = 0.0
        self._dismiss_at: float | None = None
        self._pending: HudContent | None = None
        self._swap_at: float | None = None
        self._content_alt: HudContent | None = None

    def apply_options(
        self,
        *,
        duration: float | None = None,
        dwell: float | None = None,
        label_hold: float | None = None,
        swap: bool | None = None,
        scale: float | None = None,
    ) -> bool:
        """热更新播放参数（配置文件改动后调用），返回是否因此改了窗口尺寸。

        除 `scale` 外都只影响**下一次** `play()`；`scale` 会立即同步窗口大小与位置，
        所以调完 `scale` 不需要重启程序。
        """
        if duration is not None:
            self.duration = A.clamp_duration(duration)
        if dwell is not None:
            self.dwell = max(0.2, float(dwell))
        if label_hold is not None:
            self.label_hold = max(0.0, float(label_hold))
        if swap is not None:
            self.swap = bool(swap)
        if scale is None:
            return False
        s = min(4.0, max(0.35, float(scale)))
        if abs(s - self.scale) < 1e-9:
            return False
        self.scale = s
        self.base_scale = T.GLOBAL_SCALE * self.ui_scale * self.scale
        self.w = max(4, int(round(T.PILL_WIDTH * self.base_scale)))
        self.h = max(4, int(round(T.PILL_HEIGHT_MAX * self.base_scale)))
        self.win.resize(self.w, self.h)
        self.pos = self._calc_pos()
        self.win.move(*self.pos)
        return True

    # ------------------------------------------------------------ 位置

    def _calc_pos(self) -> tuple[int, int]:
        """工作区顶部水平居中，顶边固定距顶 `TOP_MARGIN` 逻辑像素。

        顶边用**逻辑像素**锚定，所以缩放倍率再大也不会把胶囊顶边推出屏幕；
        水平方向严格居中，倍率过大导致窗口比屏幕还宽时两侧对称溢出。
        """
        left, top, right, bottom = self.area
        x = left + (right - left - self.w) // 2
        y = top + int(round(TOP_MARGIN * self.ui_scale))
        return x, y

    def reflow(self) -> None:
        """显示器/DPI 变化后重新计算位置。"""
        self.area = primary_work_area()
        self.pos = self._calc_pos()

    # ------------------------------------------------------------ 控制

    @property
    def busy(self) -> bool:
        return self._phase != "idle"

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def swap_at(self) -> float | None:
        """「名称 → IP」切换的绝对时刻（秒，自动画开始起算）；None 表示不切换。"""
        return self._swap_at

    @property
    def swapped(self) -> bool:
        """当前帧是否已经显示 IP。"""
        return self._content_alt is not None

    def play(self, content: HudContent) -> None:
        """立即开始播放；正在播放时先收尾，结束后自动接上新的内容。"""
        if self._phase != "idle":
            self._pending = content
            self.dismiss()
            return
        self._start(content)

    def _start(self, content: HudContent) -> None:
        self.content = content
        self._renderer = Renderer(content, self.base_scale)
        self._anim = A.HudAnimation(self.duration, outward=content.outward)
        self._tail_total, self._tail_track = self._anim.dwell_tail(self.dwell)
        self._tail_close = max(0.01, self._tail_total - self.dwell)

        # 名称停留 label_hold 秒后换成 IP（计时从信息页出现开始）
        self._swap_at = None
        self._content_alt = None
        if self.swap and self.label_hold > 0.0 and content.swap_text:
            alt = content.swapped()
            if alt is not content:
                self._swap_at = (
                    A.cue_seconds(self.duration, A.T_NUM_READY) + self.label_hold
                )
                self._content_alt = alt

        self._phase = "intro"
        self._t0 = time.perf_counter()
        self._last_frame = 0.0
        self._dismiss_at = None
        self.win.move(*self.pos)

    def dismiss(self) -> None:
        """点击关闭：跳到收尾段。"""
        if self._phase == "intro":
            self._dismiss_at = time.perf_counter()
        elif self._phase == "tail":
            now = time.perf_counter()
            if now - self._tail_t0 < self.dwell:
                self._tail_t0 = now - self.dwell

    def stop(self) -> None:
        """立刻隐藏并回到空闲。"""
        self._phase = "idle"
        self._pending = None
        self.win.hide()

    # ------------------------------------------------------------ 帧循环

    def tick(self, force: bool = False) -> None:
        """推进动画；到帧间隔才真正重绘。"""
        if self._phase == "idle":
            return
        now = time.perf_counter()
        if not force and now - self._last_frame < FRAME_INTERVAL:
            return
        self._last_frame = now
        assert self._anim is not None and self._renderer is not None
        age = now - self._t0

        if self._phase == "intro":
            t = age
            if self._dismiss_at is not None or t >= self._anim.dwell_start:
                self._phase = "tail"
                elapsed = max(0.0, t - self._anim.dwell_start)
                if self._dismiss_at is not None:
                    elapsed = self.dwell
                self._tail_t0 = now - elapsed
                st = self._anim.dwell_tail_state(
                    min(elapsed, self._tail_total), self._tail_track
                )
            else:
                st = self._anim.state_at(t)
        else:  # tail
            e = now - self._tail_t0
            if e >= self._tail_total:
                self._finish()
                return
            st = self._anim.dwell_tail_state(e, self._tail_track)

        content = self.content
        if self._content_alt is not None and self._swap_at is not None and age >= self._swap_at:
            content = self._content_alt

        img = self._renderer.render(st, content)
        if max(0.0, st.get("scale_out.sx", 1.0)) < 0.004 or max(
            0.0, st.get("pill_appear.op", 1.0)
        ) < 0.004:
            self.win.hide()
        else:
            self.win.present(img, *self.pos)
            self.win.show()

    def _finish(self) -> None:
        self.win.hide()
        self._phase = "idle"
        self._renderer = None
        self._anim = None
        if self.on_closed:
            self.on_closed()
        pending, self._pending = self._pending, None
        if pending is not None:
            self._start(pending)

    def pump(self) -> bool:
        """处理窗口消息并推进一帧；收到 WM_QUIT 返回 False。"""
        alive = self.win.pump()
        self.tick()
        return alive

    def destroy(self) -> None:
        self.win.destroy()
