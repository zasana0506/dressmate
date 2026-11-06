# -*- coding: utf-8 -*-
"""紫微斗数「今日幸运穿搭」：把流日盘翻译成颜色与款式建议。

排盘交给 iztro（Node），这里只做两件事：

  1. 取流日命宫的地支与主星
  2. 按五行的传统对应关系翻成颜色和风格

映射依据（都是斗数基础，不是我编的）：

  - 十二地支五行：子亥水、寅卯木、巳午火、申酉金、辰戌丑未土
  - 十四主星五行：紫微天府天梁土、天机贪狼木、太阳廉贞火、
                  武曲七杀金、天同太阴巨门天相破军水
  - 流日四化：化禄星取作点缀色，化忌星取作避开色

**这是传统文化参考，不是科学结论。**
它不该压过保暖和场合——零下十度穿不住薄纱，见客户也不能靠撞色撑场面。
所以幸运色在推荐里只作为一个小权重加分项，改不了保暖和正式度的底线。
"""

import json
import os
import shutil
import subprocess
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ziwei_bridge.mjs")


def _profile_path():
    from . import paths
    return paths.PROFILE_PATH


PROFILE_PATH = _profile_path()

# --- 十二地支 → 五行
BRANCH_ELEMENT = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# --- 十四主星 → 五行
STAR_ELEMENT = {
    "紫微": "土", "天机": "木", "太阳": "火", "武曲": "金", "天同": "水",
    "廉贞": "火", "天府": "土", "太阴": "水", "贪狼": "木", "巨门": "水",
    "天相": "水", "天梁": "土", "七杀": "金", "破军": "水",
}

# --- 五行 → 颜色。family 用衣橱里已有的色系名，才能参与配色打分
ELEMENT_COLORS = {
    "水": {"family": "蓝", "names": ["藏青", "深蓝", "黑"], "desc": "藏青、深蓝、墨黑"},
    "木": {"family": "绿", "names": ["墨绿", "橄榄绿", "青"], "desc": "墨绿、橄榄绿、青灰"},
    "火": {"family": "红", "names": ["酒红", "正红", "藕粉", "紫"], "desc": "酒红、正红、藕粉"},
    "土": {"family": "棕", "names": ["驼色", "卡其", "燕麦", "姜黄"], "desc": "驼色、卡其、燕麦"},
    "金": {"family": "白", "names": ["米白", "纯白", "浅灰", "银"], "desc": "米白、纯白、浅灰"},
}

# --- 十四主星 → 款式气质。斗数里星曜各有性格，这里取其象征义
STAR_STYLE = {
    "紫微": ("挺拔有轮廓", "有肩线的外套、剪裁利落的深色正装，别穿软塌的针织"),
    "天机": ("层次感", "适合叠穿：衬衫加薄马甲，线条干净，带点书卷气"),
    "太阳": ("明朗精神", "亮一点的颜色、干净的发型，别闷在深色里"),
    "武曲": ("硬朗利落", "结构感强的单品，少装饰，配金属表或皮质腰带"),
    "天同": ("柔和舒适", "针织、软质面料，宽松但有腰线，别穿得太板"),
    "廉贞": ("精致收腰", "合身版型加一处小亮色，配饰点到为止"),
    "天府": ("稳重有质感", "好面料比花哨设计重要，米棕大地色最稳"),
    "太阴": ("素雅垂坠", "浅色系、垂感好的长裤或长裙，避免硬挺轮廓"),
    "贪狼": ("有设计感", "可以放开一点：花色、异材质、显眼的配饰"),
    "巨门": ("低调内敛", "深色为主，不抢眼，靠版型和质感撑住"),
    "天相": ("整洁得体", "衬衫是安全牌，条纹或纯色都行，别穿皱的"),
    "天梁": ("端正经典", "经典款最合，避免潮流单品，颜色保守一点"),
    "七杀": ("利落冷峻", "短款外套、冷色系、直线条，别叠太多层"),
    "破军": ("个性破格", "可以撞色或解构，但只留一个亮点，别全身都跳"),
}

