# -*- coding: utf-8 -*-
"""分时段换装：把一天按日程切成若干段，每段用该时段的真实天气与场合独立推荐。

解决的问题：上午见客户要正装、下午坐工位、傍晚去健身，
一天只给一套衣服显然不够；但也不能傻乎乎地给三套互不相关的方案。

做法：
  1. 按日程事件切片，合并"可以穿同一套"的相邻事件
  2. 每段从逐小时预报里取该时间窗的体感温度/降水/风/紫外
  3. 每段独立跑一次推荐引擎
  4. 与前一段比对，算出真正需要换/增减的层，生成换装提示
"""
from . import config as C
from . import context as CTX
from . import recommend as REC

SLOT_NAME = C.SLOT_NAME


# ---------------------------------------------------------------- 时间工具

def _hour(s, default=9.0):
    """'09:30' → 9.5；解析失败给默认值。"""
    try:
        h, m = str(s).split(":")[:2]
        return int(h) + int(m) / 60.0
    except Exception:
        return default


def _hhmm(h):
    h = max(0.0, min(23.9, h))
    return f"{int(h):02d}:{int(round((h - int(h)) * 60)):02d}"


# ---------------------------------------------------------------- 分段

def build_segments(events, weather):
    """日程事件 → 可穿衣的时段列表。

    合并规则：相邻事件如果都是非运动，且正式度相差 ≤1 档、间隔 ≤3 小时，
    视为"穿同一套就行"，合并成一段（正式度取该段最高值）。
    """
    parsed = []
    for ev in events or []:
        lvl, sport, tag, _ = CTX.classify_event(ev.get("title", ""), ev.get("note", ""))
        start = _hour(ev.get("start"), 9.0)
        end = _hour(ev.get("end"), start + 1.5)
        if end <= start:
            end = start + 1.5
        parsed.append({
            "title": ev.get("title", ""),
            "start": start, "end": end,
            "formality": lvl, "sport": sport, "tag": tag,
        })
    parsed.sort(key=lambda x: x["start"])

    if not parsed:
        return [{
            "start": 8.0, "end": 20.0, "formality": 2, "sport": False,
            "tag": C.FORMALITY_LABELS[2], "events": [],
            "label": "全天", "default": True,
        }]

    groups = []
    for ev in parsed:
        if groups:
            g = groups[-1]
            compatible = (
                g["sport"] == ev["sport"]
                and (ev["start"] - g["end"]) <= 3.0
                and (abs(g["formality"] - ev["formality"]) <= 1 or g["sport"])
            )
            if compatible:
                g["end"] = max(g["end"], ev["end"])
                g["formality"] = max(g["formality"], ev["formality"])
                g["events"].append(ev)
                # 合并后正式度可能升高，标签必须跟着更新
                g["tag"] = "运动" if g["sport"] else C.FORMALITY_LABELS[g["formality"]]
                continue
        groups.append({
            "start": ev["start"], "end": ev["end"],
            "formality": ev["formality"], "sport": ev["sport"], "tag": ev["tag"],
            "events": [ev], "default": False,
        })

    # 日程可以重叠：9:00–12:00 考试 ＋ 11:00–12:00 客户沟通，11 点这一小时
    # 同时属于两段。按开始时间排好后，前一段必须在后一段开始时收尾，
    # 否则用户拿着时间轴不知道 11 点到底穿哪套；被完全覆盖的短段直接丢掉。
    keep = []
    for g in groups:
        while keep and keep[-1]["end"] > g["start"]:
            keep[-1]["end"] = g["start"]
            if keep[-1]["end"] - keep[-1]["start"] >= 0.25:
                break
            keep.pop()
        keep.append(g)
    groups = keep

    for g in groups:
        g["label"] = f"{_hhmm(g['start'])}–{_hhmm(g['end'])}"
        g["events_title"] = [e["title"] for e in g["events"]]
    return groups


# ---------------------------------------------------------------- 时段天气

