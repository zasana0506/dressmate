# -*- coding: utf-8 -*-
"""日程 → 场合情境。判断今天要穿得多正式、要不要跑动、是否基本在室内。"""
import re

from . import config as C
from . import identity as ID


def _identity(profile=None):
    """读穿衣者的性别与年龄。

    profile 传了就用它（测试可以注入隔离的档案），
    没传就读磁盘上的 data/profile.json。读不到就返回空字典（等于不过滤）。
    """
    if profile is None:
        profile = ID.load_profile()
    return {
        "gender": ID.gender_of(profile),
        "age": ID.age_of(profile),
        "profile": profile,
    }


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


def build_context(events, weather=None, profile=None):
    """把一天的日程聚合成一个穿衣情境。

    规则：取当天"最高正式度要求"作为主基调（穿得差一点比穿得太正式好得多），
    同时记录是否有运动项目、是否几乎全程室内（影响是否需要抗造型的外层）。

    profile: 穿衣者档案（出生日期+性别）。不传就读磁盘上的 data/profile.json。
    测试要传隔离的档案，否则会被开发者本机的档案影响——比如档案里写了
    「8 岁」，正式度就被封顶到休闲档，用例里断言的正式度自然对不上。
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
    # 穿衣者身份（性别/年龄）。推荐引擎靠它排除不合适的单品与配件——
    # 领带给女生、皮带给小孩，都是靠这里挡住的。
    ctx["identity"] = _identity(profile)
    who = ctx["identity"].get("gender")
    age = ctx["identity"].get("age")
    if who or age is not None:
        bits = []
        if who:
            bits.append(f"{who}性")
        if age is not None:
            bits.append(f"{age} 岁")
        ctx["advice"].append(
            "已按你的档案（" + "、".join(bits) + "）筛选："
            + ("不给女性配领带这类男士正装配件；" if who == "女" else "")
            + ("不给未成年人配皮带这类成人配件。" if age is not None and age < ID.CHILD_AGE else "")
            + "档案可在「幸运」那栏改。")
    # 年纪小的人正式度要求要往下压一档：小孩不该被推西装通勤
    ceil = ID.formality_ceiling(ctx["identity"])
    if ceil is not None and formality > ceil:
        ctx["formality"] = ceil
        ctx["formality_label"] = C.FORMALITY_LABELS[ceil]
        ctx["formality_capped"] = True
        ctx["advice"].append(
            f"按年龄（{ctx['identity'].get('age')} 岁）把正式度从"
            f"「{C.FORMALITY_LABELS[formality]}」调到"
            f"「{C.FORMALITY_LABELS[ceil]}」。")
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
