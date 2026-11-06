# -*- coding: utf-8 -*-
"""推荐引擎：候选筛选 → 束搜索组合 → 打分排序 → 生成逐件理由。

两个关键设计：
1. 正式度是"软偏好 + 分级降级"，不是硬过滤。否则衣橱里没有正装外套时，
   引擎会直接返回空结果——这正是实际使用时最常见的场景。
2. 组合空间用束搜索（beam search）逐层扩展，而非暴力笛卡尔积。
   5 层 × 束宽 200 × 每层 12 候选 ≈ 1.2 万次打分，毫秒级。
"""
import datetime

from . import config as C
from . import styling as STYLE
from . import extras as EXTRAS


# ---------------------------------------------------------------- 工具

def _lerp(knots, t):
    """在 [(x, y), ...] 上线性插值，超出范围取端点。"""
    if t <= knots[0][0]:
        return knots[0][1]
    if t >= knots[-1][0]:
        return knots[-1][1]
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if x0 <= t <= x1:
            return y0 + (y1 - y0) * (t - x0) / (x1 - x0)
    return knots[-1][1]


def band_of(feel):
    """体感温度 → 温度档位 key。"""
    if feel >= 28:
        return "hot"
    if feel >= 22:
        return "warm"
    if feel >= 15:
        return "mild"
    if feel >= 8:
        return "cool"
    return "cold"


def _days_since(date_str, today):
    if not date_str:
        return 999
    try:
        return (today - datetime.date.fromisoformat(date_str)).days
    except Exception:
        return 999


# 保暖匹配度低于这条线，宁可不推荐，也不让人穿错。
# 4 件衣服的衣橱里只剩羽绒服时，15℃ 硬配出来就是「穿多」不是「穿对」。
MIN_FIT = 0.30

# 「三套方案是否真的不同」按这五层比。配饰不算：换条项链不叫换一套衣服。
CORE_SLOTS = ("base", "mid", "outer", "bottom", "shoes")

# 「缺这一层该补什么」的品类措辞。clo 区间按当天体感算，不写死——
# 十二月让人去买 0.2 clo 的衬衫没有意义。
SLOT_WORDS = {
    "base": "长袖T／衬衫／薄打底",
    "mid": "薄针织／卫衣／开衫",
    "outer": "夹克／风衣／薄大衣",
    "bottom": "长裤／牛仔裤",
    "shoes": "运动鞋／乐福鞋／短靴",
}


def slot_words(slot, band):
    """同一层在不同温度下的说法不一样：30℃ 让人补「长袖T」是错的。"""
    if slot == "base":
        if band in ("hot", "warm"):
            return "短袖T／薄衬衫"
        return "保暖内衣／厚打底" if band == "cold" else "长袖T／衬衫／薄打底"
    if slot == "outer":
        return ("夹克／风衣／薄大衣" if band in ("warm", "mild")
                else "厚大衣／羽绒服")
    return SLOT_WORDS.get(slot, "同类单品")


# 正式度不够时该补什么。和保暖值无关，是另一类缺口，不能混着说：
# 「你有卫衣但太薄」和「你有卫衣但不够正式」是完全不同的建议。
FORMAL_WORDS = {
    "base": "正装衬衫／丝光棉衬衫",
    "mid": "西装马甲／精纺开衫",
    "outer": "西装外套／羊绒大衣",
    "bottom": "西裤／直筒长裤",
    "shoes": "皮鞋／乐福鞋",
}


def target_clo(slot, temp):
    """该层在这个温度下的目标保暖值。候选池与「补货建议」共用同一套折线。"""
    knots = {"base": C.BASE_CLO_KNOTS, "mid": C.MID_CLO_KNOTS,
             "outer": C.OUTER_CLO_KNOTS}.get(slot)
    return _lerp(knots, temp) if knots else 0.18


def slot_gaps(pools, ctx, weather, wardrobe=None):
    """逐层说清楚缺什么：是根本没有，还是有但保暖值不对。

    只报「当前温度下真正需要」的层——28℃ 的日子不该催人买大衣。
    返回的 range 是该补单品的 clo 区间，用户照着买就能配上。

    wardrobe 用来区分「一件都没有」和「有但今天穿不了」：
    只看候选池的话，一件 0.92 clo 的羽绒服在 16℃ 会被保暖值过滤掉，
    于是被误报成「衣橱里还没有外层」——用户看着自己的羽绒服会以为出了 bug。
    """
    band = band_of(weather["feel_mean"])
    need = list(C.TEMPERATURE_BANDS[band]["required"]) + ["bottom", "shoes"]
    gaps = []
    for slot in need:
        cands = pools.get(slot) or []
        if any(c["warm_fit"] >= MIN_FIT for c in cands):
            continue
        owned = [it for it in (wardrobe or []) if it.get("slot") == slot]
        temp = (ctx.get("slot_temp") or {}).get(slot, weather["feel_mean"])
        t = round(target_clo(slot, temp), 2)
        lo, hi = round(max(0.05, t * 0.8), 2), round(t * 1.3, 2)
        gap = {"slot": slot, "slot_name": C.SLOT_NAME[slot],
               "target_clo": t, "range": [lo, hi],
               "hint": f"{lo}–{hi} clo 的{slot_words(slot, band)}"}
        if slot == "shoes":
            # 鞋不是按 clo 挑的，按用途挑。写「0.14–0.23 clo 的运动鞋」没人读得懂
            gap["hint"] = "一双正经鞋：运动鞋／乐福鞋／短靴"
        if cands or owned:
            # 有这一类却没有一件用得上：要么保暖值不对，要么正式度撑不住。
            # 这两种必须分开说，否则用户会去买一件厚薄对了、却依然穿不出门的衣服。
            have = [c["item"] for c in sorted(cands, key=lambda c: -c["warm_fit"])] or owned
            names = "、".join(
                f"{it.get('name')}（{float(it.get('clo') or 0):.2f}）" for it in have[:2])
            avg = sum(float(it.get("clo") or 0) for it in have) / len(have)
            req = int(ctx.get("formality") or 2)
            near = [it for it in have if abs(float(it.get("clo") or 0) - t) <= 0.30]
            # 进不了候选池 + 厚薄其实对得上 → 是被正式度筛掉的，不是保暖问题
            if not cands and near and req >= 2:
                top = max(int(it.get("formality") or 0) for it in have)
                gap["reason"] = "formality"
                gap["hint"] = f"{FORMAL_WORDS.get(slot, '同款更正式的一件')}（正式度 ≥{req}）"
                gap["have"] = [it.get("name") for it in have][:3]
                gap["note"] = (f"你有{names}，厚薄对了，但正式度只到"
                               f"「{C.FORMALITY_LABELS.get(top, '休闲')}」，撑不起这个场合")
            else:
                gap["reason"] = "mismatch"
                gap["have"] = [it.get("name") for it in have][:3]
                gap["note"] = (f"你有{names}，这个温度{'太厚' if avg > t else '太薄'}了，"
                               f"该穿 {lo}–{hi} clo 的")
        else:
            gap["reason"] = "empty"
            gap["note"] = f"衣橱里还没有{C.SLOT_NAME[slot]}"
        gaps.append(gap)
    return gaps


