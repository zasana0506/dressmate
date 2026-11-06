# -*- coding: utf-8 -*-
"""穿着反馈：记录今天实际穿了什么，回写 last_worn / wear_count。

这是让推荐越用越准的关键闭环：
  1. 用户在 App 里点「今天就穿这套」
  2. 本脚本更新 wardrobe.json 的 last_worn 与 wear_count
  3. 引擎的轮换分（freshness）随之变化，避免天天推同一套

用法：
    python tools/feedback.py --wear w001,w102,w204      # 记录实际穿着
    python tools/feedback.py --clean w001,w105           # 标记为待洗
    python tools/feedback.py --clean-all                # 全部标脏
    python tools/feedback.py --stats                    # 查看统计
"""
import argparse
import datetime
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WARDROBE_PATH = os.path.join(BASE_DIR, "wardrobe", "wardrobe.json")
LOG_PATH = os.path.join(BASE_DIR, "data", "wear_log.json")


def load():
    with open(WARDROBE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(data):
    with open(WARDROBE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_log():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_log(log):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wear", help="逗号分隔的单品ID，记录今天穿了这些")
    ap.add_argument("--clean", help="逗号分隔的单品ID，标记为待洗")
    ap.add_argument("--clean-all", action="store_true", help="把所有 clean 之外的保持不变，仅列出状态")
    ap.add_argument("--stats", action="store_true", help="输出穿着统计")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args()

    data = load()
    items = {it["id"]: it for it in data["items"]}

    if args.wear:
        ids = [x.strip() for x in args.wear.split(",") if x.strip()]
        today = args.date
        for i in ids:
            if i not in items:
                print(f"  ! 未知单品ID: {i}")
                continue
            it = items[i]
            it["last_worn"] = today
            it["wear_count"] = it.get("wear_count", 0) + 1
            if it.get("status") != "clean":
                it["status"] = "clean"
            print(f"  ✓ {it['name']} → 已记录 {today}")
        log = load_log()
        log.append({"date": today, "items": ids})
        save_log(log)
        save(data)
        print(f"已写入 {len(ids)} 件单品的穿着记录")
        return

    if args.clean:
        ids = [x.strip() for x in args.clean.split(",") if x.strip()]
        for i in ids:
            if i not in items:
                print(f"  ! 未知单品ID: {i}")
                continue
            items[i]["status"] = "dirty"
            print(f"  ✓ {items[i]['name']} → 待洗")
        save(data)
        return

    if args.stats:
        log = load_log()
        print(f"累计穿着记录 {len(log)} 天\n")
        by_count = sorted(items.values(), key=lambda x: -x.get("wear_count", 0))
        print("高频单品 TOP10：")
        for it in by_count[:10]:
            print(f"  {it.get('wear_count',0):>3} 次  {it['name']}  (最近 {it.get('last_worn') or '—'})")
        print("\n久未穿（>30天）：")
        old = [x for x in by_count if x.get("last_worn") and
               (datetime.date.today() - datetime.date.fromisoformat(x["last_worn"])).days > 30]
        for it in old[:8]:
            print(f"  {it['name']}  (最后 {it['last_worn']})")
        if not old:
            print("  无")
        return

    # 默认：列出当前状态
    from collections import Counter
    c = Counter(it.get("status", "clean") for it in data["items"])
    print("衣橱状态统计：")
    for k, v in c.items():
        print(f"  {k}: {v} 件")
    print("\n当前不可穿：")
    for it in data["items"]:
        if it.get("status", "clean") != "clean":
            print(f"  {it['name']}  [{it['status']}]")


if __name__ == "__main__":
    main()
