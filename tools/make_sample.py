# -*- coding: utf-8 -*-
"""生成公开样例衣橱（samples/wardrobe.json）。

为什么要单独生成，而不是直接用真实衣橱：
仓库要公开，真实衣橱里的 1989 件商品图来自电商平台，不能随代码分发。
所以这里用一套完全虚构的衣橱重建同样的数据结构——字段、取值范围、
保暖值曲线都和真实标注一致，别人拿到后既能看懂引擎的输入长什么样，
也能立刻跑出推荐结果。

photo 字段留空：没有真实图片时，前端会自动显示占位方块。
"""

# -*- coding: utf-8 -*-
# 强制 UTF-8 输出：CI（GitHub Actions 的 Ubuntu runner）默认 locale 是 C，
# Python 3.7+ 在那种环境下用 ASCII 编码 stdout，print 中文会抛
# UnicodeEncodeError —— 本地 Windows 中文环境却是好的，很难本地复现。
# 这里显式把 stdout/stderr 换成 UTF-8，与运行环境无关。
import io as _io
import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(BASE_DIR, "samples", "wardrobe.json")

# 每一件：id, 名称, 层位, 品类, 颜色, 材质, 保暖值, 正式度, 季节, 附加属性
ITEMS = [
    # ---------------- 内层 base ----------------
    ("s001", "白色棉质短袖T恤", "base", "tshirt", "白", "棉", 0.15, 1,
     ["spring", "summer", "autumn"], {}),
    ("s002", "藏青长袖衬衫", "base", "shirt", "藏青", "棉", 0.20, 3,
     ["spring", "autumn", "winter"], {}),
    ("s003", "黑色保暖打底衫", "base", "thermal", "黑", "莫代尔", 0.26, 0,
     ["autumn", "winter"], {}),
    ("s004", "灰色速干运动T恤", "base", "sport_tshirt", "灰", "涤纶", 0.16, 1,
     ["spring", "summer", "autumn"], {"sport": True}),
    ("s005", "米白真丝衬衫", "base", "shirt", "米白", "真丝", 0.18, 4,
     ["spring", "autumn"], {}),

    # ---------------- 中层 mid ----------------
    ("s010", "灰色连帽卫衣", "mid", "hoodie", "灰", "棉混纺", 0.38, 1,
     ["spring", "autumn", "winter"], {}),
    ("s011", "驼色羊绒开衫", "mid", "cardigan", "驼", "羊绒", 0.42, 3,
     ["autumn", "winter"], {}),
    ("s012", "黑色羊毛毛衣", "mid", "sweater", "黑", "羊毛", 0.42, 2,
     ["autumn", "winter"], {}),
    ("s013", "藏青羊绒圆领针织衫", "mid", "sweater", "藏青", "羊绒", 0.44, 3,
     ["autumn", "winter"], {}),
    ("s014", "灰色薄羊毛马甲", "mid", "vest", "灰", "羊毛", 0.24, 3,
     ["spring", "autumn"], {}),
    ("s015", "黑色半拉链抓绒上衣", "mid", "fleece", "黑", "抓绒", 0.40, 1,
     ["autumn", "winter"], {}),

    # ---------------- 外层 outer ----------------
    ("s020", "深灰长款羽绒服", "outer", "down_jacket", "灰", "羽绒", 0.92, 1,
     ["winter"], {"waterproof": True, "windproof": True}),
    ("s021", "米白短款羽绒服", "outer", "down_jacket", "米白", "羽绒", 0.92, 1,
     ["winter"], {"waterproof": True, "windproof": True}),
    ("s022", "藏青单排扣西装外套", "outer", "blazer", "藏青", "羊毛混纺", 0.38, 4,
     ["spring", "autumn"], {}),
    ("s023", "驼色风衣", "outer", "trench", "驼", "棉混纺", 0.40, 3,
     ["spring", "autumn"], {"waterproof": True, "windproof": True}),
    ("s024", "黑色羊毛大衣", "outer", "coat", "黑", "羊毛", 0.65, 4,
     ["autumn", "winter"], {"windproof": True}),
    ("s025", "深蓝防风冲锋衣", "outer", "jacket", "深蓝", "涤纶", 0.38, 1,
     ["spring", "autumn", "winter"], {"waterproof": True, "windproof": True}),
    ("s026", "黑色皮夹克", "outer", "leather_jacket", "黑", "真皮", 0.36, 3,
     ["spring", "autumn"], {"windproof": True}),

    # ---------------- 下装 bottom ----------------
    ("s030", "深蓝直筒牛仔裤", "bottom", "jeans", "深蓝", "棉", 0.28, 1,
     ["spring", "autumn", "winter"], {}),
    ("s031", "炭灰西裤", "bottom", "dress_pants", "炭灰", "羊毛混纺", 0.26, 4,
     ["spring", "autumn", "winter"], {}),
    ("s032", "卡其直筒长裤", "bottom", "chinos", "卡其", "棉混纺", 0.26, 2,
     ["spring", "autumn"], {}),
    ("s033", "黑色修身西裤", "bottom", "dress_pants", "黑", "羊毛", 0.24, 4,
     ["spring", "autumn", "winter"], {}),
    ("s034", "灰色运动长裤", "bottom", "sport_pants", "灰", "涤纶", 0.26, 0,
     ["spring", "summer", "autumn"], {"sport": True}),
    ("s035", "米白亚麻短裤", "bottom", "shorts", "米白", "亚麻", 0.10, 1,
     ["summer"], {}),

    # ---------------- 鞋 shoes ----------------
    ("s040", "白色简洁运动鞋", "shoes", "sneakers", "白", "皮革", 0.16, 1,
     ["spring", "summer", "autumn", "winter"], {}),
    ("s041", "深棕皮质系带鞋", "shoes", "dress_shoes", "棕", "真皮", 0.20, 4,
     ["spring", "autumn", "winter"], {}),
    ("s042", "黑色切尔西靴", "shoes", "boots", "黑", "真皮", 0.28, 3,
     ["autumn", "winter"], {"waterproof": True}),
    ("s043", "灰色跑步鞋", "shoes", "running_shoes", "灰", "网布", 0.14, 0,
     ["spring", "summer", "autumn"], {"sport": True}),

    # ---------------- 配饰 accessory ----------------
    ("s050", "黑色棒球帽", "accessory", "hat", "黑", "棉", 0.04, 1,
     ["spring", "summer", "autumn"], {}),
    ("s051", "深灰羊毛围巾", "accessory", "scarf", "深灰", "羊毛", 0.10, 3,
     ["autumn", "winter"], {}),
    ("s052", "棕色皮质手套", "accessory", "gloves", "棕", "真皮", 0.06, 3,
     ["winter"], {}),
]


