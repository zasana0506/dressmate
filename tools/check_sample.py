# -*- coding: utf-8 -*-
"""校验公开样例衣橱的数据没写错。

为什么要单独一个脚本而不是塞在 CI 的 YAML 里：
YAML 会先处理引号，python -c "..." 这种写法里的转义会被吃掉一层，
在 GitHub Actions 上表现为「本地能过、CI 必挂」。
把逻辑放进文件，CI 只管调用，就没有转义问题了。

用法：
    python tools/check_sample.py
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(BASE_DIR, "samples", "wardrobe.json")

# 每层至少要有几件，否则推荐池太窄，出不了有差异的三套
MIN_PER_SLOT = {
    "base": 2,
    "mid": 2,
    "outer": 2,
    "bottom": 2,
    "shoes": 2,
}
# 这些层可有可无，但有的话更好
OPTIONAL_SLOTS = ("accessory",)

VALID_CATEGORIES = {
    "tshirt", "shirt", "thermal", "sport_tshirt", "hoodie", "cardigan",
    "sweater", "vest", "fleece", "down_jacket", "blazer", "trench", "coat",
    "jacket", "leather_jacket", "jeans", "dress_pants", "chinos",
    "sport_pants", "shorts", "sneakers", "dress_shoes", "boots",
    "running_shoes", "hat", "scarf", "gloves",
}


def main():
    if not os.path.exists(SAMPLE):
        print(f"失败：找不到 {SAMPLE}")
        return 1

    with open(SAMPLE, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items") or []
    if not items:
        print("失败：样例衣橱是空的")
        return 1

    errors = []

    # --- 层位覆盖 ---
    by_slot = {}
    for it in items:
        by_slot.setdefault(it.get("slot"), []).append(it)
    for slot, need in MIN_PER_SLOT.items():
        got = len(by_slot.get(slot, []))
        if got < need:
            errors.append(f"层位 {slot} 只有 {got} 件，至少要 {need} 件")

    # --- 单件字段 ---
    seen_ids = set()
    for it in items:
        name = it.get("name") or "(无名)"
        iid = it.get("id")
        if not iid:
            errors.append(f"{name}：缺 id")
        elif iid in seen_ids:
            errors.append(f"{name}：id 重复（{iid}）")
        else:
            seen_ids.add(iid)

        if not it.get("name"):
            errors.append(f"{iid}：缺 name")
        if it.get("category") not in VALID_CATEGORIES:
            errors.append(f"{name}：品类 {it.get('category')!r} 不在已知列表里")
        if not it.get("color"):
            errors.append(f"{name}：缺 color")
        if not it.get("material"):
            errors.append(f"{name}：缺 material")

        clo = it.get("clo")
        if not isinstance(clo, (int, float)) or not (0 <= clo <= 2):
            errors.append(f"{name}：clo={clo!r} 越界（应为 0~2）")

        formal = it.get("formality")
        if not isinstance(formal, int) or not (0 <= formal <= 4):
            errors.append(f"{name}：formality={formal!r} 越界（应为 0~4 的整数）")

        seasons = it.get("season")
        if not seasons or not all(s in ("spring", "summer", "autumn", "winter")
                                  for s in seasons):
            errors.append(f"{name}：season 取值有问题（{seasons!r}）")

        # 照片可以留空（前端会显示占位块），但不能指向不存在的文件
        photo = it.get("photo") or ""
        if photo:
            fp = os.path.join(BASE_DIR, "wardrobe", photo)
            if not os.path.exists(fp):
                errors.append(f"{name}：photo 指向不存在的文件 {photo}")

    # --- 保暖值与正式度要符合常识 ---
    for it in items:
        if it.get("category") == "down_jacket" and it.get("clo", 0) < 0.6:
            errors.append(f"{it.get('name')}：羽绒服保暖值 {it.get('clo')} 偏低")
        if it.get("category") == "dress_shoes" and it.get("formality", 0) < 3:
            errors.append(f"{it.get('name')}：正装鞋正式度 {it.get('formality')} 偏低")

    print(f"样例衣橱：{len(items)} 件")
    print("  覆盖：" + " ".join(
        f"{k}:{len(v)}" for k, v in sorted(by_slot.items())))
    missing_opt = [s for s in OPTIONAL_SLOTS if s not in by_slot]
    if missing_opt:
        print("  提示：可选层位没有：" + " ".join(missing_opt))

    if errors:
        print(f"\n发现 {len(errors)} 个问题：")
        for e in errors:
            print("  - " + e)
        return 1

    print("  OK 数据校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
