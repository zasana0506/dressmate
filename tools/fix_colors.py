# -*- coding: utf-8 -*-
"""用图片主色校正衣橱单品的 color 字段与名字前缀。

背景：电商标题里很多不带颜色词（001_男装夏季新款T恤...），
import_photos.infer 缺省填「黑」，结果 2000 件里大半是黑，
推荐配色直接退化成全黑，也让名字（黑短袖T恤）与实物不符。

做法：抠掉近白背景后取前三个量化色簇的平均色，按 HSV 归到中文色名。
只改 color 与名字前缀，不动 clo/正式度——那两个是文件名规则更靠谱的维度。
"""
import colorsys
import json
import os
import re
import sys
from collections import Counter

from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
from tools import import_photos as IP  # noqa: E402

PHOTO_DIR = os.path.join(BASE_DIR, "wardrobe", "photos")


def _bg_colors(im):
    """边缘出现频率 ≥2% 的量化颜色，视为背景候选（渐变底也能覆盖）。"""
    w, h = im.size
    edge = []
    for x in range(w):
        edge.append(im.getpixel((x, 0)))
        edge.append(im.getpixel((x, h - 1)))
    for y in range(h):
        edge.append(im.getpixel((0, y)))
        edge.append(im.getpixel((w - 1, y)))
    c = Counter((p[0] // 24, p[1] // 24, p[2] // 24) for p in edge)
    n = len(edge)
    return {b for b, cnt in c.items() if cnt >= n * 0.02}


def dominant_rgb(path):
    """返回主体主色（单个色簇的均值）；失败返回 None。

    两条实测教训：
    1) 只取一个簇而不是几个簇求平均——粉色 polo 配白领、红鞋配白鞋底时，
       平均会把饱和度稀释成米白／浅灰；
    2) 影棚图不一定纯白底，还有浅灰底、蓝天渐变底。只剔白底会让背景
       反成主色（PUMA 红鞋被判浅灰、深色运动裤被判浅蓝）。
       所以取中心 70% 区域判色，并剔除边缘高频色。
    """
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((96, 96), Image.LANCZOS)
            bg_bins = _bg_colors(im)
            w, h = im.size
            box = (int(w * 0.15), int(h * 0.15), int(w * 0.85), int(h * 0.85))
            center = im.crop(box)
            px = list(center.getdata())
    except Exception:
        return None

    fg = [p for p in px
          if (p[0] // 24, p[1] // 24, p[2] // 24) not in bg_bins
          and not (min(p) > 243 and max(p) - min(p) < 8)]
    if len(fg) < len(px) * 0.10:
        fg = px          # 中心几乎全是背景 → 整幅都算（例如商品很小）
    if not fg:
        return None
    bins = Counter((r // 24, g // 24, b // 24) for r, g, b in fg)
    total = len(fg)
    best, best_score = None, -1.0
    for b, cnt in bins.items():
        if cnt < total * 0.06:
            continue
        rr, gg, bb = [(c * 24 + 12) / 255.0 for c in b]
        _h, s, _v = colorsys.rgb_to_hsv(rr, gg, bb)
        score = cnt * (0.35 + s)
        if score > best_score:
            best, best_score = b, score
    if best is None:
        best = bins.most_common(1)[0][0]
    sel = [p for p in fg if (p[0] // 24, p[1] // 24, p[2] // 24) == best]
    n = len(sel)
    return (sum(p[0] for p in sel) / n, sum(p[1] for p in sel) / n, sum(p[2] for p in sel) / n)


def name_of_color(rgb):
    r, g, b = [x / 255.0 for x in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    hd = h * 360

    if v < 0.16:
        return "黑"
    if s < 0.12:
        # 米色/燕麦这类「暖白」饱和度只有 0.06~0.10，比纯白多一点黄，
        # 归成浅灰会丢掉这个色系（衣橱里米白是常用搭配色）
        if s >= 0.06 and 25 <= hd <= 65 and v > 0.55:
            return "米白"
        if v > 0.88:
            return "白"
        if v > 0.66:
            return "浅灰"
        if v > 0.40:
            return "灰"
        return "深灰" if v > 0.20 else "黑"
    # 低饱和不等于无色：浅粉、浅蓝、米黄的饱和度都在 0.15~0.30，
    # 一刀切成米白会让粉 polo 变成米白衬衫。这里按色相细分。
    if s < 0.30:
        if hd < 15 or hd >= 345:
            return "粉" if v > 0.70 else "酒红"
        if hd < 45:
            return "米白" if v > 0.82 else "卡其"
        if hd < 70:
            return "米白" if v > 0.85 else "黄"
        if hd < 160:
            return "绿"
        if hd < 265:
            return "浅蓝"
        if hd < 300:
            return "紫"
        return "粉"
    if hd < 8 or hd >= 350:
        return "酒红" if v < 0.45 else ("粉" if s < 0.45 and v > 0.75 else "红")
    if hd < 22:
        return "棕" if v < 0.55 else "橙"
    if hd < 38:
        return "驼" if s < 0.5 else ("卡其" if v < 0.6 else "橙")
    if hd < 50:
        return "驼" if v > 0.55 and s < 0.45 else "卡其"
    if hd < 70:
        return "黄" if s > 0.45 and v > 0.6 else "卡其"
    if hd < 100:
        return "墨绿" if v < 0.45 else "绿"
    if hd < 160:
        return "墨绿" if v < 0.45 else "绿"
    if hd < 200:
        return "浅蓝" if v > 0.7 and s < 0.35 else "蓝"
    if hd < 250:
        return "藏青" if v < 0.42 else ("浅蓝" if v > 0.72 else "蓝")
    if hd < 290:
        return "紫"
    if hd < 340:
        return "粉" if v > 0.6 else "酒红"
    return "红"


def strip_color(name, old):
    """把旧颜色前缀换成占位符，保留后面品类与序号。"""
    if old and name.startswith(old):
        return name[len(old):]
    return name


def main(dry=0):
    data = IP.load_wardrobe()
    items = data["items"]
    IMPORT_PREFIX = ("上衣_", "裤子_", "鞋_", "饰品_")
    changed, failed, skipped = [], 0, 0
    for it in items:
        if it.get("slot") == "accessory":
            # 首饰看的是金属色，名字里已经带了（金手链/银项链），
            # color 不能留默认的「黑」
            nm = it.get("name") or ""
            if nm.startswith("金"):
                it["color"] = "金"
            elif nm.startswith("银"):
                it["color"] = "银"
            else:
                it["color"] = "彩色"
            continue
        fname = os.path.basename(it.get("photo", ""))
        if not fname.startswith(IMPORT_PREFIX):
            skipped += 1  # 用户自己录的，不擅自改名
            continue
        path = os.path.join(PHOTO_DIR, fname)
        if not os.path.exists(path):
            failed += 1
            continue
        rgb = dominant_rgb(path)
        if not rgb:
            failed += 1
            continue
        new = name_of_color(rgb)
        old = it.get("color") or ""
        if new == old:
            continue
        it["color"] = new
        it["name"] = new + strip_color(it["name"], old)
        changed.append((old or "-", new, it["name"]))

    print(f"待改 {len(changed)} 件，读图失败 {failed} 件，跳过用户自录 {skipped} 件")
    dist = Counter(it["color"] for it in items)
    print("全橱颜色分布：", dict(dist.most_common(12)))
    if dry:
        for old, new, nm in changed[:dry]:
            print(f"  {old} → {new}  {nm}")
        print("（预览，未写入）")
        return

    # 改名后可能撞名：同色同品类加序号区分
    seen = Counter()
    for it in items:
        n = it["name"]
        seen[n] += 1
        if seen[n] > 1:
            it["name"] = f"{n}{seen[n]}"
    IP.save_wardrobe(data)
    print("已写回 wardrobe.json")


if __name__ == "__main__":
    main(dry=int(sys.argv[1]) if len(sys.argv) > 1 else 0)