def gaps_note(gaps, when="今天"):
    """把缺层清单压成一句话，给 degraded.note 用。when 区分「今天」和「这趟」。"""
    if not gaps:
        return ""
    items = "、".join(f"{g['slot_name']}（{g['hint']}）" for g in gaps)
    return f"{when}还差 {len(gaps)} 层：{items}。补齐这几件就能出整套。"


# ---------------------------------------------------------------- 候选池

def _trim_accessories(cands, per_bucket=2, cap=60):
    """按「类型 + 颜色」分桶取样，别让截断把配饰压成同一件。

    衣服按保暖匹配度取前 12 是对的——同一层保暖差得远就是穿不了。
    但配饰不保暖，warm_fit 几乎恒定，按它排序等于随机排序：
    五百件首饰截断后只剩十几条同名的手链，于是每天都挑同一条。
    改成每个（类型, 颜色）桶最多留 2 件，候选里才有真正的选择。
    """
    buckets, order = {}, []
    for c in cands:
        it = c["item"]
        if it.get("category") == "jewelry":
            key = ("jewelry", jewelry_type(it),
                   C.normalize_color(it.get("color") or ""))
        else:
            # 帽子也按名字分桶：148 顶里遮阳帽、防寒帽、棒球帽是不同的东西，
            # 只按 category 分桶会被压成两件
            key = (it.get("category"), it.get("name") or "", "")
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        if len(buckets[key]) < per_bucket:
            buckets[key].append(c)
    return [c for k in order for c in buckets[k]][:cap]


def _item_text(item):
    """把可能写着商品名/原始文件名的字段拼起来，用于品类与属性的词面判断。"""
    return " ".join(str(item.get(k) or "") for k in C.NAME_FIELDS)


def _is_workwear(item):
    """劳保/警示类：荧光高可视、反光条、防护服。

    只看 name 会漏——人工命名把「高可视警示网眼马甲」简化成了「绿马甲2」，
    原始商品名还留在图片文件名里。
    """
    text = _item_text(item)
    return any(w in text for w in C.WORKWEAR_WORDS)


def _banned_for_dress(item, slot, need_formal):
    """品类禁区：不看分值，看这东西该不该出现在这个正式度上。

    羽绒马甲的正式度标 2、羊绒衫也标 2，但一件套在衬衫外是邋遢，
    一件套在衬衫外是层次。分值分不出这个差别，品类能。
    """
    if need_formal >= 1 and _is_workwear(item):
        return True
    ban = C.CATEGORY_FORMAL_BAN.get(slot) or {}
    floor = ban.get(item.get("category"))
    return floor is not None and need_formal >= floor


def build_candidates(wardrobe, ctx, weather, laundry=None, today=None,
                      formality_slack=0, formality_override=None):
    """按槽位构建候选池。

    formality_slack: 允许的正式度降级档数。0 = 只接受完全符合的，
    1 = 允许低一档，2 = 允许低两档。用于在衣橱不满足要求时优雅降级。
    formality_override: 直接指定正式度要求（运动套装用 0）。
    """
    today = today or datetime.date.today()
    laundry = laundry or {}
    slot_temp = ctx["slot_temp"]
    band = band_of(weather["feel_mean"])
    req = C.TEMPERATURE_BANDS[band]["required"]
    need_formal = ctx["formality"] if formality_override is None else formality_override

    pools = {s: [] for s in C.SLOT_ORDER}

    # 命理给的保暖余量（疾厄宫见煞）。三条硬规矩：
    # 一是只加不减，二是热天不生效（夏天"多穿一层"是错的），
    # 三是有上限（上限在 luck 里，0.10 clo 约一件薄针织）。
    # 22℃ 以上完全不生效，12℃ 以下全额，中间线性过渡——
    # 温和天气加满 0.10 会把短袖换成衬衫，那是穿多不是穿对。
    bonus = float(ctx.get("warmth_bonus") or 0)
    if bonus:
        m = weather["feel_mean"]
        if m > 22:
            bonus = 0.0
        elif m > 12:
            bonus *= (22 - m) / 10.0

    for item in wardrobe:
        slot = item.get("slot")
        if slot not in pools:
            continue
        # 非穿搭件直接跳过：批量导入的「饰品」文件夹里混着臂章、标牌、
        # 瓷砖找平器这类电商杂货，它们的 slot 也是 accessory
        if item.get("non_wearable") or item.get("category") == "junk":
            continue
        # 配件角色（皮带/袜/包/领带/丝袜）不进主候选池：
        # 它们由 extras 层按主体反推（皮带跟皮鞋、袜子跟裤子），没有独立自由度；
        # 混进 accessory 候选只会挤掉真正决定观感的项链耳饰。
        if EXTRAS.role_of(item):
            continue
        # 劳保/警示服与「这个正式度不该出现的品类」在进候选池前就拦掉：
        # 进了池，保暖匹配度会把它推到第一（荧光背心的 clo 常常刚好命中中层目标）
        if _banned_for_dress(item, slot, need_formal):
            continue
        state = laundry.get(item["id"], item.get("status", "clean"))
        if state != "clean":
            continue

        temp = slot_temp.get(slot, weather["feel_mean"])
        target = target_clo(slot, temp)

        if bonus and slot in ("base", "mid", "outer"):
            target += bonus

        fit = self_fit(item, slot, target, band)
        if fit is None:
            continue

        formal = item.get("formality", 2)
        lo, hi = C.FORMALITY_BANDS[slot].get(need_formal, (0, 4))
        if formal < lo - formality_slack:
            continue

        pools[slot].append({
            "item": item,
            "slot": slot,
            "warm_fit": fit,
            "formal": formal,
            "formal_gap": max(0, need_formal - formal),
            "state": state,
            "days": _days_since(item.get("last_worn"), today),
        })

    for s in pools:
        pools[s].sort(key=lambda c: (-c["warm_fit"], c["formal_gap"]))
        if s == "accessory":
            pools[s] = _trim_accessories(pools[s])
        else:
            pools[s] = pools[s][:12]
    return pools