def window_weather(weather, start_h, end_h):
    """从逐小时预报里切出该时段的天气，作为该段推荐的输入。"""
    hours = [h for h in weather.get("hours", []) if start_h - 1 <= h["hour"] <= end_h + 1]
    if not hours:
        return weather

    feels = [h["apparent"] for h in hours]
    pops = [h["pop"] or 0 for h in hours]
    winds = [h["wind"] or 0 for h in hours]
    uvs = [h["uv"] or 0 for h in hours]

    w = dict(weather)
    w["feel_min"] = min(feels)
    w["feel_max"] = max(feels)
    w["feel_mean"] = round(sum(feels) / len(feels), 1)
    d = dict(weather["daily"])
    d["pop_max"] = max(pops)
    d["wind_max"] = max(winds)
    d["uv_max"] = max(uvs)
    w["daily"] = d
    w["window_hours"] = [h["hour"] for h in hours]
    return w


def segment_context(seg, w):
    """构造该段的穿衣情境。"""
    ctx = {
        "formality": seg["formality"],
        "formality_label": "运动" if seg["sport"] else C.FORMALITY_LABELS[seg["formality"]],
        "has_sport": seg["sport"],
        "indoor_ratio": 0.5,
        "events": [{"title": t, "start": "", "end": "", "formality": seg["formality"],
                    "sport": seg["sport"], "tag": seg["tag"], "matched": []}
                   for t in seg.get("events_title", [])],
        "advice": [],
    }
    ctx["slot_temp"] = {
        "base": w["feel_max"],
        "mid": w["feel_mean"],
        "outer": w["feel_min"],
        "bottom": w["feel_mean"],
        "shoes": w["feel_mean"],
    }
    return ctx


# ---------------------------------------------------------------- 差异比对

def diff_outfits(prev, cur):
    """比较两套方案，返回需要换掉/新增/脱掉的槽位。"""
    if prev is None:
        return []
    a = {o["slot"]: o["item"]["id"] for o in prev["outfit"]}
    b = {o["slot"]: o["item"]["id"] for o in cur["outfit"]}
    name_b = {o["slot"]: o["item"]["name"] for o in cur["outfit"]}
    changes = []
    for slot in C.SLOT_ORDER:
        if a.get(slot) == b.get(slot):
            continue
        if b.get(slot) and not a.get(slot):
            changes.append({"slot": slot, "slot_name": SLOT_NAME[slot],
                            "action": "加上", "item": name_b[slot]})
        elif a.get(slot) and not b.get(slot):
            changes.append({"slot": slot, "slot_name": SLOT_NAME[slot],
                            "action": "脱掉", "item": None})
        else:
            changes.append({"slot": slot, "slot_name": SLOT_NAME[slot],
                            "action": "换成", "item": name_b[slot]})
    return changes


def change_advice(seg, prev_seg, changes):
    """判断这段相对上一段是否真的需要换装，并生成人话提示。"""
    if prev_seg is None:
        return True, ["这是今天的第一套，按这个穿出门。"]

    reasons = []
    need = False

    if seg["sport"] != prev_seg["sport"]:
        if seg["sport"]:
            reasons.append("接下来有运动安排，整套换成运动装备")
        else:
            reasons.append("运动结束，换回日常穿着")
        need = True

    df = seg["formality"] - prev_seg["formality"]
    if df >= 2:
        reasons.append(f"场合从「{prev_seg['tag']}」升到「{seg['tag']}」，需要更正式")
        need = True
    elif df <= -2 and not seg["sport"]:
        reasons.append("后面没有正式场合了，可以放松穿着")

    dt = seg["weather"]["feel_mean"] - prev_seg["weather"]["feel_mean"]
    if dt <= -6:
        reasons.append(f"体感从 {prev_seg['weather']['feel_mean']:.0f}℃ 降到 "
                       f"{seg['weather']['feel_mean']:.0f}℃，要加一层")
        need = True
    elif dt >= 6:
        reasons.append(f"体感回升到 {seg['weather']['feel_mean']:.0f}℃，可以脱掉外层")
        need = True

    p0 = prev_seg["weather"]["pop_max"] or 0
    p1 = seg["weather"]["pop_max"] or 0
    if p0 < 40 <= p1:
        reasons.append(f"这个时段降水概率升到 {p1}%，带伞或换防水外套")
        need = True

    if not changes:
        reasons.append("和上一套一致，不用换")
        need = False

    if not reasons:
        reasons.append("场合与温度变化不大")
    return need, reasons