# --- 六煞：擎羊陀罗是「刑」，火铃是「急」，空劫是「虚」。
# 落在疾厄宫都表示当天身体容易吃不消，不是吉凶判断，只是"多留一分余地"。
SHA_STARS = ("擎羊", "陀罗", "火星", "铃星", "地空", "地劫")

# --- 桃花：红鸾天喜是正桃花（婚恋、喜事），咸池偏欲，沐浴主风情。
# 只取这几颗，不把贪狼廉贞算进来——它们是主星，出现频率太高，
# 天天标"桃花"等于没标。
PEACH_STARS = ("红鸾", "天喜", "咸池", "沐浴")

# 桃花星只认流日命宫，不扩到三方四正。
# 一开始按三方四正（命/财帛/官禄/迁移）算，结果 14 天里有 7 天都标"桃花"——
# 一半的日子都成立的标签没有信息量，用户看两次就不看了。收到命宫后约 2/12。
PEACH_PALACES = ("命宫",)

# --- 文昌文曲：主文书、考试、科名。
# 文昌走正途（考试、答辩、签约、材料），文曲走口才才艺（面试、汇报、谈判）。
# 这两颗是「六吉」里的文星，但都不主保暖也不主场合，
# 所以只能落在「今天穿得素不素净」这个边缘决定上。
STUDY_STARS = ("文昌", "文曲")

# 和桃花一样只认流日命宫与官禄宫。若按三方四正算，
# 文昌每天必然待在十二宫之一，三分之一的日子都会标「利文书」，标签就废了。
STUDY_PALACES = ("命宫", "官禄")

# 亮度权重：庙旺算真有力，得利算中等，平不陷不主科名（落陷的文星只是块木板）。
STUDY_BRIGHT = {"庙": 2, "旺": 2, "得": 1, "利": 1}

BRIGHTNESS_STRENGTH = {
    "庙": "strong", "旺": "strong", "得": "medium", "利": "medium",
    "平": "medium", "不": "weak", "陷": "weak",
}

STRENGTH_NOTE = {
    "strong": "今天这颗星在旺位，按这个方向穿会更有底气。",
    "medium": "今天这颗星力量中等，作参考就好。",
    "weak": "今天这颗星落陷，风格建议只当点缀，别为它牺牲保暖和场合。",
}


# ---------------------------------------------------------------- 排盘

def iztro_available():
    """排盘依赖是否齐全：Node.js 在，且 iztro 装在能找到的地方。

    只看 node 是不够的 —— CI 的 runner 自带 Node，但没装 iztro，
    于是「有 node 就跑排盘」的测试会真的去调，然后因为找不到
    iztro 而失败。判断条件必须和 Node 侧 loadIztro() 的候选路径一致。
    """
    if not shutil.which("node"):
        return False
    for d in _iztro_candidates():
        if os.path.exists(os.path.join(d, "node_modules", "iztro")):
            return True
    return False


def _iztro_candidates():
    """iztro 可能所在的位置，与 ziwei_bridge.mjs 的 CANDIDATES 保持一致。"""
    env = os.environ.get("ZIWEI_NODE_MODULES")
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    cands = []
    if env:
        cands.append(env)
    if home:
        cands.append(os.path.join(home, ".workbuddy", "skills",
                                  "ziwei-doushu", "scripts"))
        cands.append(os.path.join(home, ".workbuddy", "skills", "ziwei-doushu"))
    # npm 全局安装目录（node -g 的位置）
    npm_root = os.environ.get("NPM_CONFIG_PREFIX")
    if npm_root:
        cands.append(os.path.join(npm_root, "lib", "node_modules"))
    cands.append("/usr/local/lib/node_modules")
    return [c for c in cands if c]


