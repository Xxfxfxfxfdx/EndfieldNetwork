"""配色 / 字体 / 几何常量 —— 对应参考项目的 `Styles/HudTheme.axaml`。

原项目配色（浅色底板 + 深色字形）在本项目里按用户要求「颜色取反」：
素材统一成"黑底白字"后，底板用深色 `#141313`、字形用浅色 `#E9E7E4`。
"""

from __future__ import annotations

import os
from functools import lru_cache

from PIL import ImageFont

__all__ = [
    "PILL",
    "RIPPLE",
    "PLATE",
    "GLYPH",
    "WHITE",
    "ACCENT",
    "DANGER",
    "OP_SECONDARY",
    "OP_TERTIARY",
    "GLOBAL_SCALE",
    "PILL_WIDTH",
    "TEXT_LEFT",
    "RIGHT_PAD",
    "TAG_CY_DY",
    "TITLE_CY_DY",
    "INFO_LINE1_DY",
    "INFO_LINE2_DY",
    "FS_TAG",
    "FS_TITLE",
    "FS_SSID",
    "FS_SUB",
    "FS_VALUE",
    "FS_UNIT",
    "PLATE_CIRCLE",
    "PLATE_SQUARE",
    "PLATE_SQUARE_RADIUS",
    "GLYPH_CIRCLE",
    "GLYPH_SQUARE",
    "font",
    "font_path",
]

# ----------------------------------------------------------------- 配色 (RGB)
PILL = (0x31, 0x2F, 0x30)          # Hud.Pill
RIPPLE = (0x65, 0x63, 0x63)        # 波纹
PLATE = (0x14, 0x13, 0x13)         # Hud.BoltDark（取反后的底板）
GLYPH = (0xE9, 0xE7, 0xE4)         # Hud.IconPlate（取反后的字形）
WHITE = (0xFF, 0xFF, 0xFF)
ACCENT = (0xC6, 0xCA, 0x4C)        # Hud.Accent（全主题唯一彩色）
DANGER = (0xFF, 0x4D, 0x4F)        # 低电量红

OP_SECONDARY = 0.55                # 次级文字
OP_TERTIARY = 0.40                 # 三级文字（TagLine）

# ----------------------------------------------------------------- 几何
GLOBAL_SCALE = 0.8                 # 原项目 GlobalScale（ScaleX/Y = 0.8）
PILL_WIDTH = 560.0                 # 胶囊固定宽度
PILL_HEIGHT_MAX = 90.0             # 画布高度 = 状态 B 的最大高度
TEXT_LEFT = 60.0                   # 状态 C 文字左边界（距胶囊左缘）
RIGHT_PAD = 32.0                   # 状态 C 右侧内边距

TAG_CY_DY = -14.0                  # 状态 B：TagLine 相对胶囊中心 y 偏移
TITLE_CY_DY = 11.0                 # 状态 B：标题相对胶囊中心 y 偏移
INFO_LINE1_DY = -10.0              # 状态 C：第一行相对胶囊中心 y 偏移
INFO_LINE2_DY = 15.0               # 状态 C：第二行相对胶囊中心 y 偏移

# 字号（逻辑像素，最终绘制时乘 S）
FS_TAG = 9.0                       # TagLineText（原 9 + LetterSpacing 2）
FS_TITLE = 26.0                    # TitleText（原 26 Bold + LetterSpacing 2）
FS_SSID = 22.0                     # WiFi SSID / 非 WiFi 的适配器名
FS_SUB = 12.0                      # 网卡名 + 频率（左下行）
FS_VALUE = 27.0                    # 链接速率数字
FS_UNIT = 15.0                     # 速率单位 / dBm

TAG_TRACKING = 2.0                 # TagLine 字距
TITLE_TRACKING = 2.0               # 标题字距

# 图标底板（原项目 CircleForm 32 / SquareForm 18，为容纳更复杂的 logo 略放大）
PLATE_CIRCLE = 34.0
GLYPH_CIRCLE = 20.0
PLATE_SQUARE = 26.0
PLATE_SQUARE_RADIUS = 6.5
GLYPH_SQUARE = 18.0

ICON_SS = 4                        # 图标超采样倍率

# ----------------------------------------------------------------- 字体
_FONT_DIRS = (
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
)

_CANDIDATES: dict[str, tuple[str, ...]] = {
    # 中文/UI：原项目字体族首选 HarmonyOS Sans SC
    "ui": ("HarmonyOS_Sans_SC_Regular.ttf", "msyh.ttc", "Deng.ttf", "simhei.ttf", "segoeui.ttf"),
    "ui_bold": ("HarmonyOS_Sans_SC_Bold.ttf", "msyhbd.ttc", "Deng.ttf", "simhei.ttf", "segoeuib.ttf"),
    # 数字：原项目用 Inter Medium，本机回退 Segoe UI Semibold
    "num": ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "HarmonyOS_Sans_SC_Bold.ttf"),
}


@lru_cache(maxsize=16)
def font_path(kind: str) -> str:
    for name in _CANDIDATES.get(kind, ()):
        if os.path.isabs(name) and os.path.exists(name):
            return name
        for d in _FONT_DIRS:
            if d:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    return p
    return ""


@lru_cache(maxsize=512)
def font(kind: str, size_px: int) -> ImageFont.FreeTypeFont:
    """按像素高度取字体；size_px 至少为 1。"""
    size = max(1, int(round(size_px)))
    path = font_path(kind)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size)