# ---------------------------------------------------------------- 主入口

def same_outfit(a, b):
    """两套方案是不是同一身衣服（只比核心五层，配饰换了不算换装）。"""
    if not a or not b:
        return False
    def sig(r):
        return {o["slot"]: (o.get("item") or {}).get("id")
                for o in (r.get("outfit") or []) if o.get("slot") in REC.CORE_SLOTS}
    return sig(a) == sig(b)


def plan_day(wardrobe, events, weather, top_n=1, day_ctx=None):
    """生成全天的分时段穿搭计划。

    day_ctx: 全天级的上下文（命理层的文昌/桃花等）。这些规则「一天之内都成立」，
    必须跟着每一段走——否则主方案写「配饰最多一件」，分时段方案照样给两件。
    """
    segs = build_segments(events, weather)
    out = []
    prev = None
    gaps_seen = []
    for seg in segs:
        w = window_weather(weather, seg["start"], seg["end"])
        ctx = segment_context(seg, w)
        for key in ("study", "social", "travel"):
            if day_ctx and day_ctx.get(key):
                ctx[key] = day_ctx[key]
        if seg["sport"]:
            # 运动段：直接用运动装备清单，不做正式度推荐
            picks = REC.sport_outfit(wardrobe, ctx, w)
            outfit = [{"slot": c["slot"], "slot_name": SLOT_NAME[c["slot"]],
                       "item": c["item"], "reason": "运动专用，速干透气"} for c in picks]
            rec = {"rank": 1, "score": None, "parts": None,
                   "outfit": outfit, "label": "运动装备"}
        else:
            recs, _, rex = REC.recommend(wardrobe, ctx, w, top_n=top_n)
            if not recs:
                gaps_seen = rex.get("gaps") or gaps_seen
                continue
            rec = recs[0]

        item = {
            "label": seg["label"],
            "time_start": _hhmm(seg["start"]),
            "time_end": _hhmm(seg["end"]),
            "occasion": seg["tag"],
            "formality": seg["formality"],
            "sport": seg["sport"],
            "events": seg.get("events_title", []),
            "band": C.TEMPERATURE_BANDS[REC.band_of(w["feel_mean"])]["label"],
            "weather": {
                "feel_min": w["feel_min"], "feel_max": w["feel_max"],
                "feel_mean": w["feel_mean"],
                "pop_max": w["daily"]["pop_max"],
                "wind_max": w["daily"]["wind_max"],
                "uv_max": w["daily"]["uv_max"],
            },
            "recommendation": rec,
        }
        item["_w"] = w
        item["_seg"] = seg
        out.append(item)

    # 逐段比对。
    # 关键：判定"不用换"时直接沿用上一套，而不是展示一套不同的衣服——
    # 否则场合/温度几乎相同的两段会因为打分的微小差异选出完全不同的单品，
    # 用户会被要求莫名其妙地换掉全身。
    prev = None
    for item in out:
        changes = diff_outfits(prev["recommendation"] if prev else None,
                               item["recommendation"])
        seg_meta = {
            "sport": item["sport"], "formality": item["formality"],
            "tag": item["occasion"],
        }
        prev_meta = ({"sport": prev["sport"], "formality": prev["formality"],
                      "tag": prev["occasion"]} if prev else None)
        need, reasons = change_advice(
            {"weather": item["weather"], **seg_meta},
            {"weather": prev["weather"], **prev_meta} if prev else None,
            changes)

        if prev and not need:
            item["recommendation"] = prev["recommendation"]
            item["changes"] = []
            item["change_needed"] = False
            if prev["formality"] - item["formality"] >= 2:
                reason = ("后面的场合更轻松了，但沿用它完全没问题，不需要专门换一套。")
            else:
                reason = "场合与温度变化不大，沿用上一套，不用换。"
            item["change_reasons"] = [reason]
        else:
            item["changes"] = changes
            item["change_needed"] = need if prev else False
            item["change_reasons"] = reasons
        prev = item

    # 相邻两段衣服完全一样就并成一段。
    # 「11:00 见客户」和「14:00 坐工位」其实是同一身，展示成两张卡会让人
    # 以为要回家换一次衣服。只有明确标了 change_needed 的段才保留独立。
    merged = []
    for item in out:
        if (merged
                and not item.get("change_needed")
                and merged[-1]["sport"] == item["sport"]
                and same_outfit(merged[-1]["recommendation"], item["recommendation"])):
            prev = merged[-1]
            prev["time_end"] = item["time_end"]
            prev["label"] = f"{prev['time_start']}–{prev['time_end']}"
            prev["events"] = list(dict.fromkeys(prev["events"] + item["events"]))
            # 段落变长后，场合按其中更高的那一档说，别把正式的一小时说成办公
            if item["formality"] > prev["formality"]:
                prev["formality"] = item["formality"]
                prev["occasion"] = item["occasion"]
            continue
        merged.append(item)
    out = merged

    # 清理内部字段
    for item in out:
        item.pop("_w", None)
        item.pop("_seg", None)

    # 全天级提示：找出温差最大、是否需要带备用外层
    day_advice = []
    if len(out) > 1:
        tmin = min(i["weather"]["feel_mean"] for i in out)
        tmax = max(i["weather"]["feel_mean"] for i in out)
        if tmax - tmin >= 8:
            day_advice.append(
                f"全天各时段体感跨度 {tmax - tmin:.0f}℃（{tmin:.0f}~{tmax:.0f}℃），"
                f"出门时带一件可脱的外层，别只按早上的温度穿。")
        if any(i["change_needed"] for i in out):
            day_advice.append("今天有需要换装的时段，详见下方各段提示。")
        first, last = out[0], out[-1]
        drop = first["weather"]["feel_min"] - last["weather"]["feel_min"]
        if drop >= 5:
            day_advice.append(
                f"末段最低体感 {last['weather']['feel_min']:.0f}℃，比早间低 {drop:.0f}℃，"
                f"晚归的话出门时多带一件外层。")
        elif last["weather"]["feel_min"] <= 5:
            day_advice.append(f"末段最低体感仅 {last['weather']['feel_min']:.0f}℃，晚归注意保暖。")

    # 有运动段就必须提醒带替换衣物：上下午是通勤装，不能穿着运动服来回走
    sport_segs = [i for i in out if i.get("sport")]
    if sport_segs:
        s = sport_segs[0]
        day_advice.append(
            f"{s['time_start']} 有运动安排：包里放一套替换衣物（内衣、袜子、毛巾），"
            f"通勤装和运动装分开，别穿着运动服走夜路。")

    # 早晚温差大的日子，鞋袜是最容易漏的一环——皮鞋挡不住地上的凉气
    if out and out[0]["weather"]["feel_min"] <= 3:
        day_advice.append(
            f"最早一段最低体感 {out[0]['weather']['feel_min']:.0f}℃，"
            f"鞋和袜子按深秋的来：厚棉袜或短靴，别穿薄单鞋站风里等车。")
    if not out:
        # 一段都排不出来时，说清楚缺哪一层、该多厚，而不是只说「请补充单品」
        day_advice.append(REC.gaps_note(gaps_seen)
                          or "当前衣橱没有能满足今天温度的组合，请补充单品。")

    return {
        "segments": out,
        "day_advice": day_advice,
        "needs_change": any(i["change_needed"] for i in out),
        "segment_count": len(out),
    }
