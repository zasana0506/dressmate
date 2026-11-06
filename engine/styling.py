# -*- coding: utf-8 -*-
"""穿搭铁律层：把搭配师的自检清单落成可执行的规则。

规则来源（三个技能的方法论，不是泛泛的经验）：
- wardrobe-buddy「穿搭搭子」：只用已有单品、每套给取舍、天气要核验；
- womenswear-styling / menswear-styling：15 条色彩铁律 + 得体铁律，
  以及「结论 / 整套 / 这身的坑」三段式输出。

为什么单开一层：`harmony_score` 判的是「这几个颜色放一起协调吗」，
回答不了搭配师真正在查的问题——整身几个色系、鞋有没有单独跳出来、
西裤能不能配运动鞋、深褐配黑会不会互相吞掉。这些是全局约束，不是相邻关系。

这里只做「扣分 + 提醒」，不做硬门。硬门会让衣橱不全的人直接拿不到方案，
而这类规矩的代价本来就该是「不推荐」，不是「没有」。
"""
from . import config as C

# 明度：用来判「上浅下深」和「内外两件套是否卡在中间态」。
# 只给色系一个粗略的明度档，够判方向，不需要精确到 Lab。
BRIGHTNESS = {
    "黑": 0.08, "深灰": 0.22, "灰": 0.50, "浅灰": 0.68, "白": 0.95,
    "米白": 0.88, "米": 0.85, "驼": 0.62, "棕": 0.40, "咖啡": 0.35,
    "卡其": 0.65, "杏": 0.80, "沙": 0.70, "褐": 0.30, "燕麦": 0.78,
    "藏青": 0.18, "深蓝": 0.15, "蓝": 0.50, "浅蓝": 0.72, "天蓝": 0.75,
    "红": 0.40, "酒红": 0.28, "粉": 0.75, "绿": 0.45, "墨绿": 0.20,
    "黄": 0.80, "紫": 0.30, "橙": 0.60,
}

# 抢色：明度都低，放一起互相吞掉（男女装色彩铁律第 14 条）
STEAL_DARK = {"褐", "深褐"}
# 高风险撞色：绿色配红/紫（色彩规则「拿绿色硬配」）
GREEN_RISK = {"红", "紫"}

# 每条规则的扣分权重。加总封顶 1.0，乘 STYLE_WEIGHT 后进总分。
PENALTY = {
    "three_colors": 0.32,      # 一身超过三个色系
    "four_colors": 0.15,       # 再超一个，叠加
    "shoe_jump": 0.20,         # 鞋单独跳一个颜色
    "sneaker_dress_pants": 0.45,   # 运动鞋配西裤
    "sneaker_tailored_outer": 0.35,  # 大衣/西装外套配运动鞋
    "steal_color": 0.15,       # 深褐/深紫配黑
    "green_risk": 0.15,        # 绿配红/紫
    "middle_tone": 0.10,       # 内外两件套卡在中间态
    "tone_up_dark": 0.08,      # 正式场合用上深下浅
    "accessory_pile": 0.10,    # 配饰超过两处
    "shoe_drops_tier": 0.28,   # 鞋掉档：整套正式度被一双鞋拖下来
    "outer_drops_tier": 0.20,  # 外套掉档
}


def brightness(color):
    return BRIGHTNESS.get(C.normalize_color(color), 0.50)


def family(color):
    c = C.normalize_color(color)
    return C.COLOR_FAMILY.get(c, c)


def _pick(chosen, *slots):
    """按槽位优先级取第一件有色的单品。"""
    for slot in slots:
        for c in chosen:
            if c["slot"] == slot:
                it = c["item"]
                if it.get("color"):
                    return it
    return None


def lane(wardrobe):
    """衣橱的语言：有没有裙装，决定跑哪套得体规矩。

    男装铁律管皮带袜子领带，女装铁律管腰线丝袜长度。
    两套不能混跑——对一条西裤讲「露腰线」是废话，对一条裙子讲「领带别同色」是胡说。
    """
    for it in wardrobe:
        if it.get("category") in ("skirt", "dress", "heels", "shoes_heels"):
            return "women"
    return "men"