def self_fit(item, slot, target, band):
    """单品与目标温度的匹配度。

    返回 None 表示该单品在此温度下物理上不可接受，直接剔除。
    保暖不足是硬约束（冷天不能拿薄西装外套充数），
    保暖过剩只在很热时才硬剔除（否则天冷时厚被子也得穿）。

    注意 delta > 0.30 也剔除：这时匹配度已经是 0，
    留着它只会「占住这一层」——16℃ 配出一件 0.92 clo 的羽绒服就是这么来的。
    宁可让缺口清单说「你有羽绒服但太厚」，也不能让引擎假装配齐了。
    """
    clo = item.get("clo", 0.2)
    if slot in ("base", "mid", "outer"):
        # 太热：目标接近 0 还穿厚外套 → 剔除
        if target <= 0.05 and clo > 0.16:
            return None
        # 太冷：外层/中层保暖值不足目标的一半 → 硬剔除
        if slot in ("outer", "mid") and target >= 0.30 and clo < target * 0.55:
            return None
        # 太热的老规则：≥28℃ 不穿羽绒服级
        if target <= 0.02 and clo > 0.30:
            return None
        delta = abs(clo - target)
        if delta > 0.30:
            return None
        return max(0.0, 1.0 - delta / 0.22)
    if slot == "shoes":
        if item.get("category") == "boots" and band in ("hot", "warm"):
            return 0.25
        if item.get("category") == "running_shoes" and band == "cold":
            return 0.35
        return 0.8
    return 0.8


# ---------------------------------------------------------------- 单项打分

def formality_cost(item_formality, required):
    """正式度偏离的代价。低于要求比高于要求更糟（太正式会显得刻意）。"""
    if item_formality == required:
        return 0.0
    if item_formality < required:
        return (required - item_formality) * 0.30
    return (item_formality - required) * 0.16


def harmony_score(colors):
    """配色协调分：全身非中性色不超过 2 个色系。

    色名先归一化——AI 识别和手工录入常写「藏青色」「深蓝色」，
    不归一化会全部落进点缀色，让配色分失去意义。
    """
    colors = [C.normalize_color(c) for c in colors]
    accents = [c for c in colors if c not in C.NEUTRAL_COLORS]
    families = {C.COLOR_FAMILY.get(a, a) for a in accents}
    if len(families) <= 1:
        return 1.0
    if len(families) == 2:
        return 0.85
    return max(0.0, 0.55 - 0.15 * (len(families) - 2))


def weather_score(items, weather):
    """雨、风、暴晒等特殊天气的加分/扣分。"""
    s = 0.75
    pop = weather["daily"]["pop_max"] or 0
    wind = weather["daily"]["wind_max"] or 0
    uv = weather["daily"]["uv_max"] or 0
    has_outer = any(i["slot"] == "outer" for i in items)
    if pop >= 40:
        if any(i.get("waterproof") for i in items if i["slot"] in ("outer", "shoes")):
            s += 0.25
        elif any(i.get("category") == "umbrella" for i in items):
            s += 0.20
        elif has_outer:
            s -= 0.20
        else:
            s -= 0.35
    if wind >= 25:
        if any(i.get("windproof") for i in items):
            s += 0.20
        elif has_outer:
            s -= 0.10
    if uv >= 8:
        if any(i.get("sun_protective") for i in items):
            s += 0.20
        else:
            s -= 0.15
    return min(1.0, max(0.0, s))


def freshness_score(days):
    """轮换分：越久没穿越优先，但新衣也有新鲜感加成。"""
    if days >= 999:
        return 0.85
    if days < 2:
        return 0.25
    if days < 4:
        return 0.55
    if days < 7:
        return 0.75
    return 1.0


# ---------------------------------------------------------------- 束搜索

def search(pools, ctx, weather, beam=200, allow_missing=False):
    """逐槽位扩展，保留最优 beam 个部分方案。

    allow_missing 时这三类组合直接剔除：只有两件不到三件、没有下装的、
    以及保暖值低于 MIN_FIT 的。半套衣服不叫方案，缺层交给 slot_gaps 说。
    """
    required = C.TEMPERATURE_BANDS[band_of(weather["feel_mean"])]["required"]
    slots = [s for s in C.SLOT_ORDER if s != "accessory"]

    combos = [([], 0.0)]
    for slot in slots:
        cand_list = pools.get(slot, [])
        if not cand_list:
            # 这一层一件可用的都没有：能缺层就跳过，不能缺层就没必要再往下拼
            if allow_missing or slot not in required:
                continue
            return []
        new_combos = []
        for chosen, sc in combos:
            for cand in cand_list:
                new_combos.append((chosen + [cand], sc))
        # 局部预筛：按 warm_fit 截断，避免组合爆炸
        new_combos.sort(key=lambda x: -sum(c["warm_fit"] for c in x[0]))
        combos = new_combos[:beam]

    scored = []
    for chosen, _ in combos:
        if not chosen:
            continue
        if allow_missing:
            # 没有下装不叫方案；两件半套也不叫。
            # 例外：必需层全齐时（例如 28℃ 只要内层），内层+下装就是完整一套。
            has_bottom = any(c["slot"] == "bottom" for c in chosen)
            has_required = all(any(c["slot"] == r for c in chosen) for r in required)
            if not has_bottom or not (has_required or len(chosen) >= 3):
                continue
        full = score_combo(chosen, ctx, weather, required, allow_missing=allow_missing)
        if full:
            scored.append(full)
    scored.sort(key=lambda r: -r["score"])
    return scored


def _luck_bonus(chosen, ctx):
    """幸运色加权：命中主色 +0.04，撞上避讳色 -0.04。

    权重刻意压得很小。命理是趣味层，它不该让引擎把零下十度的羽绒服
    换成一件薄风衣，也不该为了配色把正装换成休闲装。
    """
    luck = ctx.get("luck") or {}
    fam = luck.get("color_family")
    if not fam:
        return 0.0, False
    fams = set()
    for c in chosen:
        if c["slot"] in ("base", "mid", "outer", "bottom"):
            fams.add(C.COLOR_FAMILY.get(C.normalize_color(c["item"].get("color", "")), ""))
    bonus, hit = 0.0, False
    if fam in fams:
        bonus += 0.04
        hit = True
    if set(luck.get("avoid_families") or []) & fams:
        bonus -= 0.04
    return bonus, hit


