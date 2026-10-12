"""三次贝塞尔缓动 —— 等价于 Avalonia 的 KeySpline。

原项目 `Animations/HudAnimations.cs` 里定义的 KeySpline：
    KS_In    = (0.42, 0.00, 1.00, 1.00)
    KS_Out   = (0.00, 0.00, 0.58, 1.00)
    KS_InOut = (0.42, 0.00, 0.58, 1.00)
    KS_Smooth= (0.65, 0.00, 0.35, 1.00)
    BackOut  = (0.175, 0.885, 0.32, 1+BounceStrength)   BounceStrength=0.275

注意 p1y / p2y 允许 > 1（BackOut 的回弹），所以求值只能解 x 再代 y。
"""

from __future__ import annotations

__all__ = ["KeySpline", "KS_IN", "KS_OUT", "KS_INOUT", "KS_SMOOTH", "back_out"]


def _bezier(t: float, p1: float, p2: float) -> float:
    mt = 1.0 - t
    return 3.0 * mt * mt * t * p1 + 3.0 * mt * t * t * p2 + t * t * t


def _bezier_d(t: float, p1: float, p2: float) -> float:
    mt = 1.0 - t
    return 3.0 * mt * mt * p1 + 6.0 * mt * t * (p2 - p1) + 3.0 * t * t * (1.0 - p2)


def _solve_t(x: float, p1x: float, p2x: float) -> float:
    """已知曲线横坐标 x，求参数 t（牛顿迭代 + 二分兜底）。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    t = x
    for _ in range(8):
        fx = _bezier(t, p1x, p2x) - x
        if -1e-7 < fx < 1e-7:
            return t
        d = _bezier_d(t, p1x, p2x)
        if -1e-9 < d < 1e-9:
            break
        t -= fx / d
        if t < 0.0 or t > 1.0:
            break
    lo, hi, t = 0.0, 1.0, x
    for _ in range(40):
        fx = _bezier(t, p1x, p2x) - x
        if -1e-9 < fx < 1e-9:
            break
        if fx > 0.0:
            hi = t
        else:
            lo = t
        t = (lo + hi) * 0.5
    return t


class KeySpline:
    """把归一化时间 [0,1] 映射为归一化进度（可过冲）。"""

    __slots__ = ("p1x", "p1y", "p2x", "p2y", "_cache")

    def __init__(self, p1x: float, p1y: float, p2x: float, p2y: float) -> None:
        self.p1x, self.p1y, self.p2x, self.p2y = p1x, p1y, p2x, p2y
        self._cache: dict[int, float] = {}

    def __call__(self, x: float) -> float:
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        # 量化到 1/2048 缓存，避免每帧重复解方程
        key = int(x * 2048.0)
        hit = self._cache.get(key)
        if hit is None:
            xq = key / 2048.0
            hit = _bezier(_solve_t(xq, self.p1x, self.p2x), self.p1y, self.p2y)
            self._cache[key] = hit
        return hit

    def __repr__(self) -> str:  # pragma: no cover
        return f"KeySpline({self.p1x},{self.p1y},{self.p2x},{self.p2y})"


KS_IN = KeySpline(0.42, 0.0, 1.0, 1.0)
KS_OUT = KeySpline(0.0, 0.0, 0.58, 1.0)
KS_INOUT = KeySpline(0.42, 0.0, 0.58, 1.0)
KS_SMOOTH = KeySpline(0.65, 0.0, 0.35, 1.0)


def back_out(bounce: float = 0.275) -> KeySpline:
    """原项目 BackOut：p2y = 1 + BounceStrength。"""
    return KeySpline(0.175, 0.885, 0.32, 1.0 + bounce)
