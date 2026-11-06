# -*- coding: utf-8 -*-
"""无 API key 的照片批量导入：从中文文件名推断单品属性，写入衣橱。

文件名怎么写最准：
    藏青长袖衬衫.jpg            → 内层/衬衫/藏青/clo 0.20/正式度3
    黑色厚羽绒服.jpg             → 外层/羽绒服/黑/clo 1.20/防水防风
    米白薄针织衫.jpg             → 中层/针织衫/米白/clo 0.18
    灰色加绒运动长裤.jpg         → 下装/运动裤/灰/clo 0.42/运动属性

用法：
    python tools/import_photos.py                  # 预览推断结果（不写入）
    python tools/import_photos.py --commit         # 写入 wardrobe.json
    python tools/import_photos.py --export-csv     # 导出 CSV 供人工校对
    python tools/import_photos.py --from-csv 校对.csv --commit   # 按校对结果导入

关键：推断结果全部标记 needs_review=true，请抽查 clo 与 formality，
这两个字段直接决定推荐质量。校对后可运行 tools/check_wardrobe.py 体检。
"""
import argparse
import csv
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(BASE_DIR, "wardrobe", "photos")
WARDROBE_PATH = os.path.join(BASE_DIR, "wardrobe", "wardrobe.json")
CSV_PATH = os.path.join(BASE_DIR, "wardrobe", "review.csv")

# 品类关键词 → (槽位, 细分品类, 基准clo, 正式度, 默认材质, 季节)
# 顺序重要：长词放前面，避免"衬衫"抢先匹配掉"防晒衬衫"
CATEGORY_RULES = [
    (["保暖内衣", "秋衣", "打底衫", "保暖打底"], "base", "thermal_undershirt", 0.26, 0, "棉", "冬"),
    (["速干T", "运动T", "速干短袖"], "base", "sport_tee", 0.14, 0, "涤纶速干", "全年"),
    (["防晒衬衫", "防晒衣", "防晒服"], "outer", "sun_shirt", 0.22, 1, "锦纶", "夏"),
    (["长袖衬衫", "牛津纺衬衫", "衬衣"], "base", "shirt", 0.20, 3, "棉", "春秋"),
    (["短袖衬衫"], "base", "shirt", 0.16, 3, "棉", "夏"),
    (["衬衫"], "base", "shirt", 0.20, 3, "棉", "春秋"),
    (["T恤", "t恤", "短袖", "半袖", "背心"], "base", "tshirt", 0.15, 1, "纯棉", "夏"),
    (["polo", "POLO"], "base", "polo", 0.16, 2, "棉", "夏"),

    (["薄羽绒马甲", "羽绒马甲", "马甲"], "mid", "vest_down", 0.46, 2, "羽绒", "冬"),
    (["羊绒开衫", "羊毛开衫", "针织开衫", "开衫"], "mid", "cardigan", 0.38, 2, "羊绒", "春秋"),
    (["薄针织", "薄毛衣"], "mid", "sweater", 0.24, 2, "棉", "春秋"),
    (["厚毛衣", "粗针毛衣"], "mid", "sweater", 0.50, 2, "羊毛", "冬"),
    (["羊绒衫", "毛衣", "针织衫", "毛衫"], "mid", "sweater", 0.42, 2, "羊毛", "冬"),
    (["卫衣", "帽衫"], "mid", "hoodie", 0.38, 1, "棉混纺", "春秋"),
    (["抓绒"], "mid", "fleece", 0.40, 1, "抓绒", "冬"),

    (["羽绒服", "羽绒衣"], "outer", "down_jacket", 0.92, 2, "羽绒", "冬"),
    (["冲锋衣", "硬壳"], "outer", "hardshell", 0.48, 2, "防水面料", "春秋"),
    (["西装外套", "西服", "西装", "blazer"], "outer", "blazer", 0.32, 4, "羊毛混纺", "春秋"),
    (["风衣", " trench"], "outer", "trench", 0.40, 3, "涤纶混纺", "春秋"),
    (["皮夹克", "皮衣"], "outer", "leather_jacket", 0.35, 2, "真皮", "春秋"),
    (["大衣", "呢子", "毛呢外套"], "outer", "coat", 0.65, 3, "羊毛", "冬"),
    (["运动外套", "抓绒外套"], "outer", "track_jacket", 0.40, 0, "抓绒", "春秋"),
    (["夹克", "外套"], "outer", "jacket", 0.35, 2, "棉混纺", "春秋"),

    (["加绒裤", "加厚裤"], "bottom", "fleece_pants", 0.42, 1, "加绒", "冬"),
    (["速干裤", "运动长裤", "运动裤"], "bottom", "gym_pants", 0.18, 0, "涤纶", "全年"),
    (["紧身裤", "leggings"], "bottom", "leggings", 0.16, 0, "锦纶氨纶", "全年"),
    (["西裤", "正装裤"], "bottom", "dress_pants", 0.26, 4, "羊毛混纺", "春秋"),
    (["牛仔裤"], "bottom", "jeans", 0.24, 1, "牛仔", "春秋"),
    (["工装裤", "休闲裤", "chinos"], "bottom", "chinos", 0.25, 1, "棉", "春秋"),
    (["短裤"], "bottom", "shorts", 0.12, 1, "棉", "夏"),
    (["半裙", "裙子", "长裙"], "bottom", "skirt", 0.22, 2, "混纺", "春秋"),
    (["阔腿裤", "长裤", "裤子"], "bottom", "trousers", 0.25, 2, "棉", "春秋"),

    (["跑步鞋", "跑鞋", "运动鞋"], "shoes", "running_shoes", 0.15, 0, "网布", "全年"),
    (["小白鞋", "板鞋", "帆布鞋"], "shoes", "shoes_sneakers", 0.16, 2, "皮革", "春秋"),
    (["皮鞋", "德比鞋", "牛津鞋", "乐福鞋"], "shoes", "shoes_leather", 0.18, 4, "牛皮", "春秋"),
    (["切尔西靴", "马丁靴", "短靴", "靴"], "shoes", "boots", 0.26, 3, "牛皮", "冬"),
    (["凉鞋", "拖鞋"], "shoes", "sandals", 0.10, 1, "皮革", "夏"),

    (["折叠伞", "雨伞", "伞"], "accessory", "umbrella", 0.0, 1, "涤纶", "全年"),
    (["太阳镜", "墨镜"], "accessory", "sunglasses", 0.0, 2, "树脂", "夏"),
    (["围巾"], "accessory", "scarf", 0.18, 2, "羊毛", "冬"),
    (["毛线帽", "帽子", "针织帽"], "accessory", "hat", 0.12, 0, "羊毛", "冬"),
    (["手套"], "accessory", "gloves", 0.12, 0, "羊毛", "冬"),
    (["皮带", "腰带"], "accessory", "belt", 0.0, 3, "牛皮", "全年"),
]