def _study_bonus(chosen, ctx):
    """文昌日的配色纪律：越素净越加分，撞色扣分。

    斗数里文星主条理，穿到身上就是"配色收得住、颜色不抢话"。
    幅度刻意压在 ±0.03——比幸运色（0.04）还小一档，
    它是"今天更该素净"的偏好，不是"今天必须穿素"的规定：
    保暖和场合的权重远大于它，改不了底线的决定。
    """
    study = ctx.get("study") or {}
    if not study.get("flag"):
        return 0.0
    accents = []
    for c in chosen:
        if c["slot"] in ("base", "mid", "outer", "bottom"):
            col = C.normalize_color(c["item"].get("color", ""))
            if col not in C.NEUTRAL_COLORS:
                accents.append(col)
    families = {C.COLOR_FAMILY.get(a, a) for a in accents}
    if len(families) <= 1:
        return 0.03
    if len(families) == 2:
        return 0.01
    return -0.03


def score_combo(chosen, ctx, weather, required, allow_missing=False):
    """给一个完整组合打总分。allow_missing 时缺层只扣分不判死。"""
    items = [c["item"] for c in chosen]
    slots = [c["slot"] for c in chosen]

    missing = [r for r in required if r not in slots]
    if missing and not allow_missing:
        return None

    # 保暖：必需层权重更高
    warmth, wsum = 0.0, 0.0
    for c in chosen:
        w = 1.6 if c["slot"] in required else 0.7
        warmth += c["warm_fit"] * w
        wsum += w
    warmth = warmth / wsum if wsum else 0.0

    # 正式度：以「最差的那一件」为主，平均分只作辅。
    # 用纯平均时，7 件里塞一条牛仔裤，它的罚分被其余 6 件除没了——
    # 正式场合的成败由最不得体的那件决定，不是由平均值决定。
    req = ctx["formality"]
    per_item = [formality_cost(c["formal"], req) for c in chosen]
    worst = max(per_item) if per_item else 0.0
    mean_pen = sum(per_item) / max(1, len(per_item))
    formal_pen = 0.65 * worst + 0.35 * mean_pen

    # 配色
    colors = [c["item"].get("color", "黑") for c in chosen
              if c["slot"] in ("base", "mid", "outer", "bottom")]
    harm = harmony_score(colors)

    # 轮换
    fresh = sum(freshness_score(c["days"]) for c in chosen) / max(1, len(chosen))

    # 天气
    wsc = weather_score(items, weather)

    # 幸运色（可选，仅小幅加权）
    luck_bonus, luck_hit = _luck_bonus(chosen, ctx)

    # 文昌日：配色不抢话（可选，幅度更小）
    study_bonus = _study_bonus(chosen, ctx)

    # 穿搭铁律：整身色系数量、鞋是否跳色、运动鞋配西裤这类「搭不起来」的问题。
    # 只扣分不进候选池——硬门会让衣橱不全的人直接拿不到方案。
    style = STYLE.audit(chosen, ctx)

    base = (C.WEIGHTS["warmth"] * warmth
            + C.WEIGHTS["formality"] * max(0.0, 1.0 - formal_pen)
            + C.WEIGHTS["harmony"] * harm
            + C.WEIGHTS["freshness"] * fresh
            + C.WEIGHTS["weather"] * wsc
            + luck_bonus
            + study_bonus
            - 0.08 * len(missing))
    # 铁律按乘法扣：它是门槛不是加分项，减分会被保暖的细微差异顶掉
    score = base * (1.0 - C.STYLE_WEIGHT * (1.0 - style["score"]))

    return {
        "score": round(min(1.0, max(0.0, score)), 4),
        "missing": missing,
        "parts": {
            "warmth": round(warmth, 3),
            "formality": round(max(0.0, 1.0 - formal_pen), 3),
            "harmony": round(harm, 3),
            "style": round(style["score"], 3),
            "freshness": round(fresh, 3),
            "weather": round(wsc, 3),
            "luck": round(luck_bonus, 3),
            "study": round(study_bonus, 3),
        },
        "luck_hit": luck_hit,
        "chosen": chosen,
        "items": items,
    }


# ---------------------------------------------------------------- 理由生成

def explain(cand, ctx, weather):
    """为每件单品生成一句人话理由。"""
    item = cand["item"]
    slot = cand["slot"]
    temp = ctx["slot_temp"].get(slot, weather["feel_mean"])
    name = item.get("name", item.get("id"))

    if slot == "base":
        # 「要轻要透气」不能套在加绒加厚保暖衬衫上——文案得看这件衣服是什么，
        # 否则一眼就是模板句：说它轻，下一句又说它有厚度锁暖。
        heavy = (item.get("clo") or 0.2) >= 0.22 or any(
            w in _item_text(item) for w in ("加绒", "加厚", "保暖", "羊毛", "羊绒"))
        if heavy:
            return (f"{name}：{temp:.0f}℃ 体感，贴身层要能锁温，"
                    f"它{_describe_cushion(item)}。")
        return f"{name}：{temp:.0f}℃ 体感下贴身层要轻要透气，它{_describe_cushion(item)}。"
    if slot == "mid":
        return f"{name}：保暖值 {item.get('clo', 0.2):.2f} clo，搭在贴身层外补上温差。"
    if slot == "outer":
        if (weather["daily"]["pop_max"] or 0) >= 40:
            cap = "雨和风都能挡" if item.get("windproof") else "能挡雨" if item.get("waterproof") else "只能挡一部分风雨"
            return f"{name}：降水概率 {weather['daily']['pop_max']}%，外层得扛住，这件{cap}。"
        if weather["feel_min"] <= 12:
            return f"{name}：全天最低体感 {weather['feel_min']:.0f}℃，保暖值 {item.get('clo', 0.3):.2f} clo，是最关键的一件。"
        return f"{name}：{temp:.0f}℃ 下外层用这件刚好，早晚偏凉时也好脱下来拿手上。"
    if slot == "bottom":
        return f"{name}：下装选它是因为{_bottom_reason(item, weather)}。"
    if slot == "shoes":
        if (weather["daily"]["pop_max"] or 0) >= 40:
            return f"{name}：有雨，鞋得耐水防滑。"
        return f"{name}：{_shoe_reason(item, ctx)}。"
    if slot == "accessory":
        return f"{name}：{_accessory_reason(cand, ctx)}。"
    return f"{name}：点睛之笔，把整体正式度凑齐。"