def run_bridge(solar_date, time_index, gender, target_date, timeout=25):
    """调 Node 桥接排盘。失败时返回 ok=False 与可读原因。"""
    payload = json.dumps({
        "solar_date": solar_date,
        "time_index": int(time_index),
        "gender": gender,
        "target_date": target_date,
    }, ensure_ascii=False)
    try:
        proc = subprocess.run(
            ["node", BRIDGE],
            input=payload.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, cwd=BASE_DIR,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "这台机器没有安装 Node.js，紫微排盘无法运行"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "排盘超时，检查网络或 Node 环境"}
    except Exception as exc:
        return {"ok": False, "error": f"排盘调用失败：{exc}"}

    out = (proc.stdout or b"").decode("utf-8", "ignore").strip()
    if not out:
        err = (proc.stderr or b"").decode("utf-8", "ignore").strip()[:200]
        return {"ok": False, "error": f"排盘没有输出（{err or '未知原因'}）"}
    try:
        return json.loads(out)
    except Exception:
        return {"ok": False, "error": "排盘输出无法解析"}


# ---------------------------------------------------------------- 三项延伸判断
#
# 这里只做「今天和穿衣有关的三个决定」：穿多暖、路上顺不顺、要不要见人。
# 刻意不碰吉凶断语——那些既不可验证，也会挤掉保暖和场合这两个真约束。

def _flow_palace(palaces, idx_of, name):
    """流日某宫 → 它落在本命哪一宫（含该宫星曜）。

    流日十二宫是轮转的：流日疾厄宫今天可能落在本命田宅宫上。
    所以先按宫名找回下标，再回本命盘取星曜——这是看流日的标准做法。
    """
    i = idx_of.get(name)
    if i is None or i >= len(palaces):
        return None
    return palaces[i]


def _star_names(palace):
    """某宫所有星曜名（主星 + 辅星 + 杂曜）。

    不含长生/博士/将前/岁前四组十二神：那四组按本命年支固定排布，
    逐日不变，拿来判断"今天"会得出全年恒定的结论，是假的日运。
    """
    if not palace:
        return set()
    names = {s.get("name") for s in palace.get("major") or []}
    names |= {s.get("name") for s in palace.get("minor") or []}
    names |= set(palace.get("adj") or [])
    return {n for n in names if n}


def _main_star(palace):
    major = (palace or {}).get("major") or []
    return major[0] if major else None


