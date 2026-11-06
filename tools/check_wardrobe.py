# -*- coding: utf-8 -*-
"""衣橱体检：导入照片后跑一遍，找出会导致推荐出问题的单品。

    python tools/check_wardrobe.py
    python tools/check_wardrobe.py --strict   # 有 ERROR 时退出码非 0
"""
import argparse
import json
import os
import sys
from collections import Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WARDROBE_PATH = os.path.join(BASE_DIR, "wardrobe", "wardrobe.json")
PHOTO_DIR = os.path.join(BASE_DIR, "wardrobe", "photos")

REQUIRED = ["id", "name", "slot", "category", "color", "clo", "formality"]
SLOTS = {"base", "mid", "outer", "bottom", "shoes", "accessory"}
STATUS = {"clean", "dirty", "laundry", "dryclean", "stored"}
SEASONS = {"spring", "summer", "autumn", "winter"}

# 各槽位 clo 的合理范围，超出就是明显填错
CLO_RANGE = {
    "base": (0.08, 0.40), "mid": (0.15, 0.70), "outer": (0.15, 1.30),
    "bottom": (0.08, 0.60), "shoes": (0.05, 0.40), "accessory": (0.0, 0.30),
}
# 正式度与品类的粗略一致性检查
FORMAL_HINT = [
    (["blazer", "dress_pants", "shoes_leather"], 3, "正装类单品正式度偏低"),
    (["sport_tee", "running_shoes", "gym_pants", "leggings", "track_jacket"], 1, "运动类单品正式度偏高"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--path", default=WARDROBE_PATH)
    args = ap.parse_args()

    with open(args.path, encoding="utf-8") as f:
        data = json.load(f)
    items = data["items"]

    errors, warns, infos = [], [], []
    missing_photos = []
    seen_ids = set()

    for it in items:
        tag = f"{it.get('id', '?')} {it.get('name', '?')}"
        for k in REQUIRED:
            if k not in it or it[k] in (None, ""):
                errors.append(f"{tag}: 缺少必填字段 {k}")
        i = it.get("id")
        if i in seen_ids:
            errors.append(f"{tag}: id 重复")
        seen_ids.add(i)

        slot = it.get("slot")
        if slot not in SLOTS:
            errors.append(f"{tag}: slot={slot} 非法（应为 {sorted(SLOTS)}）")
            continue

        clo = it.get("clo")
        if not isinstance(clo, (int, float)):
            errors.append(f"{tag}: clo 不是数字")
        else:
            lo, hi = CLO_RANGE[slot]
            if not (lo <= clo <= hi):
                errors.append(f"{tag}: clo={clo} 超出 {slot} 合理范围 [{lo}, {hi}]")

        fml = it.get("formality")
        if not isinstance(fml, int) or not (0 <= fml <= 4):
            errors.append(f"{tag}: formality={fml} 应为 0-4 的整数")

        if it.get("status", "clean") not in STATUS:
            errors.append(f"{tag}: status={it.get('status')} 非法")

        for s in it.get("season", []):
            if s not in SEASONS:
                warns.append(f"{tag}: season={s} 非法")

        for cats, bound, msg in FORMAL_HINT:
            if it.get("category") in cats and isinstance(fml, int):
                if cats[0] in ("blazer", "dress_pants", "shoes_leather") and fml < bound:
                    warns.append(f"{tag}: {msg}（当前 {fml}，建议 ≥{bound}）")
                if cats[0] == "sport_tee" and fml > bound:
                    warns.append(f"{tag}: {msg}（当前 {fml}，建议 ≤{bound}）")

        photo = it.get("photo")
        if not photo:
            warns.append(f"{tag}: 没有照片，Web 端会显示占位块")
        elif not os.path.exists(os.path.join(PHOTO_DIR, os.path.basename(photo))):
            missing_photos.append(f"{tag}: {photo}")

        if it.get("needs_review"):
            infos.append(f"{tag}: 待人工校对（clo={clo}, 正式度={fml}）")

    # 槽位覆盖
    by_slot = Counter(it.get("slot") for it in items)
    clean_by_slot = Counter(it.get("slot") for it in items if it.get("status", "clean") == "clean")
    for s in ("base", "outer", "bottom", "shoes"):
        if clean_by_slot[s] == 0:
            errors.append(f"槽位 {s} 没有任何可穿单品 → 推荐引擎会返回空结果")
        elif clean_by_slot[s] < 2:
            warns.append(f"槽位 {s} 只有 {clean_by_slot[s]} 件可穿，备选方案会很少")
    if clean_by_slot["outer"] < 3:
        warns.append("外层可穿单品少于 3 件，冷天/雨天可能无法给出合适组合")

    # 保暖覆盖：外层有没有厚衣服
    outer_clos = sorted(it.get("clo", 0) for it in items
                        if it.get("slot") == "outer" and it.get("status", "clean") == "clean")
    if outer_clos and max(outer_clos) < 0.60:
        warns.append(f"最厚外层只有 {max(outer_clos):.2f} clo，0℃ 以下会有保暖硬约束失败")

    # 大量缺图时汇总，避免几十条同质量警告淹没真正的问题
    if len(missing_photos) >= 5:
        warns.append(f"共 {len(missing_photos)} 件引用了不存在的照片文件"
                     f"（示例衣橱未附图片时属正常），前 3 条："
                     + "；".join(missing_photos[:3]))
    else:
        warns.extend(missing_photos)

    print("=" * 60)
    print(f"衣橱体检：{len(items)} 件单品")
    print("=" * 60)
    print("槽位分布（可穿/总数）：")
    for s in ("base", "mid", "outer", "bottom", "shoes", "accessory"):
        print(f"  {s:<10} {clean_by_slot[s]:>3} / {by_slot[s]:<3}")

    print(f"\nERROR  {len(errors)}")
    for e in errors:
        print("  ✗ " + e)
    print(f"\nWARN   {len(warns)}")
    for w in warns[:20]:
        print("  ! " + w)
    if len(warns) > 20:
        print(f"  … 另有 {len(warns) - 20} 条")
    if infos:
        print(f"\n待校对  {len(infos)}")
        for i in infos[:10]:
            print("  · " + i)
        if len(infos) > 10:
            print(f"  … 另有 {len(infos) - 10} 条")

    if not errors and not warns:
        print("\n全部通过，衣橱数据健康。")
    print("=" * 60)
    if args.strict and errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
