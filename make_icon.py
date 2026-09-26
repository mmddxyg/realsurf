# -*- coding: utf-8 -*-
"""生成 RealSurf 应用图标：realsurf.ico（多尺寸）+ icon_preview.png。

思路：2048 超采样绘制（自带抗锯齿）→ LANCZOS 缩小 → 输出 ICO。
图案：深蓝→青 对角渐变圆角方块 + 三道海浪 + 网络信号波形（带节点）。
"""
import math

import numpy as np
from PIL import Image, ImageDraw

S = 2048            # 超采样尺寸
MAIN = 1024         # 主图尺寸
ICO_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]


def diagonal_gradient(size, c1, c2):
    y, x = np.mgrid[0:size, 0:size]
    t = (x + y) / (2.0 * (size - 1))
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for i in range(3):
        img[..., i] = (c1[i] + (c2[i] - c1[i]) * t).astype(np.uint8)
    return Image.fromarray(img, 'RGB')


def radial_glow(size, cx, cy, radius, color, alpha):
    """在透明层上画一个柔和径向光斑。"""
    layer = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(layer)
    steps = 40
    for i in range(steps, 0, -1):
        t = i / steps
        r = radius * t
        a = int(alpha * (1.0 - t) ** 1.4)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=a)
    glow = Image.new('RGBA', (size, size), color + (0,))
    glow.putalpha(layer)
    return glow


def rounded_mask(size, radius):
    m = Image.new('L', (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def wave_polygon(w, h, y_base, amp, freq, phase, steps=260):
    pts = []
    for i in range(steps + 1):
        x = w * i / steps
        y = y_base - amp * math.sin(freq * 2 * math.pi * i / steps + phase)
        pts.append((x, y))
    pts += [(w, h + 20), (0, h + 20)]
    return pts


def build():
    base = diagonal_gradient(S, (7, 24, 56), (0, 152, 200)).convert('RGBA')

    # 右上角青色柔光
    base = Image.alpha_composite(base, radial_glow(S, int(S * 0.80), int(S * 0.18),
                                                   int(S * 0.55), (60, 230, 255), 130))
    d = ImageDraw.Draw(base, 'RGBA')

    # 三道海浪（由远及近）
    d.polygon(wave_polygon(S, S, S * 0.60, S * 0.052, 1.5, 0.0), fill=(40, 190, 255, 95))
    d.polygon(wave_polygon(S, S, S * 0.69, S * 0.044, 1.9, 1.15), fill=(110, 228, 255, 150))
    d.polygon(wave_polygon(S, S, S * 0.78, S * 0.034, 2.3, 2.05), fill=(255, 255, 255, 235))

    # 网络信号波形（带节点的折线）
    line = [(0.09, 0.375), (0.225, 0.375), (0.305, 0.185),
            (0.385, 0.545), (0.465, 0.245), (0.565, 0.375), (0.915, 0.375)]
    pts = [(x * S, y * S) for x, y in line]
    lw = int(S * 0.026)
    d.line(pts, fill=(255, 255, 255, 255), width=lw, joint='curve')
    r = lw // 2
    for (x, y) in pts:
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))
    # 峰值节点用亮青色强调
    for idx in (2, 4):
        x, y = pts[idx]
        rr = int(S * 0.022)
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(90, 235, 255, 255))

    # 圆角裁切
    base.putalpha(rounded_mask(S, int(S * 0.215)))

    main = base.resize((MAIN, MAIN), Image.LANCZOS)
    main.save('realsurf.ico', format='ICO', sizes=ICO_SIZES)
    main.resize((384, 384), Image.LANCZOS).save('icon_preview.png')
    print('OK -> realsurf.ico', ICO_SIZES, '| preview 384x384')


if __name__ == '__main__':
    build()
