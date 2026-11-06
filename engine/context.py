# -*- coding: utf-8 -*-
"""日程 → 场合情境。判断今天要穿得多正式、要不要跑动、是否基本在室内。"""
import re

from . import config as C


def classify_event(title, note=""):
    """单个日程 → (正式度0-4, 是否运动, 标签)。"""
    text = f"{title} {note}".lower()
    level = 0
    matched = []
    for lvl, kws in C.SCENARIO_KEYWORDS:
        for kw in kws:
            if kw.lower() in text:
                if lvl > level:
                    level = lvl
                matched.append(kw)
                break
    sport = any(k.lower() in text for k in C.SPORT_KEYWORDS)
    if sport:
        level = 0
    elif not matched:
        # 有日程但没命中任何关键词时，默认按「常规办公」。
        # 归到 0（居家休闲）会让"整理数据""写文档"这类日常事务被当成睡衣场景。
        level = 2
    tag = C.FORMALITY_LABELS[level]
    if sport:
        tag = "运动"
    return level, sport, tag, sorted(set(matched))


def build_context(events, weather=None):
    """把一天的日程聚合成一个穿衣情境。

    规则：取当天"最高正式度要求"作为主基调（穿得差一点比穿得太正式好得多），
    同时记录是否有运动项目、是否几乎全程室内（影响是否需要抗造型的外层）。
    """
    parsed = []
    for ev in events or []:
        lvl, sport, tag, kw = classify_event(ev.get("title", ""), ev.get("note", ""))
        parsed.append({
            "title": ev.get("title", ""),
            "start": ev.get("start", ""),
            "end": ev.get("end", ""),
            "formality": lvl,
            "sport": sport,
            "tag": tag,
            "matched": kw,
        })

    if parsed:
        formality = max(p["formality"] for p in parsed)
        has_sport = any(p["sport"] for p in parsed)
    else:
        formality = 2
        has_sport = False

    outdoor = sum(1 for p in parsed if not p.get("indoor", False))
    indoor_ratio = 1.0 - (outdoor / len(parsed)) if parsed else 0.5

    advice = []
    if not parsed:
        advice.append("今天没有日程记录，按常规办公标准推荐。")
    if has_sport:
        advice.append("检测到运动项目：主推荐为日常通勤穿搭，另附一套运动装备清单。")
    if indoor_ratio > 0.8 and parsed:
        advice.append("今天基本在室内，外层可以选透气、耐坐、不易皱的面料。")
    if formality >= 3:
        advice.append("有正式度要求较高的安排，衬衫与挺括外套优先。")
    elif formality <= 1:
        advice.append("没有正式场合，可放心穿舒适休闲款。")

    ctx = {
        "formality": formality,
        "formality_label": C.FORMALITY_LABELS[formality],
        "has_sport": has_sport,
        "indoor_ratio": round(indoor_ratio, 2),
        "events": parsed,
        "advice": advice,
    }
    if weather:
        ctx["slot_temp"] = {
            "base": weather["feel_max"],
            "mid": weather["feel_mean"],
            "outer": weather["feel_min"],
            "bottom": weather["feel_mean"],
            "shoes": weather["feel_mean"],
        }
    return ctx


def infer_indoor(title):
    """粗判日程是否在室内（影响抗造型的权重，暂时只作展示用）。"""
    return bool(re.search(r"室|内|办公室|家|楼|工位|工位区", title or ""))
