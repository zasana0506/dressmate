"""重建「饰品」类单品的属性：款式、金属、宝石、真实颜色。

原来这 500 件只有 name（金手链/银手链）和 color（金/银/彩色），
拿不出任何可以用来判断搭配的信息——500 件在推荐里等价于 3 件。

这个脚本做四件事：

1. 分款式：项链/吊坠/耳钉/耳环/胸针/手链/手镯/戒指/脚链/发饰。
   耳钉和耳环不是一回事（后者只在正式场合成立），胸针必须有外套，
   这些以前全挤在 earring/necklace 里，等于没有类型。
2. 金属与颜色分离：金/银是材质不是颜色。单列 metal + tone（冷暖），
   衣服偏暖配金、偏冷配银才是真的搭配知识；把「金」当颜色去数色系是错的。
3. 补齐彩色：文件名里的红绳/绿玉/珍珠白，图像主色兜底。
   纯金属素圈首饰 color 留空——它不占色系位。
4. 剔除非穿搭件：这个文件夹其实是电商杂货（瓷砖找平器、文件柜卡扣、
   美发器、小汽车），另有臂章肩章标牌礼盒，标 non_wearable 不进配饰池。
   帽子单独归 category=hat，那是真能用的配饰（防晒/保暖）。

用法：
    python tools/fix_jewelry.py          # 执行
    python tools/fix_jewelry.py --dry    # 只看统计，不写盘
"""
import colorsys
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from tools import import_photos as IP
from tools.fix_colors import dominant_rgb

WARDROBE = os.path.join("wardrobe", "wardrobe.json")
PHOTOS = os.path.join("wardrobe", "photos")

# 款式词。顺序即优先级：「耳钉」必须先于「耳环」被匹配，
# 否则「耳钉耳环两戴」会被判成耳环，日常场合就上不了。
TYPE_WORDS = [
    ("brooch", ["胸针", "胸花", "别针"]),
    ("stud", ["耳钉", "耳夹"]),
    ("earring", ["耳环", "耳饰", "耳坠", "耳线", "耳钩"]),
    ("necklace", ["项链", "锁骨链", "颈链"]),
    ("pendant", ["吊坠", "项坠", "挂坠"]),
    ("bangle", ["手镯", "手环"]),
    ("bracelet", ["手链", "手串", "手绳", "红绳", "编绳", "手编绳"]),
    ("ring", ["戒指", "指环"]),
    ("anklet", ["脚链", "脚绳"]),
    ("hair", ["发夹", "发箍", "发带", "发簪", "发卡", "发饰"]),
]

TYPE_CN = {
    "brooch": "胸针", "stud": "耳钉", "earring": "耳环", "necklace": "项链",
    "pendant": "吊坠", "bangle": "手镯", "bracelet": "手链", "ring": "戒指",
    "anklet": "脚链", "hair": "发饰",
}

# 不是穿搭单品：这个文件夹混进来的杂货，以及「头绳/皮筋」这类消耗品。
# 注意「头绳」不算发饰——它是绑头发用的，不参与搭配。
JUNK_WORDS = [
    "臂章", "肩章", "袖标", "胸章", "胸牌", "标牌", "反光", "领花", "帽徽", "肩牌", "领章",
    "礼盒", "包装", "首饰盒", "钥匙扣",
    "找平", "瓷砖", "卡扣", "隔板", "拖书架", "飘窗垫", "太阳能", "文件柜", "台垫",
    "海绵", "卡座", "面具", "美发器", "卷发棒", "直发梳", "夹板", "小汽车", "玩具",
    "火箭", "钢丝绳", "钢线卡子", "芯片",
    # 发绳发圈是消耗品不是发饰，扎头发用的东西不参与搭配
    "头绳", "皮筋", "橡皮筋", "毛巾圈", "发绳", "发圈",
    # 杂货堆里剩下的一律不进池
    "卡子", "沙发", "电瓶", "搭火线", "多规格", "加厚皮质", "补贴",
]
HAT_WORDS = ["遮阳帽", "防晒帽", "防寒帽", "工作帽", "鸭舌帽", "渔夫帽", "棒球帽",
             "草帽", "毛线帽", "帽子"]