def _type_reason(jtype, formal=2):
    if jtype == "pendant":
        return "吊坠落在锁骨下方，露出来正好"
    if jtype == "earring":
        return ("耳边留一点晃动，正式场合压得住" if formal >= 3
                else "耳边一点小变化，不抢镜")
    return {
        "necklace": "领口上一点亮，正式场合不抢戏",
        "stud": "耳钉不挑场合，最稳的一件",
        "bracelet": "手腕轻点缀，日常刚好",
        "bangle": "手镯比手链稳，抬手看得见",
        "ring": "一枚就够，最不挑场合",
        "brooch": "别在翻领上，分寸就立住了",
        "hair": "头发收干净，整个人显利落",
        "anklet": "脚踝留一点，露腿的日子刚好",
    }.get(jtype, "低调点缀")


def _accessory_reason(cand, ctx):
    """首饰的说辞：先说款式为什么合适，再补一句颜色为什么配得上。

    颜色那半句是这套衣服给的（在 _best_accessory 里算好挂在 cand 上），
    所以不传 chosen 也能说清楚。
    """
    item = cand["item"]
    if item.get("category") != "jewelry":
        return "点睛之笔，把整体正式度凑齐"
    jtype = jewelry_type(item)
    note = cand.get("harmony_note") or ""
    st = ctx.get("study") or {}
    so = ctx.get("social") or {}

    if (st.get("flag") or st.get("careful")) and jtype in ("ring", "stud"):
        return "今天文书多，手上耳边都利落一点好"
    if (st.get("flag") or st.get("careful")) and jtype == "bracelet":
        return "文书多的日子，手腕别挂叮当的"
    if so.get("flag") and jtype in ("necklace", "pendant", "earring"):
        return "见人有点小运气，配饰留一点存在感"

    base = _type_reason(jtype, ctx.get("formality", 2))
    # 撞色的那句不往搭配理由里塞——那是扣分项，不该写成卖点
    if note and "不同路" not in note:
        return f"{base}，{note}" if base else note
    return base


def _describe_cushion(item):
    mat = item.get("material", "")
    clo = item.get("clo", 0.2)
    if clo <= 0.14:
        return "极薄不闷汗"
    if clo <= 0.20:
        return f"{mat or '棉'}质贴身穿不粘身"
    return f"{mat or '材质'}有厚度，锁住暖意"


def _bottom_reason(item, weather):
    if weather["feel_min"] <= 10:
        return f"最低体感 {weather['feel_min']:.0f}℃，腿不能受凉"
    if (weather["daily"]["pop_max"] or 0) >= 40:
        return "雨天避免浅色长裤溅泥"
    return "和上装配色平衡，也方便久坐"


def _shoe_reason(item, ctx):
    if ctx["formality"] >= 3:
        return "正式场合，鞋得跟上"
    return "通勤走路舒服就够了"


# ---------------------------------------------------------------- 配饰

# 首饰按款式细分。款式决定了它能出现在哪、适合什么场合：
# 耳钉天天能戴，耳环只在正式场合成立；胸针必须有翻领可别。
# 导入阶段已把这些写进 item["jewelry_type"]，这里只做兜底推断。
JEWELRY_TYPE_WORDS = [
    ("brooch", ("胸针", "胸花", "别针")),
    ("stud", ("耳钉", "耳夹")),
    ("earring", ("耳环", "耳饰", "耳坠", "耳线", "耳钩")),
    ("necklace", ("项链", "锁骨链", "颈链")),
    ("pendant", ("吊坠", "项坠", "挂坠")),
    ("bangle", ("手镯", "手环")),
    ("bracelet", ("手链", "手串", "手绳")),
    ("ring", ("戒指", "指环")),
    ("anklet", ("脚链", "脚绳")),
    ("hair", ("发夹", "发箍", "发带", "发簪", "发卡", "发饰")),
]

# 色系冷暖。金饰配暖调衣服、银饰配冷调衣服是搭配常识，
# 比「金银是中性色所以什么都能配」有信息量——后者等于没判断。
WARM_FAMILIES = {"红", "橙", "黄", "棕", "粉"}
COOL_FAMILIES = {"蓝", "绿", "紫"}
ADJACENT_PAIRS = [
    {"红", "粉"}, {"红", "橙"}, {"橙", "黄"}, {"黄", "绿"}, {"绿", "蓝"},
    {"蓝", "紫"}, {"紫", "粉"}, {"红", "紫"}, {"棕", "红"}, {"棕", "黄"},
]

# 金属色不是颜色。色表里没有金银，但首饰的 color 会写它们，
# 不拦住就会把「金」当成一个彩色色系去跟衣服撞色。
METAL_COLORS = {"金", "银", "钨金", "玫瑰金", "白金", "彩金", "金色", "银色", "合金"}


def _tone_of(item):
    """金属冷暖。导入阶段会写 tone，这里兜底——手工录入的单品没有这个字段。"""
    t = item.get("tone")
    if t in ("warm", "cool", "neutral"):
        return t
    metal = (item.get("metal") or "").lower()
    if metal in ("gold", "rose"):
        return "warm"
    if metal == "silver":
        return "cool"
    c = item.get("color") or ""
    if c in ("金", "玫瑰金", "金色", "彩金"):
        return "warm"
    if c in ("银", "白金", "银色"):
        return "cool"
    return "neutral"


def jewelry_type(item):
    t = item.get("jewelry_type")
    if t:
        return t
    name = item.get("name") or ""
    for jtype, words in JEWELRY_TYPE_WORDS:
        if any(w in name for w in words):
            return jtype
    return ""


def _jewelry_allowed(item, jtype, ctx, chosen, weather):
    """款式层面成不成立。不成立的直接不出现，而不是靠扣分去竞争。

    扣分是可以被加分抵掉的——颜色配得再好，正式场合也不该出现手链；
    没外套的时候胸针也没地方别。这些是硬约束，不是分数问题。
    """
    if not jtype:
        return False                      # 不知道是什么款式，就判断不了
    formal = ctx["formality"]
    if jtype == "bracelet" and formal >= 3:
        return False
    if jtype == "earring" and formal <= 1:
        return False                      # 耳环有存在感，日常反而多余
    if jtype == "brooch" and not any(c.get("slot") == "outer" for c in chosen):
        return False
    if jtype == "anklet" and (weather.get("feel_min") or 0) < 18:
        return False                      # 不露脚踝的季节戴脚链是自找麻烦
    if jtype == "hair" and formal >= 3:
        return False                      # 正式场合头发上别再添东西
    return True