def analyze(raw, target_date=""):
    """从排盘结果里取出穿衣用得上的三件事。"""
    flow = (raw.get("flow") or {}).get("daily") or {}
    idx_of = flow.get("index_of") or {}
    palaces = raw.get("palaces") or []
    mutagens = flow.get("mutagen") or []
    ji_star = mutagens[3] if len(mutagens) > 3 else ""
    ke_star = mutagens[2] if len(mutagens) > 2 else ""

    out = {
        "health": {"flag": False, "stars": [], "warmth_bonus": 0.0, "note": ""},
        "travel": {"flag": False, "stars": [], "note": ""},
        "social": {"flag": False, "stars": [], "note": ""},
        "study": {"flag": False, "careful": False, "stars": [], "palace": "",
                  "level": "none", "note": "", "exam_note": "", "checklist": []},
    }
    if not idx_of or not palaces:
        return out

    # ---- 疾厄宫：保暖余量。只加不减，冷天才生效（由 recommend 把关温度）
    hp = _flow_palace(palaces, idx_of, "疾厄")
    if hp:
        names = _star_names(hp)
        sha = [s for s in SHA_STARS if s in names]
        ji_hit = bool(ji_star) and ji_star in names
        main = _main_star(hp)
        weak = bool(main) and main.get("brightness") in ("不", "陷")

        bonus, reasons = 0.0, []
        if sha:
            bonus += 0.05
            reasons.append(f"流日疾厄宫见{'、'.join(sha)}")
        if ji_hit:
            bonus += 0.05
            reasons.append(f"正逢{ji_star}化忌")
        if weak:
            bonus += 0.03
            reasons.append(f"主星{main['name']}落陷")

        out["health"] = {
            "flag": bonus > 0,
            "stars": sha,
            "palace": f"{hp.get('name', '')}宫",
            "branch": hp.get("branch", ""),
            # 上限 0.10 clo ≈ 一件薄针织。再多就是让命理替天气预报做决定了
            "warmth_bonus": round(min(0.10, bonus), 2),
            "note": (f"今天{'，'.join(reasons)}，体感容易偏弱。"
                     f"保暖留一点余量，宁可多带一层。" if bonus > 0 else ""),
        }

    # ---- 迁移宫：出差路上的提示。
    # 只把「见煞」当提醒；天马只作说明，因为天马主奔波但不主不顺，
    # 每次出差都提示"路上小心"等于没提示。
    mp = _flow_palace(palaces, idx_of, "迁移")
    if mp:
        names = _star_names(mp)
        sha = [s for s in SHA_STARS if s in names]
        has_horse = "天马" in names
        if sha:
            # 同一颗煞星，日常和出差的处理完全不同：日常是"留出时间"，出差是"改行李策略"
            note = (f"迁移宫见{'、'.join(sha)}，今天在外容易遇到延误或改道，出门多留点时间。")
            trip_note = (f"迁移宫见{'、'.join(sha)}，路上容易遇到延误或改道。"
                         f"行李尽量随身别托运，再多带一套换洗应急。")
        elif has_horse:
            note = "迁移宫有天马，今天多在外走动，鞋以好走为先。"
            trip_note = "迁移宫有天马，这趟本就多走动，鞋以好走为先。"
        else:
            note = trip_note = ""
        out["travel"] = {
            "flag": bool(sha),
            "horse": has_horse,
            "stars": sha,
            "palace": f"{mp.get('name', '')}宫",
            "branch": mp.get("branch", ""),
            "note": note,
            "trip_note": trip_note,
        }

    # ---- 桃花：只管「今天值不值得在打扮上花点心思」，不改正式度。
    # 正式度由日程决定，命理插一层必然打架。
    hits, where = [], ""
    for pname in PEACH_PALACES:
        p = _flow_palace(palaces, idx_of, pname)
        if not p:
            continue
        names = _star_names(p)
        # 沐浴在长生十二神里，是"桃花"的传统位置之一，不在星曜列表里
        found = [s for s in PEACH_STARS if s in names or s == p.get("changsheng12")]
        if found:
            hits.extend(found)
            where = where or pname
    hits = sorted(set(hits))
    if hits:
        out["social"] = {
            "flag": True,
            "stars": hits,
            "palace": where,
            "note": (f"流日{where}见{'、'.join(hits)}，今天人气顺。"
                     f"要是有见人或约会的场合，可以穿得有点心思——"
                     f"配饰挑一件有存在感的就够，不必更正式。"),
        }

    # ---- 文昌文曲：文书与考试。
    # 落点只看「今天要不要把细节做到位」，不改正式度——
    # 面试该穿多正式由日程定，文星插一层说「再正式一档」必然和日程打架。
    found = []          # [(星名, 亮度权重, 宫名)]
    for pname in STUDY_PALACES:
        p = _flow_palace(palaces, idx_of, pname)
        if not p:
            continue
        for s in p.get("minor") or []:
            nm = s.get("name")
            if nm in STUDY_STARS:
                found.append((nm, STUDY_BRIGHT.get(s.get("brightness") or "", 0), pname))

    strong = [(n, lv, pl) for n, lv, pl in found if lv > 0]
    hit_names = sorted({n for n, _, _ in strong})
    # 化忌落在文昌/文曲本体上（辛日文昌化忌、己日文曲化忌），且就在命宫或官禄宫：
    # 这不是「不宜考试」，而是「文书契约容易出疏漏」，提示反复核对即可。
    careful = bool(found) and ji_star in {n for n, _, _ in found}
    ke_hit = bool(hit_names) and ke_star in hit_names

    if hit_names or careful:
        place = next((pl for n, lv, pl in found if lv > 0), found[0][2])
        # iztro 的宫名已经带「宫」的是命宫，其余（官禄）要补上，否则读起来是"流日官禄见文昌"
        place = place if place.endswith("宫") else place + "宫"
        stars = hit_names or sorted({n for n, _, _ in found})
        best = max((lv for _, lv, _ in strong), default=0)
        level = "strong" if (best >= 2 or ke_hit) else ("medium" if hit_names else "careful")

        note, exam_note, checklist = "", "", []
        if hit_names:
            bright_txt = "庙旺" if best >= 2 else "得地"
            note = f"流日{place}见{'、'.join(hit_names)}（{bright_txt}），今天脑子清、条理顺"
            if ke_hit:
                note += f"；{ke_star}正好化科，科名之气最正"
            note += "。"
            if "文昌" in hit_names:
                note += "有要交的材料、要签的字，趁今天办。"
            if "文曲" in hit_names:
                note += "文曲主口才，有要开口的场合可以主动一点。"
            note += ("穿着上把细节做足就够：纯色、无花纹、领口平整、鞋面干净，"
                     "配饰一件收手——文星的日子，衣服不该抢话。")
            exam_note = (f"今天有考试／面试一类的安排，而流日{place}正好见"
                         f"{'、'.join(hit_names)}。这种日子衣服不该抢戏："
                         f"纯色下装、领口平整、鞋面擦一遍、配饰最多一件，"
                         f"提前十分钟出门，别把状态耗在路上。")
            checklist = ["证件、准考证、笔放外层口袋，出门前摸一遍",
                         "鞋面擦干净，鞋带、袖口别松着",
                         "配饰只留一件，别戴会响的"]
        if careful:
            cx = (f"流日{place}的{ji_star}逢化忌，文书、契约、邮件这类东西今天容易出疏漏。"
                  f"出门前把证件、钥匙、要签的字再核一遍；衣服别穿没上过脚的新鞋，"
                  f"没把握的搭配今天都别试。")
            note = (note + cx) if note else cx
            if not exam_note:
                exam_note = cx

        out["study"] = {
            "flag": bool(hit_names),
            "careful": careful,
            "stars": stars,
            "palace": place,
            "level": level,
            "note": note,
            "exam_note": exam_note,
            "checklist": checklist if hit_names else [],
        }
    return out