# 金属：先匹配长词，且银要先于金判——「925纯银电镀白金」这种标题里
# 「金」只是「白金」的一部分，被单字「金」抢先就会把银色首饰记成金色。
# 单字「金」不进词表：命中「金属/合金/彩金」的概率比命中真金还高。
METAL_WORDS = [
    ("tungsten", ["钨金", "钨钢"]),   # 碳化钨：镜面银白或黑，冷暖中性
    ("dark", ["钛钢", "不锈钢", "黑金"]),
    ("rose", ["玫瑰金"]),
    ("silver", ["足银", "纯银", "s925", "925", "银", "白金", "铂金"]),
    ("gold", ["足金", "黄金", "硬金", "18k金", "18k", "k金", "千足金"]),
]
# 冷暖决定它配什么色调的衣服：金配暖色系，银配冷色系。
METAL_TONE = {"gold": "warm", "rose": "warm", "silver": "cool",
              "tungsten": "neutral", "dark": "neutral"}
METAL_CN = {"gold": "金", "rose": "玫瑰金", "silver": "银", "dark": "钨金",
            "tungsten": "钨金", "": ""}

# 宝石决定点缀色：玉是绿的、珍珠是白的，这些不靠猜。
GEM_WORDS = [
    ("jade", ["和田玉", "翡翠", "玉"]),
    ("pearl", ["珍珠", "贝母"]),
    ("diamond", ["莫桑", "钻石", "锆石", "水钻", "钻"]),
    ("crystal", ["水晶"]),
    ("agate", ["玛瑙"]),
    ("turquoise", ["绿松石"]),
    ("amber", ["琥珀", "蜜蜡"]),
]
GEM_COLOR = {"jade": "绿", "pearl": "白", "diamond": "白", "crystal": "白",
             "agate": "红", "turquoise": "蓝", "amber": "黄"}

# 颜色词只从标题里找，且必须先剥掉金属/宝石词——
# 「黄金」里的「金」、「莫桑钻」里的「钻」都不是颜色。
COLOR_WORDS = ["藏青", "酒红", "米白", "深蓝", "浅蓝", "天蓝", "墨绿",
               "红", "粉", "蓝", "绿", "紫", "黄", "橙", "黑", "白", "灰", "棕", "咖"]

HAT_CLO = {"防寒帽": 0.12, "毛线帽": 0.12, "渔夫帽": 0.04, "草帽": 0.02,
           "遮阳帽": 0.02, "防晒帽": 0.02, "棒球帽": 0.03, "鸭舌帽": 0.03,
           "工作帽": 0.04, "帽子": 0.03}


def metal_of(text):
    low = text.lower()
    for metal, words in METAL_WORDS:
        for w in words:
            if w.lower() in low:
                return metal
    return ""


def gem_of(text):
    for gem, words in GEM_WORDS:
        if any(w in text for w in words):
            return gem
    return ""


def type_of(text):
    for jtype, words in TYPE_WORDS:
        if any(w in text for w in words):
            return jtype
    return ""