def audit(chosen, ctx):
    """跑一遍铁律，返回风格分、命中的问题、以及「这身的坑」。

    chosen 是候选组合（含配饰）。返回的 pitfalls 直接给用户看，
    所以每一条都必须指向这身里的具体单件，不能是通用话术。
    """
    # 注意 0 是合法值（居家休闲）：用 or 2 会把 0 吃掉，误判成常规办公
    req = ctx["formality"] if ctx.get("formality") is not None else 2
    req = int(req)
    core = [c for c in chosen if c["slot"] in ("base", "mid", "outer", "bottom", "shoes")]
    issues, pitfalls = [], []

    def hit(code, note, item=None):
        issues.append({"code": code, "delta": PENALTY[code],
                       "item": (item or {}).get("name"), "note": note})
        if note:
            pitfalls.append(note)

    # —— 色系数量：一身有彩色控制在三种以内（黑白灰是无色系，不占名额）
    fams = []
    for c in core:
        raw = C.normalize_color(c["item"].get("color"))
        if raw in C.NEUTRAL_COLORS:
            continue
        f = family(raw)
        if f and f not in fams:
            fams.append(f)
    if len(fams) > 3:
        hit("three_colors", f"整身已经出现 {len(fams)} 个彩色色系（{'、'.join(fams)}），"
                            f"包和袜子请从这几个颜色里挑，别再跳第四个")
        if len(fams) > 4:
            hit("four_colors", "")

    # —— 鞋：不能单独跳出来
    shoe = _pick(chosen, "shoes")
    bottom = _pick(chosen, "bottom")
    outer = _pick(chosen, "outer")
    top = _pick(chosen, "base", "mid")
    if shoe:
        sf = family(shoe.get("color"))
        other = {family(x.get("color")) for x in (top, bottom, outer) if x}
        if sf and sf not in other and sf not in ("黑", "白", "灰") and sf != "棕":
            hit("shoe_jump",
                f"{shoe.get('name')}是整身唯一一处{sf}色，鞋单独跳出来会散；"
                f"换成和下装同色系更稳", shoe)

    # —— 运动鞋不能配西裤、不能配大衣（正式度上下不一致）
    if shoe and shoe.get("category") in ("shoes_sneakers", "running_shoes"):
        bcat = (bottom or {}).get("category") or ""
        if bcat in ("dress_pants", "trousers") or int((bottom or {}).get("formality") or 0) >= 3:
            hit("sneaker_dress_pants",
                f"{shoe.get('name')}配{bottom.get('name')}：正式度上下不一致，"
                f"要么换皮鞋，要么把裤子也降成休闲裤", shoe)
        ocat = (outer or {}).get("category") or ""
        if ocat in ("coat", "blazer") and req >= 2:
            hit("sneaker_tailored_outer",
                f"{outer.get('name')}配{shoe.get('name')}：上半身通勤、下半身像下楼取快递，"
                f"换短靴或皮质板鞋", shoe)

    # —— 抢色：深褐/深紫不与黑同穿
    colors = [C.normalize_color(c["item"].get("color")) for c in core]
    if any(c in STEAL_DARK or (family(c) == "紫" and brightness(c) < 0.4) for c in colors) \
            and "黑" in colors:
        dark = next(c for c in colors
                    if c in STEAL_DARK or (family(c) == "紫" and brightness(c) < 0.4))
        hit("steal_color", f"{dark}配黑，两个颜色明度太近会互相吞掉，"
                           f"把其中一件换成深灰或米色就清爽了")

    # —— 绿色硬配红/紫
    gf = {family(c) for c in colors}
    if "绿" in gf and gf & {f for f in GREEN_RISK}:
        hit("green_risk", "绿色配红/紫属于高风险组合，除非刻意做视觉重点，"
                          "否则其中一件换成咖啡色系")

    # —— 内外两件套：同色系或大反差，中间态最难看
    if top and outer:
        bt, bo = brightness(top.get("color")), brightness(outer.get("color"))
        if family(top.get("color")) != family(outer.get("color")) and abs(bt - bo) < 0.15:
            hit("middle_tone",
                f"{outer.get('name')}和{top.get('name')}颜色有点像又不太像，"
                f"要么穿成同色系，要么拉开明暗")

    # —— 明暗方向：一档正式不用上深下浅
    if top and bottom and req >= 4:
        if brightness(top.get("color")) < brightness(bottom.get("color")):
            hit("tone_up_dark",
                f"正式场合用上深下浅（{top.get('color')}配{bottom.get('color')}）"
                f"会显得不够正式，反过来的方向更稳")

    # —— 配饰不超过两处（搭配师规矩是「重点不超过三处」，引擎只给两件）
    acc = [c for c in chosen if c["slot"] == "accessory"]
    if len(acc) > 2:
        hit("accessory_pile",
            f"配饰已经 {len(acc)} 件，耳饰项链手链别全上，收掉最次要的那件")

    # —— 掉档：鞋和外套最容易拉低整套正式度，两个技能都点名要重点检查
    if req >= 3:
        if shoe and int(shoe.get("formality") or 0) <= req - 2:
            hit("shoe_drops_tier",
                f"整身按「{C.FORMALITY_LABELS.get(req, '')}」配，"
                f"鞋只到「{C.FORMALITY_LABELS.get(int(shoe.get('formality') or 0), '')}」，"
                f"一双鞋就能把整套拽下来", shoe)
        if outer and int(outer.get("formality") or 0) <= req - 3:
            hit("outer_drops_tier",
                f"{outer.get('name')}的正式度撑不起这个场合，"
                f"外套是掉档最明显的第二处", outer)

    used = sum(i["delta"] for i in issues)
    score = max(0.0, 1.0 - used)
    if used == 0:
        verdict = "行"
    elif used <= 0.20:
        verdict = "换一件就行"
    else:
        verdict = "这身将就"

    return {"score": round(score, 3), "verdict": verdict,
            "issues": issues, "pitfalls": pitfalls[:3], "lane": None}