# ---------------------------------------------------------------- 翻译

def translate(raw, target_date):
    """排盘结果 → 幸运色与款式建议。"""
    if not raw.get("ok"):
        return {"ok": False, "error": raw.get("error", "排盘失败")}

    daily = raw.get("daily") or {}
    branch = daily.get("palace_branch") or daily.get("branch") or ""
    day_element = BRANCH_ELEMENT.get(branch, "土")

    # 流日命宫无主星时借对宫，这是斗数的常规做法
    stars = daily.get("soul_stars") or []
    borrowed = False
    if not stars:
        stars = daily.get("opposite_stars") or []
        borrowed = bool(stars)
    star = stars[0] if stars else None
    star_name = star["name"] if star else ""
    brightness = star.get("brightness", "") if star else ""
    star_element = STAR_ELEMENT.get(star_name, day_element)

    # 四化：禄作点缀，忌作避讳
    mutagens = daily.get("mutagen") or []
    lu_star = mutagens[0] if len(mutagens) > 0 else ""
    ji_star = mutagens[3] if len(mutagens) > 3 else ""

    accent_el = STAR_ELEMENT.get(lu_star, "") if lu_star else ""
    avoid_el = STAR_ELEMENT.get(ji_star, "") if ji_star else ""

    # 主星五行正好撞上化忌时，会出现「主色」和「避讳色」是同一个颜色的荒谬建议。
    # 斗数里讲取用反耗，所以改取化禄的方向作主色，别让用户对着两条相反的建议发呆。
    main_el = star_element
    conflict_note = ""
    if avoid_el and avoid_el == main_el:
        if accent_el and accent_el != main_el:
            main_el, accent_el = accent_el, ""
            conflict_note = (f"今天{ji_star}化忌正落在主星的{star_element}行上，"
                             f"依斗数取用反耗，改走{lu_star}化禄的方向。")
        else:
            avoid_el = ""
            conflict_note = "今天主星五行既旺又带忌，用色收敛、小面积即可。"
    if accent_el and accent_el == main_el:
        accent_el = ""

    main = ELEMENT_COLORS.get(main_el) or ELEMENT_COLORS["土"]
    accent = ELEMENT_COLORS.get(accent_el, {})
    avoid = ELEMENT_COLORS.get(avoid_el, {})

    style_name, style_tip = STAR_STYLE.get(star_name, ("简约得体", "按场合穿，不必刻意"))

    strength = BRIGHTNESS_STRENGTH.get(brightness, "medium")

    tips = []
    if conflict_note:
        tips.append(conflict_note)
        tips.append(f"所以主色走{main['desc']}。")
    else:
        tips.append(f"主色走{main['desc']}——今天流日命宫落{branch}，{main_el}行。")
    if accent and accent.get("desc"):
        tips.append(f"配饰或内搭点一点{accent['desc']}，今天是{lu_star}化禄。")
    if avoid and avoid.get("desc"):
        tips.append(f"整套避开{avoid['desc']}，今天是{ji_star}化忌。")
    tips.append(f"款式偏{style_name}——{style_tip}。")
    if borrowed:
        tips.append("今天流日命宫没有主星，借对宫来看，参考价值会弱一些。")
    tips.append(STRENGTH_NOTE.get(strength, ""))

    # 疾厄/迁移/桃花/文书的提示不并进 tips：
    # 它们在「和穿衣服有关的四件事」里各有单独一条，
    # 再塞进 tips 会让同一句话说两遍，页面越加越长。
    extra = analyze(raw, target_date)

    res = {
        "ok": True,
        "date": target_date,
        "lunar_date": raw.get("lunar_date", ""),
        "day_ganzhi": f"{daily.get('stem', '')}{branch}",
        "day_element": day_element,
        "star": star_name,
        "star_element": star_element,
        "brightness": brightness,
        "borrowed": borrowed,
        "strength": strength,
        "lucky_colors": main["names"],
        "lucky_desc": main["desc"],
        "color_family": main["family"],
        "accent_colors": accent.get("names", []),
        "accent_desc": accent.get("desc", ""),
        "accent_star": lu_star,
        "avoid_colors": avoid.get("names", []),
        "avoid_desc": avoid.get("desc", ""),
        "avoid_star": ji_star,
        "style": style_name,
        "style_tip": style_tip,
        "tips": [t for t in tips if t],
        "soul_star": raw.get("soul", ""),
        "five_elements_class": raw.get("five_elements_class", ""),
        "disclaimer": "命理内容属传统文化参考，不作决策依据；保暖和场合永远优先。",
    }
    res.update(extra)
    return res


