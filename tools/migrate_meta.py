# -*- coding: utf-8 -*-
"""给衣橱补两个字段：gender（性别）和 layer_role（配件角色）。

为什么需要
----------
「皮带与皮鞋同色」「深色西装不配白袜」「领带尖落在皮带扣」「裙摆到膝」
这几条礼仪铁律以前判不了，不是规则难写，是衣橱里没有可以挂靠的字段：
一件单品只有 slot/category/color，系统不知道它是皮带还是裤子，
也不知道它是男款还是女款。

补完之后：
- `layer_role` 让皮带/袜/包/领带/丝袜能被认出来，
  从而走 engine/extras.py 的「按主体反推 + 同色校验」；
- `gender` 让女装铁律（裙长、腰线、透光度）能只对女装生效。

推断原则
--------
宁可留空，不要猜错。批量导入的品名是电商全称，
「秋季休闲劳保裤潮流系腰带西裤」里写着腰带，它是裤子；
「男鞋透气网面飞织袜子板鞋」里写着袜子，它是鞋。
所以只在「槽位/品类本身可能是这件东西」时才按品名认角色。

用法
----
    python tools/migrate_meta.py            # 只看统计，不写盘
    python tools/migrate_meta.py --write    # 写回 wardrobe.json
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import extras as EXTRAS  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE, "wardrobe", "wardrobe.json")

# 裙长：只有女装下装才填，男装裤子没有这一维度
LENGTH_WORDS = (
    ("mini", ("迷你", "超短", "短裙")),
    ("knee", ("及膝", "过膝", "中裙")),
    ("midi", ("中长", "中长裙", "小腿")),
    ("maxi", ("长裙", "拖地", "脚踝")),
)

# 先认男装再认女装：男装商品名里「修身」「显瘦」用得极多，
# 把这类模糊词放前面会把 59 件男士修身衬衫判成女装。
# 「修身」已经剔掉，只留明确的性别词。
WOMEN_WORDS = ("女士", "女装", "女式", "女款", "女鞋", "裙", "高跟", "女包")
MEN_WORDS = ("男士", "男装", "男式", "男款", "男鞋", "爸爸装", "商务男", "男")


def guess_gender(item):
    """显式字段优先；否则看品名里的性别词，最后看品类。"""
    if item.get("gender") in ("men", "women", "neutral"):
        return None  # 已有的不动
    cat = item.get("category") or ""
    if cat in EXTRAS.WOMEN_CATS:
        return "women"
    text = " ".join(str(item.get(k) or "") for k in ("name", "photo"))
    # 「男女同款」这类情侣装归中性，别硬塞一边
    if any(w in text for w in ("男女", "情侣", "中性")):
        return "neutral"
    if any(w in text for w in MEN_WORDS):
        return "men"
    if any(w in text for w in WOMEN_WORDS):
        return "women"
    return "neutral"


def guess_length(item):
    if item.get("length"):
        return None
    cat = item.get("category") or ""
    if cat not in ("skirt", "dress"):
        return None
    text = " ".join(str(item.get(k) or "") for k in ("name", "photo"))
    for tag, words in LENGTH_WORDS:
        if any(w in text for w in words):
            return tag
    return None


def main():
    write = "--write" in sys.argv
    data = json.load(open(PATH, encoding="utf-8"))
    items = data["items"]

    roles, genders, lengths = Counter(), Counter(), Counter()
    changed = 0
    for it in items:
        touched = False
        g = guess_gender(it)
        if g:
            it["gender"] = g
            genders[g] += 1
            touched = True
        r = EXTRAS.role_of(it)
        if r and it.get("layer_role") != r:
            it["layer_role"] = r
            roles[r] += 1
            touched = True
        ln = guess_length(it)
        if ln:
            it["length"] = ln
            lengths[ln] += 1
            touched = True
        changed += touched

    print(f"共 {len(items)} 件，本次补字段 {changed} 件")
    print("  gender   ", dict(genders) or "无新增")
    print("  layer_role", dict(roles) or "无新增")
    print("  length   ", dict(lengths) or "无新增")

    # 现状统计：这些是「配件收口」能用到多少真数据
    bucket = EXTRAS.index(items)
    print("  现有配件：", {EXTRAS.ROLE_NAME[k]: len(v) for k, v in bucket.items()})
    print("  配件规矩：", EXTRAS.lane(items))

    if write:
        json.dump(data, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("已写回", PATH)
    else:
        print("（未写盘，加 --write 生效）")


if __name__ == "__main__":
    main()