def _outfit_tone(chosen):
    """这套衣服的彩色家族、冷暖倾向，以及每个色系落在哪一层。

    只数彩色：中性色（黑白灰米驼）不表态，全身中性才是「没彩色」。
    """
    fams, warm, cool, hosts = set(), 0, 0, {}
    for c in chosen:
        if c.get("slot") == "accessory":
            continue
        col = C.normalize_color(c["item"].get("color"))
        fam = C.COLOR_FAMILY.get(col)
        if not fam or col in C.NEUTRAL_COLORS:
            continue
        fams.add(fam)
        hosts.setdefault(fam, c)
        if fam in WARM_FAMILIES:
            warm += 1
        elif fam in COOL_FAMILIES:
            cool += 1
    return fams, warm, cool, hosts


def _jewelry_harmony(item, chosen, ctx):
    """首饰和这套衣服配不配。返回 (加分, 理由)。

    首饰是点缀不是主体，所以判断标准和衣服互搭不一样：
    衣服多一个色系是灾难，首饰多一个色系可能正是点睛——
    区别在于它跟已有颜色有没有关系。
    """
    fams, warm, cool, hosts = _outfit_tone(chosen)
    jc = C.normalize_color(item.get("color") or "")
    jfam = C.COLOR_FAMILY.get(jc, jc) if jc else ""
    neutral = (not jc) or jc in C.NEUTRAL_COLORS or jc in METAL_COLORS
    tone = _tone_of(item)
    delta, reason = 0.0, ""

    if not neutral and jfam:
        if jfam in fams:
            delta += 0.14
            host = hosts.get(jfam)
            slot_cn = C.SLOT_NAME.get((host or {}).get("slot"), "")
            reason = (f"和{slot_cn}同一个色系，看着成套"
                      if slot_cn else "和身上的彩色呼应")
        elif not fams:
            delta += 0.10
            reason = "一身素色，用一点颜色提气"
        elif any({jfam, f} in ADJACENT_PAIRS for f in fams):
            delta += 0.02
        else:
            delta -= 0.10
            reason = "和身上的颜色不同路，容易显杂"
    else:
        # 金属和素色首饰不占色系位，怎么搭都不出错
        delta += 0.10 if not fams else 0.04
        if not fams:
            reason = "全身没彩色，首饰是唯一的亮点"

    # 金属冷暖：金配暖、银配冷
    if tone == "warm" and warm and not cool:
        delta += 0.06
        reason = reason or "暖色衣服配金，色调顺"
    elif tone == "cool" and cool and not warm:
        delta += 0.06
        reason = reason or "冷色衣服配银，色调顺"
    elif tone in ("warm", "cool") and (warm + cool) >= 2:
        # 冷暖撞：不是错，但没必要为一件首饰制造矛盾
        delta -= 0.05

    # 幸运色最容易落在配饰上——改一件首饰比改全身主色克制得多。
    # 同时命中衣服色系时合并成一句：看得见的理由比玄的更有说服力。
    lk = ctx.get("luck") or {}
    lfam = lk.get("color_family")
    if lfam and jfam == lfam:
        delta += 0.08
        if jfam in fams:
            host = hosts.get(jfam)
            slot_cn = C.SLOT_NAME.get((host or {}).get("slot"), "")
            reason = (f"和{slot_cn}同色系，也正合今天的幸运色" if slot_cn
                      else "和身上的彩色呼应，也正合今天的幸运色")
        else:
            reason = f"今天的幸运色系是{lfam}，戴它正好"
    return delta, reason


def _jewelry_gain(item, jtype, ctx, chosen, weather):
    """首饰排序分：款式适配场合。

    不合适的情形已经被 _jewelry_allowed 挡在门外，所以这里只有加分——
    留下来的都是「能戴的」，比的是谁更合适。
    两条边界不动：不改正式度、不碰保暖。首饰只决定戴不戴、戴哪件。
    """
    gain = 0.0
    formal = ctx["formality"]

    if jtype == "necklace":
        gain += 0.18 + (0.20 if formal >= 3 else 0.0)
    elif jtype == "pendant":
        # 吊坠是项链的轻量版，日常也能戴
        gain += 0.16 + (0.18 if formal >= 3 else -0.02)
    elif jtype == "stud":
        # 耳钉不挑场合，日常最稳的一件
        gain += 0.15 + (0.10 if 2 <= formal <= 3 else 0.0)
    elif jtype == "earring":
        gain += 0.10 + (0.22 if formal >= 3 else 0.0)
    elif jtype == "bracelet":
        gain += 0.14 + (0.12 if formal <= 2 else 0.0)
    elif jtype == "bangle":
        gain += 0.13 + (0.06 if formal <= 2 else 0.0)
    elif jtype == "ring":
        gain += 0.12
    elif jtype == "brooch":
        # 已经确认有外套可别，剩下的就是它比别的首饰更有分寸
        gain += 0.32
    elif jtype == "hair":
        gain += 0.08 + (0.10 if formal <= 2 else 0.0)
    elif jtype == "anklet":
        gain += 0.12 + (0.08 if formal <= 2 else 0.0)

    # 桃花日：见人的场合配饰要有存在感（luck.social 本来就在说这件事）
    so = ctx.get("social") or {}
    if so.get("flag") and jtype in ("necklace", "pendant", "earring"):
        gain += 0.10
    # 文昌日：写字敲键盘，手腕上的东西最碍事
    st = ctx.get("study") or {}
    if st.get("flag") or st.get("careful"):
        if jtype == "bracelet":
            gain -= 0.25
        elif jtype == "ring":
            gain += 0.05
    return gain