_CACHE = {}


def daily_luck(profile, target_date=None, use_cache=True):
    """按用户生辰算今天的幸运穿搭。

    排盘要起一次 Node 进程（约 1 秒），而推荐页每次刷新都会问一次，
    所以按「生辰 + 目标日」缓存，同一天只排一次盘。
    """
    if not profile or not profile.get("solar_date"):
        return {"ok": False, "error": "还没有设置出生信息", "need_profile": True}
    target_date = target_date or datetime.date.today().isoformat()
    key = (profile.get("solar_date"), profile.get("time_index"),
           profile.get("gender"), target_date)
    if use_cache and key in _CACHE:
        return _CACHE[key]
    raw = run_bridge(
        profile["solar_date"],
        profile.get("time_index", 6),
        profile.get("gender", "男"),
        target_date,
    )
    res = translate(raw, target_date)
    res["profile"] = {k: profile.get(k) for k in ("solar_date", "time_index", "gender")}
    if res.get("ok"):
        _CACHE[key] = res
    return res


# ---------------------------------------------------------------- 生辰存储

def load_profile():
    if not os.path.exists(PROFILE_PATH):
        return {}
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_profile(data):
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


TIME_OPTIONS = [
    (0, "早子时 00:00–01:00"), (1, "丑时 01:00–03:00"), (2, "寅时 03:00–05:00"),
    (3, "卯时 05:00–07:00"), (4, "辰时 07:00–09:00"), (5, "巳时 09:00–11:00"),
    (6, "午时 11:00–13:00"), (7, "未时 13:00–15:00"), (8, "申时 15:00–17:00"),
    (9, "酉时 17:00–19:00"), (10, "戌时 19:00–21:00"), (11, "亥时 21:00–23:00"),
    (12, "晚子时 23:00–24:00"),
]
