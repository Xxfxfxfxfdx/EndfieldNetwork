"""Logo 素材处理。

`assets/*.png` 是 1:1 的二值图，白底的按用户要求取反成"黑底白字"，
再按字形外接矩形裁切并缓存成 L 模式遮罩（白=字形）。
"""

from __future__ import annotations

import os
from functools import lru_cache

from PIL import Image

__all__ = ["LOGO_NAMES", "ASSETS_DIR", "load_mask", "export_normalized"]

#: 五个素材 → 用途
LOGO_NAMES = ("wifi", "ethernet", "btpan", "usb_rndis", "nointernet")

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
NORMALIZED_DIR = os.path.join(ASSETS_DIR, "normalized")

_BORDER_EPS = 8


def _is_light_background(gray: Image.Image) -> bool:
    """取四条边框像素均值判断底色：<128 视为黑底（无需取反）。"""
    w, h = gray.size
    px = gray.load()
    total = 0
    count = 0
    step = max(1, min(w, h) // 64)
    for x in range(0, w, step):
        total += px[x, 0] + px[x, h - 1]
        count += 2
    for y in range(0, h, step):
        total += px[0, y] + px[w - 1, y]
        count += 2
    return (total / max(1, count)) >= 128


def normalize(src_path: str) -> Image.Image:
    """读入素材 → 统一成"黑底白字" → 裁到字形外接矩形。返回 L 模式图。"""
    with Image.open(src_path) as im:
        gray = im.convert("L")
        if _is_light_background(gray):
            gray = gray.point(lambda v: 255 - v)
        mask = gray.point(lambda v: v if v > _BORDER_EPS else 0)
        bbox = mask.getbbox()
        if bbox:
            mask = mask.crop(bbox)
        return mask


@lru_cache(maxsize=32)
def load_mask(name: str) -> Image.Image:
    """按名字取字形遮罩（L 模式，255=字形）。优先用 `assets/normalized/`。"""
    norm = os.path.join(NORMALIZED_DIR, name + ".png")
    if os.path.exists(norm):
        with Image.open(norm) as im:
            return im.convert("L").copy()
    src = os.path.join(ASSETS_DIR, name + ".png")
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    return normalize(src)


def export_normalized(force: bool = False) -> list[str]:
    """把取反/裁切后的结果写回 `assets/normalized/`，方便肉眼核对。"""
    os.makedirs(NORMALIZED_DIR, exist_ok=True)
    written: list[str] = []
    for name in LOGO_NAMES:
        src = os.path.join(ASSETS_DIR, name + ".png")
        dst = os.path.join(NORMALIZED_DIR, name + ".png")
        if not os.path.exists(src):
            continue
        if force or not os.path.exists(dst):
            normalize(src).save(dst)
            written.append(dst)
    return written
