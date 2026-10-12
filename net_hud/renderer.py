"""把动画状态渲染成一帧 RGBA 图像。

要点（与原项目 1:1 对齐，同时避免任何位图 resize）：
* 所有几何都在**最终像素尺寸**上直接计算：`S = 0.8 × dpi_scale × scaleHost`。
* 胶囊底 + 三圈波纹用 numpy 有符号距离场做抗锯齿，并天然支持胶囊自身的
  `PillAppear` 缩放（`Sp = S × pillS`）。
* 图标与文字用 PIL 直接按最终尺寸绘制，画在同一张 RGBA 图上
  （`ImageDraw.Draw(im, "RGBA")` 是真 alpha 混合）。
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import anim as A
from . import theme as T
from .content import HudContent
from .logos import load_mask

__all__ = ["Renderer"]

#: 三圈波纹：(基准直径, 描边宽度) —— 内圈实心
RIPPLE_GEOM = ((160.0, 0.0), (220.0, 5.0), (280.0, 3.5))

_PILL_RGB = np.array(T.PILL, dtype=np.float32)
_RIPPLE_RGB = np.array(T.RIPPLE, dtype=np.float32)


def _ellipsize(text: str, fnt, max_w: float) -> str:
    """按像素宽度裁切并加省略号（用户要求：左边文字快与右边重叠时裁掉右边）。"""
    if max_w <= 0:
        return ""
    if fnt.getlength(text) <= max_w:
        return text
    ell = "…"
    ew = fnt.getlength(ell)
    if ew > max_w:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fnt.getlength(text[:mid]) + ew <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ell


def _alpha_scale(img: Image.Image, op: float) -> Image.Image:
    if op >= 0.998:
        return img
    out = img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * op)))
    return out


class Renderer:
    """按 base_scale 固定画布尺寸，逐帧产出 RGBA 图像。"""

    def __init__(self, content: HudContent, base_scale: float) -> None:
        self.content = content
        self.base_scale = float(base_scale)
        self.w = max(4, int(round(T.PILL_WIDTH * self.base_scale)))
        self.h = max(4, int(round(T.PILL_HEIGHT_MAX * self.base_scale)))
        yy, xx = np.mgrid[0 : self.h, 0 : self.w]
        self._xx = xx.astype(np.float32)
        self._yy = yy.astype(np.float32)
        self._canon: dict[tuple[str, str], Image.Image] = {}
        self._icons: dict[tuple[str, str, int], Image.Image] = {}

    # ------------------------------------------------------------ 图标

    def _glyph_layer(self, name: str, box: int) -> Image.Image:
        mask = load_mask(name)
        mw, mh = mask.size
        sc = min(box / mw, box / mh)
        nw = max(1, int(round(mw * sc)))
        nh = max(1, int(round(mh * sc)))
        resized = mask.resize((nw, nh), Image.LANCZOS)
        tinted = Image.new("RGBA", (nw, nh), T.GLYPH + (0,))
        tinted.putalpha(resized)
        layer = Image.new("RGBA", (box, box), (0, 0, 0, 0))
        layer.alpha_composite(tinted, ((box - nw) // 2, (box - nh) // 2))
        return layer

    def _canonical_icon(self, form: str, name: str) -> Image.Image:
        key = (form, name)
        cached = self._canon.get(key)
        if cached is not None:
            return cached
        ss = T.ICON_SS
        if form == "circle":
            side = max(2, int(round(T.PLATE_CIRCLE * ss)))
            gbox = max(2, int(round(T.GLYPH_CIRCLE * ss)))
        else:
            side = max(2, int(round(T.PLATE_SQUARE * ss)))
            gbox = max(2, int(round(T.GLYPH_SQUARE * ss)))
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        box = (0, 0, side - 1, side - 1)
        if form == "circle":
            draw.ellipse(box, fill=T.PLATE + (255,))
        else:
            draw.rounded_rectangle(box, radius=T.PLATE_SQUARE_RADIUS * ss, fill=T.PLATE + (255,))
        canvas.alpha_composite(self._glyph_layer(name, gbox), ((side - gbox) // 2, (side - gbox) // 2))
        self._canon[key] = canvas
        return canvas

    def _icon_at(self, form: str, name: str, plate_px: float) -> Image.Image | None:
        size = int(round(plate_px))
        if size < 2:
            return None
        key = (form, name, size)
        cached = self._icons.get(key)
        if cached is not None:
            return cached
        src = self._canonical_icon(form, name)
        out = src.resize((size, size), Image.LANCZOS)
        if len(self._icons) > 512:
            self._icons.clear()
        self._icons[key] = out
        return out

    @staticmethod
    def _paste_centered(base: Image.Image, img: Image.Image, cx: float, cy: float) -> None:
        x = int(round(cx - img.width / 2.0))
        y = int(round(cy - img.height / 2.0))
        bw, bh = base.size
        sx = max(0, -x)
        sy = max(0, -y)
        ex = min(img.width, bw - x)
        ey = min(img.height, bh - y)
        if ex <= sx or ey <= sy:
            return
        if sx or sy or ex != img.width or ey != img.height:
            img = img.crop((sx, sy, ex, ey))
        base.alpha_composite(img, (max(0, x), max(0, y)))

    # ------------------------------------------------------------ 主流程

    def render(self, st: dict[str, float], content: HudContent | None = None) -> Image.Image:
        """渲染一帧；`content` 用于播放中途替换文案（名称 → IP）。"""
        w, h = self.w, self.h
        scale_host = max(0.0, st.get("scale_out.sx", 1.0))
        S = self.base_scale * scale_host
        if S < 0.004:
            return Image.new("RGBA", (w, h), (0, 0, 0, 0))

        cx = w * 0.5
        cy = h * 0.5

        pill_s = max(0.0, st.get("pill_appear.sx", 1.0))
        pill_op = min(1.0, max(0.0, st.get("pill_appear.op", 1.0)))
        Sp = S * pill_s

        img = self._pill_layer(st, cx, cy, Sp, pill_op)

        draw = ImageDraw.Draw(img, "RGBA")
        c = content if content is not None else self.content

        # ---- 图标（替代原项目的"电标"）
        bolt_op = st.get("bolt.op", 1.0)
        if bolt_op > 0.003:
            ix = cx + st.get("bolt.tx", 0.0) * S
            iy = cy
            bs = max(0.0, st.get("bolt.sx", 1.0))
            circle_op = st.get("circle.op", 0.0)
            square_op = st.get("square.op", 0.0)
            for form, form_op, plate, base_glyph in (
                ("circle", circle_op, T.PLATE_CIRCLE, T.GLYPH_CIRCLE),
                ("square", square_op, T.PLATE_SQUARE, T.GLYPH_SQUARE),
            ):
                if form_op <= 0.003:
                    continue
                ic = self._icon_at(form, c.logo, plate * S * bs)
                if ic is None:
                    continue
                self._paste_centered(img, _alpha_scale(ic, bolt_op * form_op), ix, iy)

        # ---- 第一页：副标题 + 主标题
        title_op = st.get("title.op", 0.0)
        if title_op > 0.003:
            tag_font = T.font("ui_bold", T.FS_TAG * S)
            self._draw_tracked(
                draw, c.tagline, tag_font, cx, cy + T.TAG_CY_DY * S,
                c.tag_color + (int(255 * T.OP_TERTIARY * title_op),),
                T.TAG_TRACKING * S,
            )
            t_font = T.font("ui_bold", T.FS_TITLE * S)
            self._draw_tracked(
                draw, c.title, t_font, cx, cy + T.TITLE_CY_DY * S,
                T.WHITE + (int(255 * title_op),), T.TITLE_TRACKING * S,
            )

        # ---- 第二页：信息
        num_op = st.get("num.op", 0.0)
        if num_op > 0.003:
            self._draw_info(draw, c, cx, cy, S, num_op)

        return img

    # ------------------------------------------------------- 胶囊 + 波纹

    def _pill_layer(
        self, st: dict[str, float], cx: float, cy: float, Sp: float, pill_op: float
    ) -> Image.Image:
        w, h = self.w, self.h
        xx, yy = self._xx, self._yy

        pw = T.PILL_WIDTH * Sp
        ph = max(0.0, st.get("pill_height.h", A.PILL_HEIGHT_A) * Sp)
        hw = pw * 0.5
        hh = ph * 0.5
        rr = max(0.0, min(st.get("pill_corner.cr", A.PILL_RADIUS_A) * Sp, hw, hh))

        qx = np.abs(xx - cx) - (hw - rr)
        qy = np.abs(yy - cy) - (hh - rr)
        d = (
            np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
            + np.minimum(np.maximum(qx, qy), 0.0)
            - rr
        )
        cov = np.clip(0.5 - d, 0.0, 1.0).astype(np.float32)

        ra = np.zeros((h, w), dtype=np.float32)
        rcx = cx + st.get("ripple_host.tx", 0.0) * Sp
        rcy = cy + st.get("ripple_rise.ty", 0.0) * Sp
        for i, (dia, stroke) in enumerate(RIPPLE_GEOM):
            op = st.get(f"ripple{i}.op", 0.0)
            if op <= 0.003:
                continue
            sx = st.get(f"ripple{i}.sx", 0.0)
            sy = st.get(f"ripple{i}.sy", 0.0)
            a = dia * 0.5 * sx * Sp
            b = dia * 0.5 * sy * Sp
            if a < 0.05 or b < 0.05:
                continue
            dx = (xx - rcx) / a
            dy = (yy - rcy) / b
            r = np.sqrt(dx * dx + dy * dy)
            m = min(a, b)
            if stroke <= 0.0:
                ring = np.clip(0.5 - (r - 1.0) * m, 0.0, 1.0)
            else:
                sw = stroke * 0.5 * Sp
                ring = np.clip(0.5 - (np.abs(r - 1.0) * m - sw), 0.0, 1.0)
            np.maximum(ra, ring * op, out=ra)

        ra *= cov
        rgb = _PILL_RGB[None, None, :] + (_RIPPLE_RGB - _PILL_RGB)[None, None, :] * ra[:, :, None]

        arr = np.empty((h, w, 4), dtype=np.uint8)
        arr[:, :, :3] = np.clip(rgb, 0.0, 255.0).astype(np.uint8)
        arr[:, :, 3] = (np.clip(cov * pill_op, 0.0, 1.0) * 255.0).astype(np.uint8)
        return Image.fromarray(arr, "RGBA")

    # ------------------------------------------------------------- 文字

    @staticmethod
    def _draw_tracked(
        draw: ImageDraw.ImageDraw,
        text: str,
        fnt,
        cx: float,
        cy: float,
        fill,
        tracking: float,
    ) -> None:
        if not text:
            return
        widths = [fnt.getlength(ch) for ch in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = cx - total * 0.5
        for ch, cw in zip(text, widths):
            draw.text((x, cy), ch, font=fnt, fill=fill, anchor="lm")
            x += cw + tracking

    def _draw_info(
        self,
        draw: ImageDraw.ImageDraw,
        c: HudContent,
        cx: float,
        cy: float,
        S: float,
        op: float,
    ) -> None:
        pill_left = cx - T.PILL_WIDTH * S * 0.5
        left_x = pill_left + T.TEXT_LEFT * S
        right_x = cx + T.PILL_WIDTH * S * 0.5 - T.RIGHT_PAD * S

        y1 = cy + T.INFO_LINE1_DY * S
        y2 = cy + T.INFO_LINE2_DY * S
        a_main = int(255 * op)
        a_sub = int(255 * op * T.OP_SECONDARY)

        f_val = T.font("num", T.FS_VALUE * S)
        f_unit = T.font("num", T.FS_UNIT * S)
        f_l1 = T.font("ui_bold", T.FS_SSID * S)
        f_l2 = T.font("ui", T.FS_SUB * S)

        # 单行（无左下行）时左右两列都垂直居中于胶囊中心
        two_line = bool(c.line2)
        ly1 = y1 if two_line else cy
        ry1 = y1 if two_line else cy
        gap = 12.0 * S

        # ---- 右列（先算宽度，左列据此裁切）
        gap_unit = 4.0 * S
        unit_w = f_unit.getlength(c.unit) if c.unit else 0.0
        val_w = f_val.getlength(c.value) if c.value else 0.0
        right_w1 = val_w + (gap_unit + unit_w if unit_w else 0.0)
        right_w2 = f_unit.getlength(c.sub) if c.sub else 0.0
        if c.value:
            if unit_w:
                draw.text((right_x, ry1), c.unit, font=f_unit,
                          fill=T.WHITE + (a_sub,), anchor="rm")
                draw.text((right_x - unit_w - gap_unit, ry1), c.value, font=f_val,
                          fill=T.WHITE + (a_main,), anchor="rm")
            else:
                draw.text((right_x, ry1), c.value, font=f_val,
                          fill=T.WHITE + (a_main,), anchor="rm")
        if c.sub:
            draw.text((right_x, y2), c.sub, font=f_unit,
                      fill=T.WHITE + (a_sub,), anchor="rm")

        # ---- 左列（超宽按用户要求裁切并加省略号；IP 则先自动缩字号）
        avail1 = (right_x - right_w1) - gap - left_x
        if c.line1_is_ip:
            l1, f_l1 = self._fit_font(c.line1, "ui_bold", T.FS_SSID * S, avail1,
                                      min_px=T.FS_SUB * S)
            if f_l1.getlength(l1) > avail1:
                l1 = _ellipsize(l1, f_l1, avail1)
        else:
            l1 = _ellipsize(c.line1, f_l1, avail1)
        draw.text((left_x, ly1), l1, font=f_l1, fill=T.WHITE + (a_main,), anchor="lm")
        if two_line:
            avail2 = (right_x - right_w2) - gap - left_x
            l2 = _ellipsize(c.line2, f_l2, avail2)
            draw.text((left_x, y2), l2, font=f_l2, fill=T.WHITE + (a_sub,), anchor="lm")

    @staticmethod
    def _fit_font(text: str, kind: str, size_px: float, max_w: float, min_px: float):
        """尽量用原始字号；放不下就按比例缩小（长 IPv6 用），返回 `(文本, 字体)`。"""
        fnt = T.font(kind, size_px)
        if not text or max_w <= 0 or size_px <= 0:
            return text, fnt
        width = fnt.getlength(text)
        for _ in range(4):
            if width <= max_w or width <= 0:
                break
            nxt = max(min_px, size_px * max_w / width * 0.99)
            if nxt >= size_px - 0.05:
                break
            size_px = nxt
            fnt = T.font(kind, size_px)
            width = fnt.getlength(text)
        return text, fnt
