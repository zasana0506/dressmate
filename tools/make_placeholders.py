# -*- coding: utf-8 -*-
"""给样例衣橱生成占位图（色块 + 简笔轮廓）。

为什么需要：README 的截图和分享卡片要好看，但仓库里的样例衣橱
是虚构的、没有真实照片。放「无图」方块太丑。

这些图是自己画的，不含任何第三方素材，可以放心进仓库。
真实用户的衣橱永远用他们自己的照片，跟这里无关。

用法：
    python tools/make_placeholders.py
"""
import io
import json
import os
import sys

# 强制 UTF-8 输出：CI 的 locale 是 C，print 中文会抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(BASE_DIR, "samples", "wardrobe.json")
OUT_DIR = os.path.join(BASE_DIR, "samples", "photos")
SIZE = 400

# 中文色名 → RGB。取偏灰的柔和色，避免截图刺眼
COLORS = {
    "白": (238, 238, 236), "米白": (240, 234, 220), "浅灰": (206, 208, 210),
    "深灰": (110, 114, 118), "灰": (168, 170, 173), "黑": (58, 58, 62),
    "藏青": (48, 62, 96), "深蓝": (42, 66, 108), "蓝": (96, 128, 178),
    "驼": (196, 166, 128), "卡其": (198, 178, 138), "棕": (122, 88, 60),
    "深褐": (92, 68, 52), "红": (188, 78, 74), "酒红": (140, 52, 58),
    "绿": (96, 132, 92), "墨绿": (56, 92, 68), "粉": (216, 172, 172),
    "米": (238, 228, 206), "银": (198, 200, 204),
}


def pick_color(name):
    """从颜色名里认出基色，认不出就按名字长度取个稳定的灰。"""
    for k, v in COLORS.items():
        if k in (name or ""):
            return v
    return (176, 176, 172)


def shade(rgb, f):
    return tuple(max(0, min(255, int(c * f))) for c in rgb)


def contrast_ink(rgb):
    """描边色。

    背景统一是浅灰了，所以描边一律用深墨色——
    这样白衣服、黑衣服在浅底上都有清晰轮廓，
    不用再按衣服亮度分两套逻辑。
    """
    return (62, 62, 66)


def draw_item(d, kind, rgb, ink):
    """按品类画一个简笔轮廓。

    画两遍：先把所有形状用对比色画大一点（当外框），
    再用基色画一遍盖在上面。这样白 T 恤在浅米色底上也有清晰轮廓，
    黑毛衣在深色底上也不会糊成一片。
    """
    W = SIZE
    line = ink + (255,)
    fill = rgb + (255,)
    dark = shade(rgb, 0.86) + (255,)
    edge = contrast_ink(rgb) + (255,)

    # 第一遍：外框（放大 4%，用对比色）
    _draw_shapes(d, kind, edge, edge, W)
    # 第二遍：本体（基色）
    _draw_shapes(d, kind, fill, line, W)


