# -*- coding: utf-8 -*-
"""出差 / 旅行打包：把逐日推荐压缩成一份真能装进行李箱的清单。

和「今天穿什么」的根本区别：

    出差不是每天一套新衣服，而是「穿一套 + 带几件可替换的」。

如果直接按天给方案，5 天出差会给出 20 件衣服，没人会那样装箱。
所以这里做三件事：

  1. 逐日独立推荐，取当天最优方案
  2. 按槽位统计每件衣服被选中的次数，用配额裁出真正要带的件数
  3. 把被裁掉的单品替换成清单内的同层替代品——
     保证「你带的这几件，确实能搭出每天的方案」，而不是清单和方案两套东西

内层按天算（贴身必须换），外层和鞋按复用算（一件顶好几天）。
"""
import math

from . import config as C
from . import context as CTX
from . import recommend as REC

SLOT_NAME = C.SLOT_NAME

# 汉字星期，用于逐日卡片
_WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------------------------------------------------------------- 配额

def quota_of(slot, days, laundry=True, span=None):
    """某层这次该带几件。

    laundry=True 表示途中会洗/有洗衣条件，件数可以压下来。
    span 是行程内体感跨度：温差大才需要两件不同厚度的中层/外层，
    只按天数堆件数是错的——同一件羽绒服穿五天是常态。
    返回的是上限，实际还要受衣橱里可用件数限制。
    """
    big_span = span is not None and span >= 12
    if slot == "base":
        # 贴身每天换：不洗就按天带，洗则约每两天一件
        return min(7, days) if not laundry else min(5, 1 + math.ceil(days / 2))
    if slot == "bottom":
        # 下装能连穿，越久越靠洗
        return min(4, 1 + days // 3) if not laundry else min(3, 1 + days // 5)
    if slot == "mid":
        # 中层不贴身，可以连穿；只有温差大或行程长才带第二件
        return 2 if (big_span or days >= 4) else 1
    if slot == "outer":
        # 外套一件穿到底，只有温差大时才需要薄厚各一件
        return 2 if big_span else 1
    if slot == "shoes":
        return 1
    if slot == "accessory":
        return 2
    return 1


QUOTA_NOTE = {
    "base": "贴身层每天换，按天数带",
    "bottom": "下装可以连穿两三天",
    "mid": "中层轮换，出一身汗才需要换",
    "outer": "外套不用换，一件穿到底",
    "shoes": "一双鞋走完整个行程",
    "accessory": "项链和耳钉各一件就够，正式场合戴的那套别忘",
}

# 量词：鞋论双，其余论件
UNIT = {"shoes": "双", "bottom": "条", "accessory": "件"}


def _unit(slot):
    return UNIT.get(slot, "件")


# ---------------------------------------------------------------- 单日情境

def _day_context(formality, weather, day_index, purpose):
    """构造某一天的穿衣情境，字段与 timeline 保持一致。"""
    return {
        "formality": formality,
        "formality_label": C.FORMALITY_LABELS.get(formality, "常规办公"),
        "has_sport": False,
        "indoor_ratio": 0.55,      # 出差多为室内会议，暴露时间短
        "events": [],
        "advice": [],
        "day_index": day_index,
        "purpose": purpose,
        "slot_temp": {
            "base": weather["feel_max"],
            "mid": weather["feel_mean"],
            "outer": weather["feel_min"],
            "bottom": weather["feel_mean"],
            "shoes": weather["feel_mean"],
        },
    }


def _replace_with_packed(rec, packed_by_slot):
    """把方案里「没带」的单品换成清单内的同层替代品。

    优先换成 clo 最接近的，避免保暖被换崩。
    返回 (新方案, 被替换的槽位列表)。
    """
    outfit, swapped = [], []
    for o in rec["outfit"]:
        slot = o["slot"]
        chosen = packed_by_slot.get(slot) or []
        if not chosen:
            outfit.append(o)
            continue
        ids = {c["item"]["id"] for c in chosen}
        if o["item"]["id"] in ids:
            outfit.append(o)
            continue
        # 同层里挑 clo 最接近的
        target = o["item"].get("clo", 0.3)
        best = min(chosen, key=lambda c: abs(c["item"].get("clo", 0.3) - target))
        outfit.append({
            "slot": slot, "slot_name": SLOT_NAME[slot],
            "item": best["item"],
            "reason": f"这次带的是{best['item']['name']}，保暖接近，直接换这一件。",
            "swapped_from": o["item"]["name"],
        })
        swapped.append(SLOT_NAME[slot])
    return {**rec, "outfit": outfit}, swapped


# ---------------------------------------------------------------- 主入口

def plan_trip(wardrobe, days_weather, formality=2, purpose="", laundry=True,
              luck_travel=None):
    """生成出差打包方案。

    参数：
        wardrobe      —— 衣橱 items 列表
        days_weather  —— weather.fetch_days 的返回值（已按日期排序）
        formality     —— 本次出差的正式度 0-4
        purpose       —— 出差目的文字，用于文案
        laundry       —— 途中是否有洗衣条件
        luck_travel   —— 迁移宫给的出行提示（dict，可为 None）。
                         单独放 luck_notes，不混进 alerts：
                         alerts 是"你行李没带够"这类事实，命理提示不是同一层级，
                         混在一起会让用户以为提醒比实际更严重。

    返回 dict，包含逐日方案、打包清单、提醒。
    """
    days_weather = list(days_weather or [])
    if not days_weather:
        return {"error": "没有可用的天气数据", "packing": [], "daily_plans": [], "alerts": []}

    n = len(days_weather)
    span = round(max(w["feel_max"] for w in days_weather)
                 - min(w["feel_min"] for w in days_weather), 1)

    # ---- 1. 逐日推荐，并统计每个槽位哪些单品被选中过
    daily_plans, slot_hits, empty_days = [], {}, []
    for i, w in enumerate(days_weather):
        ctx = _day_context(formality, w, i, purpose)
        try:
            recs, _, _ = REC.recommend(wardrobe, ctx, w, top_n=4)
        except Exception:
            recs = []
        if not recs:
            empty_days.append(w["date"])
            continue
        best = recs[0]
        daily_plans.append({
            "date": w["date"],
            "weekday": _WEEK[_weekday(w["date"])],
            "short": _short_date(w["date"]),
            "weather": w["daily"],
            "band": C.TEMPERATURE_BANDS[REC.band_of(w["feel_mean"])]["label"],
            "feel_min": w["feel_min"], "feel_max": w["feel_max"],
            "recommendation": best,
        })
        # 前 3 名都计入，排名越靠前权重越高：让"能配更多天"的衣服优先留下
        for rank, rec in enumerate(recs[:3]):
            weight = 3 - rank
            for o in rec["outfit"]:
                slot = o["slot"]
                bucket = slot_hits.setdefault(slot, {})
                key = o["item"]["id"]
                if key not in bucket:
                    bucket[key] = {"item": o["item"], "hits": 0, "best": 0.0, "used": 0}
                bucket[key]["hits"] += weight
                bucket[key]["best"] = max(bucket[key]["best"], rec["score"] or 0)
                if rank == 0:
                    bucket[key]["used"] += 1     # 只统计进了最优方案的天数

    if not daily_plans:
        # 一天都排不出来时，别只说"先补充单品"：
        # 按这趟最冷的那天算一遍缺口，告诉用户到底缺哪一层、该多厚。
        coldest = min(days_weather, key=lambda d: d["feel_mean"])
        ctx = _day_context(formality, coldest, 0, purpose)
        pools = REC.build_candidates(wardrobe, ctx, coldest)
        gaps = REC.slot_gaps(pools, ctx, coldest, wardrobe)
        return {
            "error": REC.gaps_note(gaps, when="这趟") or "衣橱里没有能应付这趟行程的组合，先补充单品。",
            "packing": [], "daily_plans": [], "gaps": gaps,
            "alerts": ["衣橱缺件：连一套完整搭配都凑不出来"],
        }

    # ---- 2. 按配额裁剪出真正要带的清单
    packing, packed_by_slot = [], {}
    for slot in C.SLOT_ORDER:
        bucket = slot_hits.get(slot)
        if not bucket:
            continue
        limit = quota_of(slot, n, laundry, span)
        ordered = sorted(bucket.values(), key=lambda x: (-x["hits"], -x["best"]))
        # 只带方案里真正用得上的：从头到尾没出现过的衣服不该占行李箱
        picked = [x for x in ordered if x["used"] > 0][:limit]
        if slot == "shoes" and not picked:
            picked = ordered[:1]          # 鞋不能让行程裸奔
        picked_ids = {x["item"]["id"] for x in picked}

        # 贴身层和下装是消耗品：算法每天推同一件，不代表真能一件穿五天。
        # 不足配额时按 clo 与正式度最接近的原则，从衣橱同层补足替换件。
        extra = []
        if slot in ("base", "bottom") and picked and len(picked) < limit:
            closs = sorted(x["item"].get("clo", 0.3) for x in picked)
            ref_clo = closs[len(closs) // 2]
            ref_fml = picked[0]["item"].get("formality", 2)
            spare = [i for i in wardrobe
                     if i.get("slot") == slot
                     and i.get("id") not in picked_ids
                     and i.get("status") != "dirty"
                     and abs(i.get("formality", 2) - ref_fml) <= 1]
            spare.sort(key=lambda i: abs(i.get("clo", 0.3) - ref_clo))
            extra = [{"item": i, "hits": 0, "best": 0.0, "used": 0}
                     for i in spare[: limit - len(picked)]]

        picked_all = picked + extra
        if not picked_all:
            continue
        packed_by_slot[slot] = picked_all

        picked_items = []
        for pd in picked_all:
            it = pd["item"]
            used = sum(1 for d in daily_plans
                       if any(o["item"]["id"] == it["id"]
                              for o in d["recommendation"]["outfit"]))
            picked_items.append(dict(it, used_days=used, spare=(pd["used"] == 0)))
        want = quota_of(slot, n, laundry)
        packing.append({
            "slot": slot,
            "slot_name": SLOT_NAME[slot],
            "count": len(picked_items),
            "unit": _unit(slot),
            "want": want,
            # 缺口：清单里的件数不够换洗，前端据此高亮
            "shortfall": max(0, want - len(picked_items)) if slot in ("base", "bottom") else 0,
            "items": picked_items,
            "note": QUOTA_NOTE.get(slot, ""),
            "capped": len(ordered) > limit,
        })

    # ---- 3. 逐日方案对齐到清单：保证「带的能穿出每天的方案」
    swap_note = []
    for d in daily_plans:
        rec, swapped = _replace_with_packed(d["recommendation"], packed_by_slot)
        d["recommendation"] = rec
        if swapped:
            swap_note.append(f"{d['short']} 的{('、'.join(swapped))}换成清单内的替代品")

    # ---- 4. 提醒
    alerts = list(_alert_gap_warmth(wardrobe, formality, days_weather))
    alerts += _alert_clothing(wardrobe, n, laundry, packed_by_slot, span)
    alerts += _alert_weather(days_weather)
    if empty_days:
        alerts.append(f"{'、'.join(_short_date(x) for x in empty_days)} 凑不出完整搭配，"
                      f"这些天的方案已跳过。")

    advice = _advice(packing, days_weather, n, laundry)
    advice += swap_note[:3]

    total = sum(p["count"] for p in packing)
    return {
        "days": n,
        "purpose": purpose,
        "formality": formality,
        "formality_label": C.FORMALITY_LABELS.get(formality, "常规办公"),
        "laundry": laundry,
        "daily_plans": daily_plans,
        "packing": packing,
        "total_items": total,
        "alerts": alerts,
        "advice": advice,
        "temp_span": span,
        "need_layers": _need_layers(days_weather),
        "luck_notes": [(luck_travel.get("trip_note") or luck_travel.get("note"))]
                        if (luck_travel or {}).get("trip_note") or (luck_travel or {}).get("note")
                        else [],
        "luck_travel": luck_travel,
    }


# ---------------------------------------------------------------- 辅助

def _weekday(date_str):
    import datetime as dt
    try:
        return dt.date.fromisoformat(str(date_str)).weekday()
    except Exception:
        return 0


def _short_date(date_str):
    """2026-11-06 → 11/06"""
    s = str(date_str)
    return f"{s[5:7]}/{s[8:10]}" if len(s) >= 10 else s


def _need_layers(days_weather):
    """这趟行程需要几层：按最冷那天判断。"""
    coldest = min(w["feel_min"] for w in days_weather)
    return list(C.TEMPERATURE_BANDS[REC.band_of(coldest)]["required"])


def _alert_gap_warmth(wardrobe, formality, days_weather):
    """最冷那天，衣橱里最厚的衣服够不够。"""
    out = []
    coldest = min(w["feel_min"] for w in days_weather)
    need = REC._lerp(C.OUTER_CLO_KNOTS, coldest)
    outers = [i for i in wardrobe if i.get("slot") == "outer"]
    if need <= 0.05 or not outers:
        return out
    thickest = max(outers, key=lambda i: i.get("clo", 0))
    if thickest.get("clo", 0) < need * 0.8:
        out.append(
            f"最冷那天体感 {coldest:.0f}℃，需要约 {need:.2f} clo 的外层，"
            f"你衣橱里最厚的{thickest['name']}只有 {thickest.get('clo', 0):.2f}，"
            f"建议再带一件更厚的，或在当地买。")
    return out


def _alert_clothing(wardrobe, days, laundry, packed_by_slot, span=None):
    """衣橱够不够撑完这趟。"""
    out = []
    for slot in ("base", "bottom"):
        want = quota_of(slot, days, laundry, span)
        have = len([i for i in wardrobe if i.get("slot") == slot])
        picked = len(packed_by_slot.get(slot) or [])
        u = _unit(slot)
        if have == 0:
            out.append(f"衣橱里一件{SLOT_NAME[slot]}都没有，这趟没法成行。")
        elif picked < want:
            msg = (f"{days} 天行程建议带 {want} {u}{SLOT_NAME[slot]}，"
                   f"符合这次场合的只有 {picked} {u}")
            if picked * 2 <= want:
                msg += "，这是明显短板，途中要反复洗，建议出发前补两件。"
            else:
                msg += "，途中要洗一次。"
            out.append(msg)
    return out


def _alert_weather(days_weather):
    """降水、大风、暴晒、温差。"""
    out = []
    rainy = [_short_date(w["date"]) for w in days_weather if (w["daily"]["pop_max"] or 0) >= 50]
    if rainy:
        out.append(f"{'、'.join(rainy)} 降水概率超过 50%，带伞，外层优先防水面料。")
    windy = [_short_date(w["date"]) for w in days_weather if (w["daily"]["wind_max"] or 0) >= 30]
    if windy:
        out.append(f"{'、'.join(windy)} 风力较大，避免穿容易被吹起的宽松外套。")
    uv = max((w["daily"]["uv_max"] or 0) for w in days_weather)
    if uv >= 8:
        out.append(f"行程中紫外线指数最高 {uv:.0f}，带帽子和防晒。")
    snow = [w for w in days_weather if (w["daily"]["code"] or 0) in (71, 73, 75, 77, 85, 86)]
    if snow:
        out.append(f"{'、'.join(_short_date(w['date']) for w in snow)} 有降雪，"
                   f"鞋要防滑，最好多带一双袜子。")
    return out


def _advice(packing, days_weather, n, laundry):
    """可复用、叠穿、行李量这类人话建议。"""
    out = []
    for p in packing:
        if p["slot"] in ("outer", "shoes") and p["count"] <= 2 and n >= 3:
            names = "、".join(i["name"] for i in p["items"])
            out.append(f"{p['slot_name']}只带 {p['count']} {p['unit']}（{names}），"
                       f"整个行程靠它轮换——{QUOTA_NOTE.get(p['slot'], '')}。")

    # 内层和下装：算法每天推同一件很正常，但贴身衣物必须换，这两件事得说清楚
    for slot in ("base", "bottom"):
        grp = next((p for p in packing if p["slot"] == slot), None)
        if not grp:
            continue
        prim = [i for i in grp["items"] if not i.get("spare")]
        main = prim[0] if prim else None
        if slot == "base" and grp["count"] > 1 and main and main["used_days"] >= n:
            out.append(f"方案里每天都是{main['name']}，但贴身层必须每天换，"
                       f"所以带够 {grp['count']} 件同类替换，搭配方式不变。")
        elif slot == "bottom" and len(prim) > 1:
            out.append(f"下装带 {len(prim)}{grp['unit']}轮换穿（"
                       + "、".join(i["name"] for i in prim) + f"），{QUOTA_NOTE['bottom']}。")

    spares = [i for p in packing for i in p["items"] if i.get("spare")]
    if spares:
        head = "、".join(i["name"] for i in spares[:3])
        out.append(f"另 {len(spares)} 件是换洗备用（{head}），不参与每日搭配，别忘了塞箱子。")

    span = max(w["feel_max"] for w in days_weather) - min(w["feel_min"] for w in days_weather)
    if span >= 12:
        mid = next((p for p in packing if p["slot"] == "mid"), None)
        outer = next((p for p in packing if p["slot"] == "outer"), None)
        two_tier = (mid and mid["count"] >= 2) or (outer and outer["count"] >= 2)
        if two_tier:
            out.append(f"行程内体感跨度 {span:.0f}℃，薄厚两档都带了，冷热都能调。")
        else:
            out.append(f"行程内体感跨度 {span:.0f}℃，但你只带了一层中层一件外套——"
                       f"靠叠穿调节：中层能脱、外套能敞开，进出室内外别硬扛。")
    if not laundry and n >= 4:
        out.append(f"按不洗衣准备，{n} 天要带足内层和下装，行李会比较满。")

    total = sum(p["count"] for p in packing)
    if total <= 8:
        out.append(f"全套 {total} 件，一个登机箱足够，不用托运。")
    elif total <= 14:
        out.append(f"全套 {total} 件，20 寸箱加一个随身包够用。")
    else:
        out.append(f"全套 {total} 件，需要 24 寸箱；想减量就把内层改成途中洗。")
    return out


# ---------------------------------------------------------------- 便捷封装

def plan_for_city(wardrobe, lat, lon, start_date, end_date,
                  purpose="出差", laundry=True, luck_travel=None):
    """按城市坐标拉多日天气后直接出方案。"""
    from . import weather as WX
    days_weather = WX.fetch_days(lat, lon, start_date, end_date)
    formality, _, tag, _ = CTX.classify_event(purpose)
    res = plan_trip(wardrobe, days_weather, formality=formality,
                    purpose=purpose, laundry=laundry, luck_travel=luck_travel)
    res["start_date"] = start_date
    res["end_date"] = end_date
    res["purpose_tag"] = tag
    return res