def summarize(audit_result, chosen, ctx):
    """「这身的坑」只写要留神的地方，不写夸奖。

    夸奖会跟警告打架——同一张卡里既说「上深下浅不够正式」又说「上浅下深真省事」，
    用户只会觉得系统在自言自语。要夸的地方已经写进每件单品的理由里了。
    """
    notes = list(audit_result["pitfalls"])
    if len(notes) >= 3:
        return notes[:3]

    # 注意 0 是合法值（居家休闲）：用 or 2 会把 0 吃掉，误判成常规办公
    req = ctx["formality"] if ctx.get("formality") is not None else 2
    req = int(req)
    acc = [c["item"].get("name") for c in chosen if c["slot"] == "accessory"]
    outer = _pick(chosen, "outer")
    mid = _pick(chosen, "mid")
    shoe = _pick(chosen, "shoes")
    bottom = _pick(chosen, "bottom")

    if acc and len(notes) < 3 and (req >= 3 or len(acc) > 1):
        notes.append(f"配饰位已经被{('、'.join(a for a in acc if a))}占住，"
                     f"手表、胸针、袖扣别再往上加")
    if mid and outer and len(notes) < 3 \
            and family(mid.get("color")) == family(outer.get("color")):
        notes.append(f"中层和外层都是{family(mid.get('color'))}色系，"
                     f"层次全靠材质区分，别再添第三个同色")
    if shoe and bottom and len(notes) < 3 \
            and brightness(shoe.get("color")) + 0.35 < brightness(bottom.get("color")):
        notes.append(f"{bottom.get('name')}偏浅、{shoe.get('name')}偏深，脚下会显得压沉；"
                     f"不赶时间就换棕色系那双")
    if not notes:
        notes.append("这身没有需要避讳的地方，出门前把鞋面擦一遍就够了")
    return notes[:3]