def _draw_shapes(d, kind, fill, line, W):
    """画具体形状。fill 是填充色，line 是描边色。"""
    dark = shade(fill[:3], 0.86) + (255,) if fill != line else line

    if kind in ("shirt", "blazer", "dress_shirt"):
        # 上身：肩线 + 两侧袖子 + 下摆
        d.polygon([(W*0.30, W*0.20), (W*0.70, W*0.20), (W*0.78, W*0.34),
                   (W*0.66, W*0.40), (W*0.66, W*0.80), (W*0.34, W*0.80),
                   (W*0.34, W*0.40), (W*0.22, W*0.34)], fill=fill, outline=line, width=5)
        d.line([(W*0.50, W*0.20), (W*0.50, W*0.80)], fill=line, width=3)
        d.line([(W*0.30, W*0.20), (W*0.70, W*0.20)], fill=line, width=3)
    elif kind in ("tshirt", "sport_tshirt", "thermal", "hoodie", "fleece"):
        d.polygon([(W*0.32, W*0.22), (W*0.68, W*0.22), (W*0.74, W*0.34),
                   (W*0.64, W*0.40), (W*0.64, W*0.78), (W*0.36, W*0.78),
                   (W*0.36, W*0.40), (W*0.26, W*0.34)], fill=fill, outline=line, width=5)
        d.ellipse([W*0.42, W*0.14, W*0.58, W*0.26], fill=dark)
    elif kind in ("sweater", "cardigan"):
        d.polygon([(W*0.28, W*0.20), (W*0.72, W*0.20), (W*0.80, W*0.34),
                   (W*0.68, W*0.42), (W*0.68, W*0.82), (W*0.32, W*0.82),
                   (W*0.32, W*0.42), (W*0.20, W*0.34)], fill=fill, outline=line, width=5)
        d.line([(W*0.50, W*0.22), (W*0.50, W*0.82)], fill=line, width=3)
    elif kind in ("vest",):
        d.polygon([(W*0.34, W*0.18), (W*0.66, W*0.18), (W*0.68, W*0.82),
                   (W*0.32, W*0.82)], fill=fill, outline=line, width=5)
        d.line([(W*0.50, W*0.18), (W*0.50, W*0.82)], fill=line, width=3)
    elif kind in ("down_jacket", "coat", "trench", "jacket", "leather_jacket"):
        # 外套：更宽更长的轮廓 + 中缝
        d.polygon([(W*0.26, W*0.18), (W*0.74, W*0.18), (W*0.82, W*0.32),
                   (W*0.68, W*0.40), (W*0.68, W*0.86), (W*0.32, W*0.86),
                   (W*0.32, W*0.40), (W*0.18, W*0.32)], fill=fill, outline=line, width=5)
        d.line([(W*0.50, W*0.18), (W*0.50, W*0.86)], fill=line, width=4)
        for i in range(3):
            y = W * (0.44 + i * 0.12)
            d.ellipse([W*0.46, y, W*0.54, y + W*0.08], fill=dark)
    elif kind in ("jeans", "dress_pants", "chinos", "sport_pants", "shorts"):
        # 下装：两条裤腿
        top = W * (0.42 if kind != "shorts" else 0.48)
        bot = W * (0.92 if kind != "shorts" else 0.78)
        d.polygon([(W*0.28, top), (W*0.72, top), (W*0.70, bot),
                   (W*0.54, bot), (W*0.50, W*0.58), (W*0.46, bot),
                   (W*0.30, bot)], fill=fill, outline=line, width=5)
        d.line([(W*0.28, top), (W*0.72, top)], fill=line, width=3)
    elif kind in ("sneakers", "dress_shoes", "running_shoes", "boots"):
        # 鞋：鞋面 + 鞋底
        d.polygon([(W*0.22, W*0.62), (W*0.62, W*0.62), (W*0.78, W*0.74),
                   (W*0.76, W*0.82), (W*0.20, W*0.82)], fill=fill, outline=line, width=5)
        d.rounded_rectangle([W*0.18, W*0.82, W*0.78, W*0.88], radius=6, fill=dark, outline=line, width=4)
        if kind == "boots":
            d.rectangle([W*0.22, W*0.40, W*0.34, W*0.62], fill=fill)
    elif kind in ("hat",):
        d.ellipse([W*0.24, W*0.36, W*0.76, W*0.62], fill=fill, outline=line, width=5)
        d.ellipse([W*0.36, W*0.24, W*0.64, W*0.50], fill=fill, outline=line, width=5)
        d.ellipse([W*0.16, W*0.50, W*0.84, W*0.62], fill=dark)
    elif kind in ("scarf",):
        for i, x in enumerate((0.34, 0.46, 0.58)):
            d.rounded_rectangle([W*x, W*0.18, W*(x+0.10), W*0.84],
                                radius=10, fill=shade(fill[:3], 1 - i * 0.06),
                                outline=line, width=5)
    elif kind in ("gloves",):
        d.rounded_rectangle([W*0.26, W*0.42, W*0.46, W*0.80], radius=14, fill=fill, outline=line, width=5)
        d.rounded_rectangle([W*0.54, W*0.42, W*0.74, W*0.80], radius=14, fill=fill, outline=line, width=5)
    else:
        # 兜底：方块
        d.rounded_rectangle([W*0.28, W*0.28, W*0.72, W*0.78],
                            radius=16, fill=fill, outline=line, width=6)


def main():
    from PIL import Image, ImageDraw

    os.makedirs(OUT_DIR, exist_ok=True)
    data = json.load(io.open(SAMPLE, encoding="utf-8"))
    items = data.get("items") or []

    # 不需要字体了：缩略图尺寸下文字会糊，改为纯图形 + 底部色条

    made = 0
    for it in items:
        iid = it.get("id")
        name = it.get("name") or ""
        cat = it.get("category") or ""
        rgb = pick_color(it.get("color") or "")

        # 背景统一用中性浅灰，不跟衣服颜色走。
        # 之前背景跟着衣服颜色，结果黑毛衣配深底、黑帽子几乎看不见。
        bg_top = (247, 246, 243)
        bg_bot = (231, 229, 224)
        img = Image.new("RGB", (SIZE, SIZE), bg_top)
        dr = ImageDraw.Draw(img)
        for y in range(SIZE):
            t = y / SIZE
            dr.line([(0, y), (SIZE, y)],
                    fill=tuple(int(bg_top[i] + (bg_bot[i] - bg_top[i]) * t)
                               for i in range(3)))
        dr = ImageDraw.Draw(img)
        draw_item(dr, cat, rgb, (70, 70, 74))

        # 底部色条（用衣服颜色，一眼能认出是什么色）
        # 不写文字：这些图在推荐卡里被缩到 64px，文字会挤成一条糊边，
        # 反而显脏。名字在列表里本来就写着。
        dr.rectangle([0, SIZE - 26, SIZE, SIZE], fill=shade(rgb, 0.82))

        out = os.path.join(OUT_DIR, f"{iid}.jpg")
        img.save(out, "JPEG", quality=88)
        it["photo"] = f"photos/{iid}.jpg"
        made += 1

    # 写回样例衣橱，把 photo 字段补上
    io.open(SAMPLE, "w", encoding="utf-8").write(
        json.dumps(data, ensure_ascii=False, indent=2))
    print(f"已生成 {made} 张占位图到 {OUT_DIR}")
    print("样例衣橱的 photo 字段已补上")


if __name__ == "__main__":
    main()
