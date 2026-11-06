# -*- coding: utf-8 -*-
"""照片批量打标：扫描 wardrobe/photos/ 下的照片，调用视觉模型识别，
把新单品写入 wardrobe/wardrobe.json。

两种用法：
1. 交互式：python tools/label_photos.py --plan
   → 生成待标注清单，人工确认分类
2. 自动：  python tools/label_photos.py --auto
   → 调视觉模型自动填写全部字段

依赖：需要配置视觉模型 API（见下）。未配置时 --plan 仍可生成清单。
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(BASE_DIR, "wardrobe", "photos")
WARDROBE_PATH = os.path.join(BASE_DIR, "wardrobe", "wardrobe.json")

SLOT_HINTS = {
    "base": "内层：T恤/打底衫/衬衫/背心",
    "mid": "中层：卫衣/毛衣/针织衫/西装马甲/薄羽绒马甲",
    "outer": "外层：外套/大衣/风衣/羽绒服/夹克/冲锋衣",
    "bottom": "下装：长裤/牛仔裤/西裤/短裤/裙子",
    "shoes": "鞋履：运动鞋/皮鞋/靴子/凉鞋",
    "accessory": "配饰：围巾/帽子/手套/腰带/伞/墨镜",
}

CLO_HINTS = {
    "base": "极薄 0.12-0.16 / 薄 0.18-0.22 / 厚 0.24-0.30",
    "mid": "薄 0.22-0.30 / 适中 0.32-0.40 / 厚 0.42-0.55",
    "outer": "薄 0.28-0.34 / 适中 0.36-0.45 / 厚 0.50-0.70 / 极厚 0.85-1.05",
}

FORMALITY_HINTS = (
    "0=居家休闲(运动服/睡衣) 1=日常休闲(T恤/牛仔裤) 2=常规办公(衬衫/休闲外套) "
    "3=商务会面(正装衬衫/西裤/风衣) 4=正式场合(西装/皮鞋/礼服)"
)

PROMPT = """你是一个衣橱管理助手。分析这张服装照片，输出 JSON（不要任何多余文字）：

{
  "name": "中文名称，如「藏青长袖衬衫」",
  "slot": "base|mid|outer|bottom|shoes|accessory",
  "category": "细分品类英文，如 tshirt/shirt/sweater/hoodie/jacket/trench/down_jacket/blazer/coats/jeans/dress_pants/shorts/skirt/shoes_sneakers/shoes_leather/boots/scarf/hat/gloves/belt/umbrella/sunglasses",
  "color": "主色中文：黑/白/灰/深灰/浅灰/藏青/深蓝/浅蓝/米白/米/驼/棕/红/酒红/绿/粉/黄/紫/橙",
  "material": "材质中文：纯棉/棉/羊毛/羊绒/针织/牛仔/皮革/真皮/涤纶/羽绒/亚麻/雪纺/冲锋面料",
  "clo": 0.15,
  "formality": 2,
  "waterproof": false,
  "windproof": false,
  "sun_protective": false,
  "season": ["spring","summer","autumn","winter"]
}

字段说明：
- slot 槽位：{slots}
- clo 保暖值（热阻单位）：{clo_hints}
- formality 正式度：{formality_hints}
- season 适用季节数组，可多选

判断 clo 的参照：纯棉短袖T恤=0.15，长袖衬衫=0.20，薄针织衫=0.25，卫衣=0.38，
厚毛衣=0.45，薄夹克=0.33，风衣=0.40，厚大衣=0.65，羽绒服=0.92，运动鞋=0.16。

