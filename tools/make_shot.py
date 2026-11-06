# -*- coding: utf-8 -*-
"""生成 README 展示图与 GitHub 分享卡片。

为什么要做分享卡片：GitHub 的 social preview 是别人在搜索结果里
第一眼看到的东西。纯网页截图塞进去又窄又乱，加个标题排版一下
才像样。

用法：
    python tools/make_shot.py <截图文件> <输出目录>
"""
import io
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

# 品牌色：与网页的深墨色一致
INK = (35, 34, 32)
PAPER = (250, 249, 246)
ACCENT = (31, 158, 117)      # 绿
MUTED = (110, 108, 104)


def render(shot_path, out_dir, wide_path=None):
    from PIL import Image, ImageDraw, ImageFont

    os.makedirs(out_dir, exist_ok=True)
    shot = Image.open(shot_path).convert("RGB")

    def font(size, bold=False):
        """找中文字体。找不到就用 PIL 默认位图字体凑合。"""
        names = (["msyhbd.ttc", "msyh.ttc", "simhei.ttf"] if bold
                 else ["msyh.ttc", "simsun.ttc", "simhei.ttf"])
        for d in (os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
                  "C:/Windows/Fonts"):
            for n in names:
                p = os.path.join(d, n)
                if os.path.exists(p):
                    try:
                        return ImageFont.truetype(p, size)
                    except Exception:
                        pass
        return ImageFont.load_default()

    # ---------- 1. README 主图：网页截图裁到重点区域 ----------
    # 上半部分留到「这身的坑」露出来，最能说明这产品在做什么
    h = min(shot.height, 1180)
    main = shot.crop((0, 0, shot.width, h))
    # 两侧留白裁掉（页面本身是居中窄列）
    main = main.crop((max(0, (main.width - 760) // 2), 0,
                      min(main.width, (main.width + 760) // 2), h))
    main_path = os.path.join(out_dir, "screenshot.png")
    main.save(main_path, "PNG", optimize=True)
    print(f"README 主图: {main_path}  {main.size[0]}x{main.size[1]}")

    # ---------- 2. 分享卡片：1280x640，左标题右截图 ----------
    # 卡片是横版的，用宽屏截图（两栏布局）比手机竖版好看
    if wide_path and os.path.exists(wide_path):
        card_src = Image.open(wide_path).convert("RGB")
    else:
        card_src = shot
    W, H = 1280, 640
    card = Image.new("RGB", (W, H), PAPER)
    dr = ImageDraw.Draw(card)

    # 左侧文字区
    x = 72
    dr.rectangle([x, 96, x + 56, 104], fill=ACCENT)          # 短线
    dr.text((x, 128), "dressmate", font=font(58, True), fill=INK)
    dr.text((x, 210), "拍照建衣橱，按天气和场合给穿搭建议",
            font=font(26), fill=INK)
    dr.text((x, 258), "19 条规则代替大模型：零 token 成本，断网也能用",
            font=font(22), fill=MUTED)

    # 特性小标签
    tags = ["零 token 成本", "断网可用", "自托管 · Docker 一键", "照片不外传"]
    tx, ty = x, 320
    for t in tags:
        tw = dr.textlength(t, font=font(19))
        dr.rounded_rectangle([tx, ty, tx + tw + 30, ty + 40], radius=20,
                             outline=(210, 208, 202), width=2)
        dr.text((tx + 15, ty + 9), t, font=font(19), fill=(70, 68, 64))
        tx += tw + 30 + 14
        if tx > 560:
            tx = x
            ty += 50

    dr.text((x, 470), "19 条可解释规则  ·  323 个城市离线坐标  ·  286 项测试",
            font=font(20), fill=(130, 128, 122))
    dr.text((x, 520), "github.com/zasana0506/dressmate",
            font=font(20), fill=ACCENT)

    # 右侧：网页截图。宽屏图裁右栏（推荐卡），竖版图裁中间
    src = card_src
    if src.width > 1000:
        # 宽屏：容器居中（1440 视口下 wrap 占 1080，左边留 180），
        # 右栏从 180+340+18=538 开始，占视口 37% 处。
        # 切 52% 会把推荐卡的左半边切掉，文字全被截断。
        left = int(src.width * 0.355)
        src = src.crop((left, 0, src.width, min(src.height, 1180)))
    else:
        src = src.crop((0, 0, src.width, min(src.height, 1180)))
        if src.width > 700:
            left = (src.width - 700) // 2
            src = src.crop((left, 0, left + 700, min(src.height, 1180)))
    # 缩放到卡片高度，同时限制最大宽度——
    # 宽屏图裁出来很宽，直接按高度缩会把左边文案全盖住
    MAX_IMG_W = 470
    scale = min((H - 80) / src.height, MAX_IMG_W / src.width)
    src = src.resize((max(1, int(src.width * scale)), H - 80), Image.LANCZOS)
    card.paste(src, (W - src.width - 0, 40))
    # 左侧与截图交界处加一条淡分隔
    dr.line([(W - src.width - 1, 40), (W - src.width - 1, H - 40)],
            fill=(228, 226, 220), width=2)

    card_path = os.path.join(out_dir, "social-preview.png")
    card.save(card_path, "PNG", optimize=True)
    print(f"分享卡片: {card_path}  {card.size[0]}x{card.size[1]}")
    return main_path, card_path


def main():
    if len(sys.argv) < 3:
        print("用法：python tools/make_shot.py <截图文件> <输出目录> [宽屏截图]")
        return 2
    shot_path = sys.argv[1]
    out_dir = sys.argv[2]
    wide = sys.argv[3] if len(sys.argv) > 3 else None
    if not os.path.exists(shot_path):
        print(f"找不到截图：{shot_path}")
        return 1
    render(shot_path, out_dir, wide)
    return 0


if __name__ == "__main__":
    sys.exit(main())