COLORS = ["藏青", "深蓝", "浅蓝", "米白", "深灰", "浅灰", "墨绿", "酒红",
          "卡其", "燕麦", "驼", "黑", "白", "灰", "棕", "红", "蓝", "绿",
          "粉", "黄", "紫", "橙", "米"]
MATERIALS = ["纯棉", "羊毛混纺", "羊绒", "羊毛", "亚麻", "真皮", "牛皮",
             "锦纶氨纶", "涤纶速干", "涤纶", "牛仔", "羽绒", "加绒", "抓绒", "棉"]

THICK_WORDS = ["加厚", "加绒", "厚款", "厚", "极厚", "重磅"]
THIN_WORDS = ["超薄", "极薄", "轻薄", "薄款", "薄", "夏季"]
SPORT_WORDS = ["运动", "速干", "健身", "跑步", "瑜伽", "训练"]
FORMAL_WORDS = ["正装", "商务", "西装", "礼服"]
CASUAL_WORDS = ["居家", "休闲", "睡衣"]

SEASON_MAP = {
    "夏": ["summer"], "冬": ["winter"], "春秋": ["spring", "autumn"],
    "全年": ["spring", "summer", "autumn", "winter"],
}
WATERPROOF_CATS = {"hardshell", "down_jacket", "trench", "leather_jacket", "umbrella"}
WINDPROOF_CATS = {"hardshell", "down_jacket", "trench", "leather_jacket",
                  "track_jacket", "scarf", "hat", "umbrella"}
SUN_CATS = {"sun_shirt", "sunglasses", "hat"}