只输出 JSON。"""


def list_photos():
    if not os.path.isdir(PHOTO_DIR):
        return []
    exts = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
    return sorted(f for f in os.listdir(PHOTO_DIR)
                  if os.path.splitext(f)[1].lower() in exts)


def existing_ids():
    with open(WARDROBE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    used = set()
    for it in data["items"]:
        p = it.get("photo")
        if p:
            used.add(os.path.basename(p))
    return data, used


def encode_image(path):
    with open(path, "rb") as f:
        b = f.read()
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    return base64.b64encode(b).decode(), mime


def call_vision(image_b64, mime, api_key, model, endpoint):
    """调用 OpenAI 兼容的视觉接口。"""
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT.format(
                    slots=" / ".join(f"{k}={v}" for k, v in SLOT_HINTS.items()),
                    clo_hints=" / ".join(f"{k}:{v}" for k, v in CLO_HINTS.items()),
                    formality_hints=FORMALITY_HINTS)},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime};base64,{image_b64}"}},
            ],
        }],
        "temperature": 0.2,
        "max_tokens": 600,
    }
    req = urllib.request.Request(
        f"{endpoint}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    text = raw["choices"][0]["message"]["content"].strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def next_id(used_ids, category):
    prefix = {"base": "w", "mid": "w", "outer": "w", "bottom": "w",
              "shoes": "w", "accessory": "w"}.get(category, "w")
    n = 1
    while f"{prefix}{n:03d}" in used_ids:
        n += 1
    return f"{prefix}{n:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="只生成待标注清单")
    ap.add_argument("--auto", action="store_true", help="调用视觉模型自动打标")
    ap.add_argument("--api-key", default=os.environ.get("DRESSMATE_API_KEY", ""))
    ap.add_argument("--model", default=os.environ.get("DRESSMATE_VISION_MODEL", "gpt-4o"))
    ap.add_argument("--endpoint", default=os.environ.get("DRESSMATE_API_ENDPOINT",
                                                         "https://api.openai.com/v1"))
    ap.add_argument("--dry-run", action="store_true", help="识别但不写入 wardrobe.json")
    args = ap.parse_args()

    photos = list_photos()
    if not photos:
        print(f"照片目录为空：{PHOTO_DIR}")
        print("把衣服照片放进去（建议文件名直接用描述，如 藏青长袖衬衫.jpg），再运行本脚本。")
        return

    data, used = existing_ids()
    todo = [p for p in photos if p not in used]
    print(f"照片目录共 {len(photos)} 张，已入库 {len(used)} 张，待处理 {len(todo)} 张")
    for p in todo:
        print(f"  - {p}")

    if args.plan or not args.auto:
        print("\n待标注清单已生成。设置环境变量后运行 --auto 自动识别：")
        print("  set DRESSMATE_API_KEY=sk-...")
        print("  set DRESSMATE_VISION_MODEL=gpt-4o")
        print("  python tools/label_photos.py --auto")
        return

    if not args.api_key:
        print("错误：缺少 --api-key 或环境变量 DRESSMATE_API_KEY")
        return

    added = []
    for i, name in enumerate(todo, 1):
        path = os.path.join(PHOTO_DIR, name)
        print(f"[{i}/{len(todo)}] 识别 {name} …", end=" ", flush=True)
        try:
            b64, mime = encode_image(path)
            tags = call_vision(b64, mime, args.api_key, args.model, args.endpoint)
        except Exception as exc:
            print(f"失败：{exc}")
            continue

        tags.setdefault("slot", "base")
        tags.setdefault("category", "unknown")
        tags.setdefault("color", "黑")
        tags.setdefault("material", "")
        tags.setdefault("clo", 0.2)
        tags.setdefault("formality", 2)
        tags.setdefault("season", ["spring", "summer", "autumn", "winter"])
        item = {
            "id": next_id(set(it["id"] for it in data["items"]), tags["slot"]),
            "name": tags.get("name", os.path.splitext(name)[0]),
            "photo": f"photos/{name}",
            "slot": tags["slot"],
            "category": tags["category"],
            "color": tags["color"],
            "material": tags["material"],
            "clo": float(tags["clo"]),
            "formality": int(tags["formality"]),
            "waterproof": bool(tags.get("waterproof", False)),
            "windproof": bool(tags.get("windproof", False)),
            "sun_protective": bool(tags.get("sun_protective", False)),
            "season": tags["season"],
            "status": "clean",
            "last_worn": None,
            "wear_count": 0,
        }
        data["items"].append(item)
        added.append(item)
        print(f"→ {item['slot']}/{item['name']} (clo={item['clo']}, formal={item['formality']})")

    if added and not args.dry_run:
        with open(WARDROBE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n已写入 {len(added)} 件新单品到 wardrobe/wardrobe.json")
    elif added:
        print(f"\n[dry-run] 识别到 {len(added)} 件，未写入")


if __name__ == "__main__":
    main()