def _score_accessory(cand, chosen, ctx, weather):
    """一个候选配饰在这套搭配里的得分和理由。不成立返回 None。"""
    item = cand["item"]
    cat = item.get("category")
    gain, note = 0.0, ""
    if cat == "umbrella" and (weather["daily"]["pop_max"] or 0) >= 35:
        gain += 0.5
    if cat in ("scarf", "hat", "gloves") and weather["feel_min"] <= 8:
        gain += 0.4
        if cat == "hat":
            note = "天冷，帽子比任何首饰都实在"
    if cat == "sunglasses" and (weather["daily"]["uv_max"] or 0) >= 6:
        gain += 0.3
    if cat == "belt" and ctx["formality"] >= 3:
        gain += 0.25
    if cat == "jewelry":
        jtype = jewelry_type(item)
        if not _jewelry_allowed(item, jtype, ctx, chosen, weather):
            return None
        gain += _jewelry_gain(item, jtype, ctx, chosen, weather)
        # 颜色合理性单独算：它是这套衣服给的，不是首饰自己带的分
        hdelta, note = _jewelry_harmony(item, chosen, ctx)
        gain += hdelta
    gain += cand["warm_fit"] * 0.2
    return gain, note


def _best_accessory(result, pools, ctx, weather):
    """挑一件最能提升整体分的配饰。"""
    chosen = result.get("chosen") or []
    best, best_gain, best_note = None, 0.0, ""
    for cand in pools.get("accessory", []):
        scored = _score_accessory(cand, chosen, ctx, weather)
        if not scored:
            continue
        gain, note = scored
        if gain > best_gain:
            best, best_gain, best_note = cand, gain, note
    if best is None or best_gain < 0.25:
        return None
    # 必须返回副本：pools 里的候选是所有方案共用的，
    # 就地写 harmony_note 会让后算的方案覆盖前一套的颜色理由，
    # 于是页面上的搭配和理由对不上（衣服是黄鞋，理由说全身没彩色）。
    return {**best, "harmony_note": best_note}


def _side_earring(result, pools, ctx, weather, main):
    """正式场合的耳机位：项链配耳钉是标准组合，耳朵和脖子不抢地盘。

    只补耳饰，且只在正式场合补——日常一对耳钉就够，
    两条项链、两个手镯叠着戴不是这套系统该管的事。
    冷天主件是帽子/围巾时也不补，压着耳朵戴不舒服。
    """
    if ctx["formality"] < 3:
        return None
    if main is not None:
        mcat = main["item"].get("category")
        if mcat in ("hat", "scarf"):
            return None
        if jewelry_type(main["item"]) in ("stud", "earring"):
            return None
    chosen = result.get("chosen") or []
    best, best_gain, best_note = None, 0.0, ""
    for cand in pools.get("accessory", []):
        item = cand["item"]
        if item.get("category") != "jewelry":
            continue
        if jewelry_type(item) not in ("stud", "earring"):
            continue
        scored = _score_accessory(cand, chosen, ctx, weather)
        if not scored:
            continue
        gain, note = scored
        if gain > best_gain:
            best, best_gain, best_note = cand, gain, note
    if best is None or best_gain < 0.24:
        return None
    # 主件已经讲过「首饰是唯一亮点」，副件再说一遍就成了复读。
    # 副件只补它自己带来的新信息（比如冷暖金属）。
    if "唯一的亮点" in best_note:
        best_note = ""
    return {**best, "harmony_note": best_note}


# ---------------------------------------------------------------- 运动套装

def sport_outfit(wardrobe, ctx, weather, laundry=None, today=None):
    """单独拼一套运动装备。

    用独立候选池（正式度要求=0），而不是复用通勤池，
    否则会把衬衫西裤当成运动装备推给用户。
    """
    today = today or datetime.date.today()
    sport_ctx = dict(ctx)
    sport_ctx["formality"] = 0
    sport_ctx["slot_temp"] = {
        "base": max(weather["feel_max"], 18),
        "mid": max(weather["feel_mean"], 16),
        "outer": max(weather["feel_min"], 14),
        "bottom": max(weather["feel_mean"], 16),
        "shoes": max(weather["feel_mean"], 16),
    }
    pools = build_candidates(wardrobe, sport_ctx, weather, laundry, today,
                             formality_slack=0, formality_override=0)

    picks = []
    for slot in ("base", "mid", "outer", "bottom", "shoes"):
        cands = pools.get(slot, [])
        if not cands:
            continue
        # 优先真正运动属性的单品；否则退到休闲款（正式度≤1）；
        # 都没有就宁可缺这一层，也不能把衬衫西裤塞进运动套装。
        sport_first = [c for c in cands if c["item"].get("sport") or
                       c["item"].get("category") in (
                           "running_shoes", "sport_tee", "leggings", "sports_bra",
                           "track_jacket", "gym_pants", "sweatpants")]
        casual = [c for c in cands if c["formal"] <= 1]
        pick = sport_first[0] if sport_first else (casual[0] if casual else None)
        if pick:
            picks.append(pick)
    return picks


# ---------------------------------------------------------------- 主入口

