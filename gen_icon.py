# -*- coding: utf-8 -*-
"""
生成苹果风格应用图标（蓝色圆角方框版，用户选定风格）
squircle 圆角矩形 + 蓝色渐变 + 白色圆角方框环 + 右上角小星芒
输出：app_icon.png (1024) / app_icon.ico (多尺寸)
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 1024
RADIUS = 232          # squircle 圆角 ≈ 22.7%（苹果规范近似）
C1 = (74, 138, 240)   # 顶部亮蓝
C2 = (43, 96, 224)    # 底部深蓝


def make_base() -> Image.Image:
    """对角渐变背景 + squircle 裁剪 + 顶部玻璃高光"""
    xx, yy = np.meshgrid(np.arange(S), np.arange(S))
    t = np.clip((xx + yy) / (2 * (S - 1)), 0, 1)[..., None].astype(np.float32)
    c1 = np.array(C1, dtype=np.float32)
    c2 = np.array(C2, dtype=np.float32)
    grad = (c1 * (1 - t) + c2 * t).astype(np.uint8)
    img = Image.fromarray(grad, "RGB").convert("RGBA")

    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, S - 1, S - 1], radius=RADIUS, fill=255)
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    base.paste(img, (0, 0), mask)

    # 顶部玻璃高光（苹果质感）
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.rounded_rectangle([-S * 0.1, -S * 0.28, S * 1.1, S * 0.52],
                         radius=int(S * 0.28), fill=(255, 255, 255, 26))
    hl = hl.filter(ImageFilter.GaussianBlur(60))
    base = Image.alpha_composite(base, hl)
    base.putalpha(Image.composite(Image.new("L", (S, S), 255),
                                  Image.new("L", (S, S), 0), mask))
    return base


def sparkle_polygon(cx, cy, r_out, rot=0.0, ctrl_frac=0.10, per_edge=90):
    """四角星芒：相邻尖角三次贝塞尔相连，控制点压近中心 → 内凹边、锐利尖"""
    tips = []
    for k in range(4):
        th = rot + k * math.pi / 2
        tips.append((cx + r_out * math.cos(th), cy + r_out * math.sin(th)))
    pts = []
    for k in range(4):
        p0 = tips[k]
        p3 = tips[(k + 1) % 4]
        bis = rot + k * math.pi / 2 + math.pi / 4
        cxy = (cx + ctrl_frac * r_out * math.cos(bis),
               cy + ctrl_frac * r_out * math.sin(bis))
        for i in range(per_edge):
            t = i / per_edge
            mt = 1 - t
            coeff = 3 * mt ** 2 * t + 3 * mt * t ** 2
            pts.append((mt ** 3 * p0[0] + coeff * cxy[0] + t ** 3 * p3[0],
                        mt ** 3 * p0[1] + coeff * cxy[1] + t ** 3 * p3[1]))
    return pts


def add_glyph(img: Image.Image) -> Image.Image:
    """白色圆角方框环（居中）+ 右上角小星芒"""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # 圆角方框环：外沿 46% 宽度，描边 ~7%，圆角为边长的 30%（一次调用画出填充+描边）
    ring_size = S * 0.46
    stroke = S * 0.068
    x0 = (S - ring_size) / 2
    y0 = (S - ring_size) / 2 + S * 0.015
    x1, y1 = x0 + ring_size, y0 + ring_size
    corner = ring_size * 0.30
    d.rounded_rectangle([x0, y0, x1, y1], radius=corner,
                        outline=(255, 255, 255, 255), width=int(stroke),
                        fill=(255, 255, 255, 18))

    # 右上角小星芒（生成魔法感）
    d.polygon(sparkle_polygon(S * 0.735, S * 0.235, S * 0.088,
                              rot=math.pi / 4, ctrl_frac=0.10),
              fill=(255, 255, 255, 250))

    out = Image.alpha_composite(img, layer)
    # 轻微内描边（小尺寸轮廓感）
    border = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(border)
    bd.rounded_rectangle([1, 1, S - 2, S - 2], radius=RADIUS - 1,
                         outline=(255, 255, 255, 28), width=3)
    return Image.alpha_composite(out, border)


def main():
    icon = add_glyph(make_base())
    here = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(here, "app_icon.png")
    ico_path = os.path.join(here, "app_icon.ico")
    icon.save(png_path)
    icon.save(ico_path, format="ICO",
              sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("saved:", png_path)
    print("saved:", ico_path)


if __name__ == "__main__":
    main()