def list_photos():
    if not os.path.isdir(PHOTO_DIR):
        return []
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    return sorted(f for f in os.listdir(PHOTO_DIR)
                  if os.path.splitext(f)[1].lower() in exts)


def infer(filename):
    """从文件名推断单品属性，返回 (item_dict, confidence, warnings)。"""
    stem = os.path.splitext(filename)[0]
    # 去掉常见的相机前缀与序号
    stem = re.sub(r"^(IMG|DSC|PHOTO|微信图片|mmexport)[_\-]?\d*[_]?", "", stem, flags=re.I)
    stem = re.sub(r"[_\-]+", "", stem).strip()
    warnings = []

    slot = category = material = None
    clo, formality, season_key = 0.20, 2, "春秋"
    matched_kw = ""
    for kws, s, cat, base_clo, base_formal, mat, season in CATEGORY_RULES:
        hit = next((k for k in kws if k.lower() in stem.lower()), None)
        if hit:
            slot, category, clo, formality, material, season_key = (
                s, cat, base_clo, base_formal, mat, season)
            matched_kw = hit
            break
    if slot is None:
        slot, category, material = "base", "unknown", ""
        warnings.append("未能从文件名识别品类，需手动指定 slot/category/clo")

    color = next((c for c in COLORS if c in stem), None)
    if color is None:
        color = "黑"
        warnings.append("未能识别颜色，默认黑")

    for m in MATERIALS:
        if m in stem:
            material = m
            break

    # 厚度修饰：若品类关键词本身已含"厚/薄"（如"厚毛衣""薄针织"），
    # 基准 clo 已经体现了，不能重复乘系数。
    already_scaled = any(w in matched_kw for w in ("厚", "薄", "加绒", "轻"))
    if not already_scaled:
        if any(w in stem for w in THICK_WORDS):
            clo = round(clo * 1.30, 2)
        elif any(w in stem for w in THIN_WORDS):
            clo = round(clo * 0.75, 2)

    # 场合修饰
    if any(w in stem for w in SPORT_WORDS):
        formality = 0
        sport = True
    else:
        sport = category in {"sport_tee", "gym_pants", "leggings", "running_shoes",
                             "track_jacket", "sports_bra"}
    if any(w in stem for w in FORMAL_WORDS):
        formality = max(formality, 3)
    if any(w in stem for w in CASUAL_WORDS):
        formality = min(formality, 1)

    waterproof = category in WATERPROOF_CATS or "防水" in stem
    windproof = category in WINDPROOF_CATS or "防风" in stem
    sun_protective = category in SUN_CATS or "防晒" in stem

    name = stem or os.path.splitext(filename)[0]
    item = {
        "name": name,
        "photo": f"photos/{filename}",
        "slot": slot,
        "category": category,
        "color": color,
        "material": material,
        "clo": clo,
        "formality": formality,
        "waterproof": waterproof,
        "windproof": windproof,
        "sun_protective": sun_protective,
        "sport": sport,
        "season": SEASON_MAP[season_key],
        "status": "clean",
        "last_worn": None,
        "wear_count": 0,
        "needs_review": True,
    }
    confidence = "低" if not slot or category == "unknown" else ("中" if warnings else "高")
    return item, confidence, warnings