def build():
    items = []
    for (iid, name, slot, cat, color, mat, clo, formal,
         seasons, extra) in ITEMS:
        it = {
            "id": iid,
            "name": name,
            "photo": "",
            "slot": slot,
            "category": cat,
            "color": color,
            "material": mat,
            "clo": clo,
            "formality": formal,
            "waterproof": bool(extra.get("waterproof")),
            "windproof": bool(extra.get("windproof")),
            "sun_protective": bool(extra.get("sun_protective")),
            "sport": bool(extra.get("sport")),
            "season": seasons,
            "status": "clean",
            "last_worn": None,
            "wear_count": 0,
            "needs_review": False,
            "gender": "neutral",
        }
        items.append(it)
    return {
        "_note": "dressmate 公开样例衣橱：完全虚构，用于演示引擎能力。"
                 "真实衣橱请通过网页上传或 tools/import_photos.py 导入。",
        "items": items,
    }


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    data = build()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    slots = {}
    for it in data["items"]:
        slots[it["slot"]] = slots.get(it["slot"], 0) + 1
    print(f"已生成 {OUT_PATH}")
    print(f"共 {len(data['items'])} 件：" +
          " ".join(f"{k} {v}" for k, v in sorted(slots.items())))


if __name__ == "__main__":
    main()