def is_metal_color(rgb):
    """图像主色是不是金属/白底。是的话不能当点缀色，否则每件首饰都「金」。"""
    if not rgb:
        return True
    r, g, b = [v / 255.0 for v in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    hd = h * 360
    if s < 0.18:                     # 无彩度：白/灰/银
        return True
    if 35 <= hd <= 60 and v > 0.35:  # 金黄
        return True
    return False


def color_of(text, metal, gem, photo_path):
    """点缀色。顺序：标题明说的 > 宝石默认色 > 图像主色 > 留空。"""
    probe = text.lower()
    for w in [x for _m, ws in METAL_WORDS for x in ws] + [x for _g, ws in GEM_WORDS for x in ws]:
        probe = probe.replace(w.lower(), "")
    for w in COLOR_WORDS:
        if w in probe:
            return w
    if gem:
        return GEM_COLOR.get(gem, "")
    full = os.path.join(PHOTOS, os.path.basename(photo_path)) if photo_path else ""
    if full and os.path.exists(full):
        rgb = dominant_rgb(full)
        if not is_metal_color(rgb):
            from tools.fix_colors import name_of_color
            c = name_of_color(rgb)
            # 「金/银」是材质不是颜色，落到这里说明是误判，宁可留空
            return "" if c in ("金", "银", "彩色") else c
    return ""


def make_name(metal, gem, jtype, color, fallback):
    """名字只写能区分的字段：金属 + 宝石 > 金属 + 颜色。

    有宝石时不再重复颜色（银玉手链，不写「银绿玉手链」）；
    没宝石时颜色才有区分意义（银粉手链 / 银黑项链）。
    白色不写——白珍珠、白钻写出来是废话。
    """
    parts = []
    if not gem and color and color != "白":
        parts.append(color)
    parts.append(METAL_CN.get(metal, ""))
    gem_cn = {"jade": "玉", "pearl": "珠", "diamond": "钻", "crystal": "晶",
              "agate": "玛瑙", "turquoise": "松石", "amber": "蜜蜡"}.get(gem, "")
    if gem_cn:
        parts.append(gem_cn)
    parts.append(TYPE_CN.get(jtype, "首饰"))
    name = "".join(p for p in parts if p)
    return name or fallback or "首饰"


def hat_name(text):
    for w in ["防寒帽", "毛线帽", "遮阳帽", "防晒帽", "棒球帽", "鸭舌帽",
              "渔夫帽", "草帽", "工作帽"]:
        if w in text:
            return w
    return "帽子"


def hat_clo(text):
    for w, clo in HAT_CLO.items():
        if w in text:
            return clo
    return 0.03


def main(dry=False):
    data = IP.load_wardrobe()
    items = data["items"]
    targets = [it for it in items if it.get("category") == "jewelry"]
    print(f"待处理 {len(targets)} 件")

    stats = Counter()
    names_used = Counter()
    for it in targets:
        photo = it.get("photo", "")
        fname = os.path.basename(photo)
        # 原始标题在 photo 名里（导入时保留了全名），属性都从这里读
        text = os.path.splitext(fname)[0]

        if any(w in text for w in JUNK_WORDS):
            it["non_wearable"] = True
            it["category"] = "junk"
            stats["非穿搭件（排除）"] += 1
            continue

        if any(w in text for w in HAT_WORDS):
            it["category"] = "hat"
            it["jewelry_type"] = ""
            it["clo"] = hat_clo(text)
            it["formality"] = 2 if "防寒" in text or "毛线" in text else 1
            it["color"] = "黑" if "黑" in text else ("白" if "白" in text else "米白")
            base = hat_name(text)
            it["name"] = _uniq(base, names_used)
            stats[f"帽子"] += 1
            continue

        jtype = type_of(text)
        # 没有款式词的首饰不进配饰池：不知道是项链还是胸针，
        # 就判断不了它适合什么场合、别在哪里。宁缺毋滥。
        if not jtype:
            it["non_wearable"] = True
            it["category"] = "junk"
            stats["非穿搭件（无款式词）"] += 1
            continue
        metal = metal_of(text)
        gem = gem_of(text)
        color = color_of(text, metal, gem, photo)

        it["jewelry_type"] = jtype
        it["metal"] = metal
        it["tone"] = METAL_TONE.get(metal, "neutral")
        it["gem"] = gem
        it["color"] = color
        # 首饰不保暖，材质字段以前被衣服规则误判成「羊毛/加绒」，清掉
        it["material"] = {"gold": "足金", "rose": "玫瑰金", "silver": "银",
                          "dark": "钨金", "tungsten": "钨金"}.get(metal, "")
        it["formality"] = 3 if jtype in ("necklace", "pendant", "earring", "ring") else 2
        it["name"] = _uniq(make_name(metal, gem, jtype, color, it.get("name")), names_used)
        stats[TYPE_CN.get(jtype, "无款式词")] += 1

    print("\n结果：")
    for k, v in stats.most_common():
        print(f"  {k}: {v}")

    if dry:
        print("\n--dry 模式，未写盘")
        for it in targets[:12]:
            print("  ", it.get("name"), "|", it.get("jewelry_type"), it.get("metal"),
                  it.get("color"), "| 原:", it.get("photo", "")[7:30])
        return data

    IP.save_wardrobe(data)
    print(f"\n已写盘 {WARDROBE}")
    return data


def _uniq(name, used):
    used[name] += 1
    return name if used[name] == 1 else f"{name}{used[name]}"


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