def recommend(wardrobe, ctx, weather, laundry=None, top_n=3, today=None):
    """返回 (排序后的方案列表, 候选池, 降级信息)。"""
    today = today or datetime.date.today()

    # 命理加严后如果一件都配不出来，退回不加严再算一次。
    # 提示层不能变成拦路的功能——「今天体感偏弱」不该让推荐开天窗。
    bonus = float(ctx.get("warmth_bonus") or 0)
    attempts = [bonus] + ([0.0] if bonus else [])

    results, pools, degraded, used_bonus = [], {}, None, 0.0
    for b in attempts:
        cx = ctx if b == bonus else {**ctx, "warmth_bonus": 0.0}
        used_bonus = b
        for slack in (0, 1, 2):
            pools = build_candidates(wardrobe, cx, weather, laundry, today, formality_slack=slack)
            results = search(pools, cx, weather)
            if results:
                if slack > 0:
                    degraded = {
                        "slack": slack,
                        "note": f"衣橱里没有完全符合「{ctx['formality_label']}」要求的单品，"
                                f"已降级到低 {slack} 档正式度挑选。",
                    }
                break
        if results:
            break

    # 齐套配不出来时退一步：只用保暖值对得上的单品拼一个「临时方案」。
    # 这一步是给衣橱没录全的人用的——但你得知道缺的是哪一层，
    # 所以缺口单独算（gaps），不能靠一件 0.9 clo 的羽绒服假装凑齐 15℃。
    # 正式度也按同样的降级顺序试，降了几档要如实标出来。
    partial = False
    unfiltered = pools
    if not results:
        for slack in (0, 1, 2):
            p2 = build_candidates(wardrobe, cx, weather, laundry, today, formality_slack=slack)
            thin = {s: [c for c in v if c["warm_fit"] >= MIN_FIT] for s, v in p2.items()}
            r2 = search(thin, cx, weather, allow_missing=True)
            if r2:
                results, pools, partial, unfiltered = r2, thin, True, p2
                degraded = {
                    "slack": slack,
                    "note": (f"衣橱里没有完全符合「{ctx['formality_label']}」要求的单品，"
                             f"已降级到低 {slack} 档正式度挑选。" if slack else ""),
                }
                break

    # 缺口用「未过滤」的候选池算：这样"有这一类但太厚／太薄"才说得出来
    gaps = slot_gaps(unfiltered, cx, weather, wardrobe)

    if not results:
        # 连临时方案都拼不出来（比如只剩一件外套）：把缺什么说清楚，别只丢一句"请补充单品"
        return [], unfiltered, {
            "degraded": {"slack": 99, "note": gaps_note(gaps) or "今天的体感温度下，衣橱里没有能穿的单品。",
                         "missing": [g["slot_name"] for g in gaps]},
            "sport_outfit": [], "partial": False, "gaps": gaps,
        }

    # 配件按角色归一次档：三套方案共用，不必每套重扫 1988 件
    extra_bucket = EXTRAS.index(wardrobe)

    finals = []
    for r in results:
        best = _best_accessory(r, pools, ctx, weather)
        if best:
            r["chosen"].append(best)
            r["items"].append(best["item"])
            r["score"] = round(r["score"] + best["warm_fit"] * 0.05, 4)
        # 正式场合多一个耳机位：项链配耳钉是标准组合，不算堆砌。
        # 但文昌日（考试/面试）的规矩是「配饰最多一件」——
        # 文案里写了规矩，代码里就得执行，否则就是自己打自己。
        study = ctx.get("study") or {}
        quiet = bool(study.get("flag")) and study.get("level") != "careful"
        side = None if quiet else _side_earring(r, pools, ctx, weather, best)
        if side:
            r["chosen"].append(side)
            r["items"].append(side["item"])
        finals.append(r)

    out = []
    # 多样性：三套方案要真的能选，不能只换一件外套的颜色。
    # 判据是「核心五层里至少有 3 层不是同一件」；凑不出 3 就退到 2，再退到 1。
    # 以前只判「外层或下装不同」，于是「同一套 + 换个羽绒服颜色」也算差异化，
    # 三套分数差 0.015，用户看到的其实是同一身衣服。
    picked, sigs = [], []
    for need in (3, 2, 1):
        for idx, r in enumerate(finals):
            if len(picked) >= top_n:
                break
            if any(p[0] == idx for p in picked):
                continue
            sig = {c["slot"]: c["item"]["id"] for c in r["chosen"]
                   if c["slot"] in CORE_SLOTS}
            if all(sum(1 for s in CORE_SLOTS if sig.get(s) != t.get(s)) >= need
                   for t in sigs):
                picked.append((idx, r))
                sigs.append(sig)
        if len(picked) >= top_n:
            break
    picked = [r for _, r in picked][:top_n]

    # 只要还有缺口（哪怕方案本身能穿，比如只差一双鞋），就得如实标注
    incomplete = partial or bool(gaps)
    gap_names = [g["slot_name"] for g in gaps]

    for i, r in enumerate(picked):
        outfit = []
        for c in sorted(r["chosen"], key=lambda c: C.SLOT_ORDER.index(c["slot"])):
            outfit.append({
                "slot": c["slot"],
                "slot_name": C.SLOT_NAME[c["slot"]],
                "item": c["item"],
                "reason": explain(c, ctx, weather),
            })
        # 铁律要在配饰加上之后再跑一遍：配饰数量、鞋与整身的关系都变了
        check = STYLE.audit(r["chosen"], ctx)
        # 配件收口：皮带/袜子/包/领带不在候选池里（保暖值≈0，且没有自由度——
        # 皮带只能跟皮鞋同色），所以在这里按主体反推。有就挑出那条，没有就开清单。
        ex = EXTRAS.check(r["chosen"], wardrobe, ctx, bucket=extra_bucket)
        out.append({
            "rank": i + 1,
            "score": r["score"],
            "parts": {**r["parts"], "style": check["score"]},
            "outfit": outfit,
            "label": ("临时方案 · " if incomplete else "")
                     + _label_for(ctx, max((c["formal"] for c in r["chosen"]), default=None)),
            # 搭配师的三段式：结论 / 整套 / 这身的坑。
            # 只给方案不给坑，等于把「搭不搭得上」的判断留给用户自己。
            "verdict": check["verdict"],
            "style_issues": check["issues"],
            "pitfalls": STYLE.summarize(check, r["chosen"], ctx),
            # 配件三件事：衣橱里有且配得上的（直接戴）、配错的、还缺的
            "extras": ex["picked"],
            "extra_issues": ex["issues"],
            "extras_needed": ex["needs"],
            # 不完整方案必须自己承认缺什么，不能让用户以为这就是「今天这套」
            "partial": incomplete,
            "missing": gap_names,
        })

    sport = []
    if ctx.get("has_sport"):
        sp = sport_outfit(wardrobe, ctx, weather, laundry, today)
        sport = [{"slot": c["slot"], "slot_name": C.SLOT_NAME[c["slot"]],
                  "item": c["item"]} for c in sp]

    # 「还差一条皮带」是衣橱的属性，不是这一套的属性。
    # 三套方案各说一遍，等于同一句话讲三次——合并成一份，页面顶部只说一次。
    extras_gaps = EXTRAS.merge_needs(r["extras_needed"] for r in out)

    return out, pools, {"degraded": degraded, "sport_outfit": sport,
                        "warmth_relaxed": bool(bonus) and used_bonus == 0.0,
                        "partial": incomplete, "gaps": gaps,
                        "extras_gaps": extras_gaps}


def _label_for(ctx, achieved=None):
    """方案标题。

    achieved 是这套里实际最高的正式度：日程要求「正式场合」而衣橱只到休闲时，
    标题不能还写「正式场合全套」——那是在替一件卫衣撒谎。
    """
    req = ctx["formality"]
    if achieved is not None and achieved < req:
        return f"{C.FORMALITY_LABELS[req]}（衣橱只到{C.FORMALITY_LABELS[achieved]}）"
    if req >= 4:
        return "正式场合全套"
    if req >= 3:
        return "商务会面稳妥版"
    if req <= 1:
        return "舒适日常版"
    return "常规办公版"