def load_wardrobe():
    with open(WARDROBE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_wardrobe(data):
    with open(WARDROBE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def free_id(data):
    used = {it["id"] for it in data["items"]}
    n = 900
    while f"w{n}" in used:
        n += 1
    return f"w{n}"


def merge(data, new_items):
    existing = {os.path.basename(it.get("photo", "")) for it in data["items"]}
    added = 0
    for it in new_items:
        if os.path.basename(it.get("photo", "")) in existing:
            continue
        it["id"] = free_id(data)
        data["items"].append(it)
        existing.add(os.path.basename(it["photo"]))
        added += 1
    return added


CSV_FIELDS = ["photo", "name", "slot", "category", "color", "material", "clo",
              "formality", "waterproof", "windproof", "sun_protective", "sport",
              "season", "status"]


def export_csv(items):
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        wr.writeheader()
        for it in items:
            row = {k: it.get(k, "") for k in CSV_FIELDS}
            row["season"] = "|".join(it.get("season", []))
            for k in ("waterproof", "windproof", "sun_protective", "sport"):
                row[k] = "1" if it.get(k) else "0"
            wr.writerow(row)
    print(f"已导出校对表：{CSV_PATH}")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("CSV 为空或格式不对（需 UTF-8、含表头）。"
                         "若用 Excel 编辑，请另存为「CSV UTF-8」并确保已保存。")
    out = []
    for r in rows:
        it = {k: r.get(k, "") for k in CSV_FIELDS}
        it["clo"] = float(r.get("clo") or 0.2)
        it["formality"] = int(r.get("formality") or 2)
        for k in ("waterproof", "windproof", "sun_protective", "sport"):
            it[k] = str(r.get(k, "")).strip() in ("1", "true", "True", "是")
        it["season"] = [s for s in r.get("season", "").split("|") if s]
        it["status"] = r.get("status") or "clean"
        it["last_worn"] = None
        it["wear_count"] = 0
        it["needs_review"] = False   # 人工校对过，取消标记
        out.append(it)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="真正写入 wardrobe.json")
    ap.add_argument("--export-csv", action="store_true", help="导出 CSV 供人工校对")
    ap.add_argument("--from-csv", default="", help="从校对后的 CSV 导入")
    ap.add_argument("--force", action="store_true", help="CSV 导入时允许覆盖同名条目")
    args = ap.parse_args()

    if args.from_csv:
        path = args.from_csv if os.path.isabs(args.from_csv) else os.path.join(BASE_DIR, args.from_csv)
        if not os.path.exists(path):
            print(f"找不到 CSV：{path}")
            return
        try:
            items = read_csv(path)
        except ValueError as exc:
            print(f"错误：{exc}")
            return
        print(f"从 CSV 读取 {len(items)} 件单品")
        if args.force:
            data = load_wardrobe()
            names = {os.path.basename(it["photo"]) for it in items}
            data["items"] = [it for it in data["items"]
                             if os.path.basename(it.get("photo", "")) not in names]
            for it in items:
                it["id"] = free_id(data)
                data["items"].append(it)
            save_wardrobe(data)
            print(f"已覆盖导入 {len(items)} 件")
        elif args.commit:
            data = load_wardrobe()
            n = merge(data, items)
            save_wardrobe(data)
            print(f"已导入 {n} 件（跳过 {len(items) - n} 件已存在的）")
        else:
            print("预览模式。加 --commit 写入；若想覆盖已有条目再加 --force")
        return

    photos = list_photos()
    if not photos:
        print(f"照片目录为空：{PHOTO_DIR}")
        print("把衣服照片放进去，文件名写成中文描述，例如：藏青长袖衬衫.jpg")
        return

    data = load_wardrobe()
    known = {os.path.basename(it.get("photo", "")) for it in data["items"]}
    todo = [p for p in photos if p not in known]
    print(f"照片 {len(photos)} 张，已入库 {len(photos) - len(todo)} 张，待导入 {len(todo)} 张\n")

    if not todo:
        print("没有新照片。若要重新导入，先从 wardrobe.json 删除对应条目。")
        return

    inferred = []
    print(f"{'文件名':<30} {'槽位':<7} {'品类':<20} {'色':<5} {'clo':>5} {'正式':>4}  置信")
    print("-" * 92)
    for name in todo:
        item, conf, warns = infer(name)
        inferred.append(item)
        print(f"{name[:29]:<30} {item['slot']:<7} {item['category']:<20} "
              f"{item['color']:<5} {item['clo']:>5.2f} {item['formality']:>4}  {conf}")
        for w in warns:
            print(f"    ! {w}")

    if args.export_csv:
        export_csv(inferred)
        print("\n请用 Excel 打开 review.csv 校对 clo / formality / slot，然后：")
        print("  python tools/import_photos.py --from-csv wardrobe/review.csv --commit")

    if args.commit:
        n = merge(data, inferred)
        save_wardrobe(data)
        print(f"\n已写入 {n} 件新单品（全部标记 needs_review=true，请抽查）")
    else:
        print("\n预览模式，未写入。确认无误后加 --commit；")
        print("或先 --export-csv 用表格校对再 --from-csv --commit。")


if __name__ == "__main__":
    main()
