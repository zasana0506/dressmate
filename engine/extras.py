# -*- coding: utf-8 -*-
"""配件收口层：皮带、袜子、包、领带、丝袜——衣橱里最常缺、却决定「整不整」的几件。

为什么单独一层，不塞进候选池
------------------------------
这几件的保暖值约等于 0，塞进 beam 搜索只会白占候选位；
它们也不能独立选择：皮带只能跟皮鞋同色，袜子只能跟裤子走，
领带由衬衫和外层决定。把它们当独立变量去搜，就是在搜一个没有自由度的东西。

搭配师的做法是反过来的：先定主体，再按主体「收口」——
皮鞋是黑的，皮带就该是黑的；裤子是深灰的，袜子就得比裤子更深或同色。
所以这一层只做两件事：

1. **反推**：给定这身衣服，算出该配什么颜色 / 什么长度，从衣橱里挑最接近的那件；
2. **校验**：衣橱里真有这件时，判它跟主体的色系关系对不对。

衣橱里没有时，不判违规、不扣分——因为「没有」不是穿错，
是还没买。这时输出的是「还差什么」，不是「你错了」。

这两件事以前都做不了，所以「皮带与皮鞋同色」「深色西装不配白袜」
「领带尖落在皮带扣」这几条只能写在文案里当提醒。现在能落到具体单品上。
"""
from . import config as C
from .styling import brightness, family
from .styling import lane as _style_lane

# --- 角色词表：靠品名判，顺序即优先级（「连裤袜」必须先于「袜」）---
# 注意单字和双字的子串陷阱：「翻领针织」会把「领针」命中，
# 「飞织袜子男鞋」会把「袜」命中——所以判定前先卡槽位（见 role_of）。
ROLE_WORDS = (
    ("hosiery", ("连裤袜", "丝袜", "裤袜", "打底袜", "光腿神器")),
    ("tie",     ("领带", "领结", "波洛领", "领带夹")),
    ("belt",    ("皮带", "腰带", "腰封")),
    ("sock",    ("中筒袜", "短袜", "船袜", "羊毛袜", "棉袜", "袜")),
    ("bag",     ("背包", "双肩包", "单肩包", "斜挎包", "手提包", "公文包",
                 "托特包", "手拿包", "胸包", "腰包", "帆布包", "手提袋")),
)

# 只有这些品类可以靠品名认角色：上衣的商品名里写「翻领」、
# 鞋的商品名里写「袜子男鞋」，说的都是设计，不是这件单品本身是袜子。
EXTRA_CATS = ("belt", "socks", "sock", "bag", "tie", "hosiery")

ROLE_NAME = {
    "belt": "皮带", "sock": "袜子", "bag": "包",
    "tie": "领带", "hosiery": "丝袜",
}

# 女装角色：只用来判断「这身有没有可判的裙装」，不参与男装规矩
WOMEN_CATS = ("skirt", "dress", "heels", "shoes_heels")

# 需要「配件收口」的场合：日常办公以下不强求，正式会面才讲究
FORMAL_ROLES = {3: ("belt",), 4: ("belt", "tie")}

# 会把衬衫领口盖住的中层：圆领/高领毛衣、卫衣。领带套在里面只露出一个结，
# 这不是「搭得好不好」的问题，是根本戴不进去。开衫、西装马甲不算——
# 它们敞着，领带照样露在外面，三件套正是这么穿的。
COVER_MIDS = ("sweater", "knit", "hoodie", "turtleneck", "fleece")
OPEN_MID_WORDS = ("开衫", "V领", "v领", "拉链", "马甲", "背心")

# 领带只在「衬衫 + 西装外套」这一种结构里成立。
# 大衣不是西装外套——它罩在西装外面，单穿大衣配领带不成立；
# 针织开衫同理，它敞着能看见领带，但针织 + 领带不是正装组合。
TIE_OUTER_CATS = ("blazer",)

# 必须是「真需要」，不是「有更好」的两级。
# required：缺了这身就不成立（皮鞋没袜、西裤没皮带、正式裙装配光腿）
# optional：缺了只是少一层讲究（包、领带）
LEVEL_REQUIRED, LEVEL_OPTIONAL = "required", "optional"


def role_of(item):
    """这件单品属于哪个配件角色；不是配件返回 None。

    优先用显式字段：用户以后可以在 UI 里直接标，比猜品名可靠。
    没有字段时才猜品名，而且**必须先卡槽位**——批量导入的商品名是电商
    全称，「秋季休闲劳保裤潮流系腰带西裤」里写着腰带，它是裤子不是皮带；
    「男鞋透气网面飞织袜子板鞋」里写着袜子，它是鞋不是袜。
    """
    role = item.get("layer_role")
    if role in ROLE_NAME:
        return role
    cat = item.get("category") or ""
    if item.get("slot") != "accessory" and cat not in EXTRA_CATS:
        return None
    text = " ".join(str(item.get(k) or "") for k in ("name", "photo", "note"))
    for role, words in ROLE_WORDS:
        if any(w in text for w in words):
            return role
    if cat in ("belt", "socks", "bag", "tie"):
        return {"belt": "belt", "socks": "sock", "bag": "bag", "tie": "tie"}[cat]
    return None


def gender_of(item):
    """男 / 女 / 中性。没证据就当中性，不硬猜。"""
    if item.get("gender") in ("men", "women", "neutral"):
        return item["gender"]
    text = " ".join(str(item.get(k) or "") for k in ("name", "photo", "note"))
    if any(w in text for w in ("女士", "女装", "女式", "女款", "裙", "高跟")):
        return "women"
    if any(w in text for w in ("男士", "男装", "男式", "男款")):
        return "men"
    if (item.get("category") or "") in WOMEN_CATS:
        return "women"
    return "neutral"


def lane(wardrobe):
    """整橱跑哪套配件规矩：有裙装/高跟才算女装衣橱。

    不能看 gender 判定——橱里有 101 件写着「女装」的上衣，但一条裙子都没有，
    这时配裤子穿的仍是男装那套（皮带跟皮鞋、深色不配白袜），
    换成女装规矩去问「腰线」反而无从答起。
    """
    return _style_lane(wardrobe)


def lane_of(chosen):
    """这一身跑哪套规矩：按这身里实际出现的单品判，而不是全橱。"""
    for c in chosen:
        if (c["item"].get("category") or "") in WOMEN_CATS:
            return "women"
    return "men"


def index(wardrobe):
    """把衣橱里所有配件按角色归档。"""
    bucket = {r: [] for r in ROLE_NAME}
    for it in wardrobe:
        if it.get("non_wearable") or it.get("category") == "junk":
            continue
        r = role_of(it)
        if r:
            bucket[r].append(it)
    return bucket


# ------------------------------------------------------------------ 反推
def _shoe(chosen):
    for c in chosen:
        if c["slot"] == "shoes":
            return c["item"]
    return None


def _bottom(chosen):
    for c in chosen:
        if c["slot"] == "bottom":
            return c["item"]
    return None


def _top(chosen):
    for c in chosen:
        if c["slot"] == "base":
            return c["item"]
    for c in chosen:
        if c["slot"] == "mid":
            return c["item"]
    return None


def _outer(chosen):
    for c in chosen:
        if c["slot"] == "outer":
            return c["item"]
    return None


def _is_dark(item, limit=0.35):
    return brightness((item or {}).get("color")) <= limit


def _is_shoe_formal(item):
    return (item or {}).get("category") in ("shoes_leather", "boots", "heels", "shoes_heels")


def _blocks_tie(mid):
    """这层中层在不在「领带能不能戴」这件事上说了不行。

    两个不同的原因，结论一样：
    1. 物理遮挡——圆领毛衣、高领、卫衣把领口盖住，领带只剩一个结；
    2. 结构不对——针织开衫敞着，领带看得见，但针织 + 领带不是正装组合。
    唯一的例外是西装马甲：衬衫 + 马甲 + 领带正是标准三件套。
    """
    if not mid:
        return False
    cat = (mid.get("category") or "")
    name = str(mid.get("name") or "")
    if cat == "vest" or "西装马甲" in name:
        return False
    return True


def _hint_belt(shoe, bottom):
    """皮带颜色由皮鞋定——这是男装礼仪里最硬的一条同色规则。

    但「同色」只在鞋是黑/棕时成立。浅灰、白、彩色的鞋是少数情况，
    这时皮带不跟着鞋走，反而要压深一档——浅灰皮鞋配浅灰皮带不是现实里存在的搭配，
    说出来用户也买不到。
    """
    sf = family((shoe or {}).get("color"))
    if sf == "棕":
        return "棕色系皮带，跟皮鞋同一族"
    if sf == "黑":
        return "黑色皮带，跟皮鞋同色"
    if sf in ("白", None):
        return "深棕或黑皮带，别用亮色去抢皮鞋"
    return f"黑色或深棕皮带——{C.normalize_color((shoe or {}).get('color'))}色的鞋是例外，皮带别跟着它走，压深一档更稳"


def _hint_sock(bottom):
    """袜子跟裤子走，但裤子已经很浅时要反过来取深色。

    否则会得出「浅蓝西裤配浅蓝袜子」这种买不到的建议。
    """
    if _is_dark(bottom):
        return f"深灰或黑的中筒袜，颜色要压过{bottom_name(bottom)}"
    if brightness((bottom or {}).get("color")) >= 0.62:
        return f"{bottom_name(bottom)}本身够浅，袜子取藏青或深灰，别跟着裤子走浅色——脚踝会断一刀"
    return "与裤子同色系、略深一档的袜子，别让脚踝跳出来"


def _hint_bag(shoe):
    sf = family((shoe or {}).get("color"))
    if sf in ("黑", "棕"):
        return f"{C.normalize_color((shoe or {}).get('color'))}色包，和鞋同色系最省事"
    if sf in ("白", None):
        return "黑或米色的包，别比鞋更抢眼"
    return "中性色包（黑/棕/米），包和鞋撞色是整身最容易散的地方"


def _hint_tie(top, bottom):
    tf = family((top or {}).get("color"))
    if tf in ("白", "浅蓝"):
        return f"比衬衫深一档的领带（藏青/酒红都行），别和{bottom_name(bottom)}一个色"
    return "领带要比衬衫深、比西裤亮，三个都深就糊成一片了"


def bottom_name(bottom):
    return (bottom or {}).get("name") or "裤子"


def needs(chosen, wardrobe, ctx, lan=None, bucket=None):
    """反推这身还差哪几件配件，并给具体颜色。

    只报「衣橱里确实没有」的角色。有的不报——用户自己会看到那件，
    系统再说「你需要一条皮带」就成了睁眼说瞎话。

    分两级，因为「缺」和「缺」不一样：
    - required：缺了这身不成立。皮鞋不穿袜、西裤不系皮带，是穿错，不是朴素。
    - optional：缺了只是少一层讲究。领带、包都属于这一类，不该催人去买。

    女士不报领带——这不是「可选」，是根本不在这一套规矩里。
    """
    req = int(ctx.get("formality") or 0) if ctx.get("formality") is not None else 2
    bucket = bucket if bucket is not None else index(wardrobe)
    lan = lan or lane_of(chosen)

    shoe, bot, top, outer = _shoe(chosen), _bottom(chosen), _top(chosen), _outer(chosen)
    mid = next((c["item"] for c in chosen if c["slot"] == "mid"), None)
    out = []

    def add(role, why, hint, priority, level):
        if bucket.get(role):
            return
        out.append({"role": role, "name": ROLE_NAME[role], "why": why,
                    "color_hint": hint, "priority": priority, "level": level})

    # —— 皮带：西裤 + 衬衫，才需要「皮带与皮鞋同色」这一说
    # 牛仔裤、运动裤没有裤袢，也不该配正装皮带；外套遮住腰时它不露，
    # 这时降级成可选——不是不用系，是别人看不见。
    bottom_formal = int((bot or {}).get("formality") or 0)
    bcat = (bot or {}).get("category") or ""
    belt_matters = (req >= 3 and bottom_formal >= 2
                    and bcat in ("dress_pants", "trousers", "chinos"))
    if belt_matters:
        covered = bool(outer) and (outer.get("category") or "") in ("coat", "blazer", "down_jacket")
        add("belt",
            f"{bottom_name(bot)}要配一条皮带，坐下或脱外套时最先被看到",
            _hint_belt(shoe, bot), 1,
            LEVEL_OPTIONAL if covered else LEVEL_REQUIRED)

    # —— 袜子：穿皮鞋就有这一说，不分场合寒暖。光脚穿皮鞋是穿错，不是随性。
    if req >= 2 and _is_shoe_formal(shoe):
        add("sock", "皮鞋配袜子，坐下来会露一截，这截决定整不整",
            _hint_sock(bot), 2, LEVEL_REQUIRED)

    # —— 领带：四个条件同时成立才提
    # ① 外层是西装外套（不是大衣）；② 内层是衬衫；③ 中层不挡领口；④ 不是女装规矩。
    # 少了任何一条，领带就不是「还没买」，而是「这身根本不戴领带」。
    ocat = (outer or {}).get("category") or ""
    tcat = (top or {}).get("category") or ""
    tie_fits = (lan != "women" and req >= 4 and ocat in TIE_OUTER_CATS
                and tcat == "shirt" and not _blocks_tie(mid))
    if tie_fits:
        add("tie", f"{outer.get('name')}配衬衫，领带能把正式度收住（不戴也不算错）",
            _hint_tie(top, bot), 3, LEVEL_OPTIONAL)

    # —— 包：正式场合才提，且是可选。没带包不构成穿错。
    if req >= 4:
        add("bag", "正式场合的包和鞋呼应，整身才收得住", _hint_bag(shoe), 4, LEVEL_OPTIONAL)

    # —— 女装两件：裙装看腰线，正式场合看丝袜
    if lan == "women":
        has_skirt = any(c["item"].get("category") in ("skirt", "dress") for c in chosen)
        if has_skirt and req >= 1:
            add("belt", "裙装配细腰带，腰线出来了比例才对",
                "细腰带，颜色跟鞋或包呼应", 1, LEVEL_OPTIONAL)
        if has_skirt and req >= 3:
            add("hosiery", "正式场合的裙装配光腿偏随意",
                "接近肤色的薄丝袜，别选带闪的", 2, LEVEL_REQUIRED)

    out.sort(key=lambda x: (x["level"] != LEVEL_REQUIRED, x["priority"]))
    return out


# ------------------------------------------------------------------ 校验
def check(chosen, wardrobe, ctx, lan=None, bucket=None):
    """配件校验：有就判对错，没有就开清单。

    返回 {lane, picked, issues, needs}：
    - picked：衣橱里有、且跟这身合得上的配件（直接显示在方案里）
    - issues：衣橱里有、但配错了（扣分项，只提示不改排序——它们不在候选池里）
    - needs：衣橱里没有的（不是错，是还没买）
    """
    if ctx.get("formality") is None:
        req = 2
    else:
        req = int(ctx["formality"])
    bucket = bucket if bucket is not None else index(wardrobe)
    lan = lan or lane_of(chosen)
    shoe, bot, top = _shoe(chosen), _bottom(chosen), _top(chosen)

    picked, issues = [], []

    def avail(role):
        return [it for it in bucket.get(role, []) if it.get("status", "clean") == "clean"]

    # —— 皮带：必须与皮鞋同色系（例外：鞋是白/米白时，棕黑都行）
    if req >= 3 and _is_shoe_formal(shoe):
        cands = avail("belt")
        sf = family((shoe or {}).get("color"))
        good = [b for b in cands if family(b.get("color")) == sf]
        if not good and sf not in ("白",):
            good = [b for b in cands if _is_dark(b) and sf == "黑"]
        if good:
            b = good[0]
            picked.append({"role": "belt", "item": b,
                           "reason": f"{b.get('name')}和{shoe.get('name')}同色系，"
                                     f"皮带是正式场合最容易露怯的一处"})
        elif cands:
            b = cands[0]
            issues.append({"code": "belt_mismatch",
                           "item": b.get("name"),
                           "note": f"{b.get('name')}配{shoe.get('name')}不同色系，"
                                   f"皮带和皮鞋必须同色，这是男装里最硬的一条"})

    # —— 袜子：深色下装不配浅袜
    cands = avail("sock")
    if cands and bot:
        dark_bottom = _is_dark(bot) or int(bot.get("formality") or 0) >= 3
        light = [s for s in cands if brightness(s.get("color")) >= 0.7]
        dark = [s for s in cands if brightness(s.get("color")) < 0.7]
        if dark_bottom and light and not dark:
            issues.append({"code": "sock_contrast",
                           "item": light[0].get("name"),
                           "note": f"{bot.get('name')}是深色，配{light[0].get('name')}会露一截白，"
                                   f"深色西装不配白袜是硬规矩"})
        elif dark:
            s = min(dark, key=lambda x: brightness(x.get("color")))
            picked.append({"role": "sock", "item": s,
                           "reason": f"{s.get('name')}比{bottom_name(bot)}更深，"
                                     f"坐下露出那一截不会跳"})

    # —— 包：与鞋同色系，不能各说各话
    cands = avail("bag")
    if cands and shoe and req >= 2:
        sf = family(shoe.get("color"))

        def dist(b):
            bf = family(b.get("color"))
            return 0 if bf == sf else (1 if bf in ("黑", "棕", "灰") else 2)

        bag = min(cands, key=dist)
        if dist(bag) >= 2:
            issues.append({"code": "bag_jump",
                           "item": bag.get("name"),
                           "note": f"{bag.get('name')}和{shoe.get('name')}色系差太远，"
                                   f"包和鞋要呼应，整身才收得住"})
        else:
            picked.append({"role": "bag", "item": bag,
                           "reason": f"{bag.get('name')}和{shoe.get('name')}呼应，"
                                     f"包是收口的那一件"})

    # —— 领带：不能和衬衫融、也不能和西裤一个色（像制服）
    cands = avail("tie")
    if cands and top and bot:
        tf, bf = family(top.get("color")), family(bot.get("color"))

        def tie_ok(t):
            f = family(t.get("color"))
            return f != tf and f != bf

        good = [t for t in cands if tie_ok(t)]
        if good:
            t = good[0]
            picked.append({"role": "tie", "item": t,
                           "reason": f"{t.get('name')}比衬衫深、和{bottom_name(bot)}不同色，"
                                     f"正好把正式度收住"})
        else:
            t = cands[0]
            same_bottom = family(t.get("color")) == bf
            issues.append({"code": "tie_clash",
                           "item": t.get("name"),
                           "note": (f"{t.get('name')}和{bottom_name(bot)}同色，上下一条线，"
                                    f"看着像制服；换一条比衬衫深、比裤子亮的"
                                    if same_bottom else
                                    f"{t.get('name')}和{top.get('name')}同色系，领带会融进衬衫里")})

    # —— 女装：裙长、露肤
    if lan == "women":
        skirt = next((c["item"] for c in chosen
                      if c["item"].get("category") in ("skirt", "dress")), None)
        if skirt:
            length = skirt.get("length") or skirt.get("skirt_length")
            if length == "mini" and req >= 3:
                issues.append({"code": "skirt_short",
                               "item": skirt.get("name"),
                               "note": f"{skirt.get('name')}是短款，正式场合裙摆到膝或过膝更稳"})
            if req >= 3 and not avail("hosiery"):
                issues.append({"code": "hosiery_gap",
                               "item": skirt.get("name"),
                               "note": f"{skirt.get('name')}配光腿在正式场合偏随意，"
                                       f"加一双接近肤色的薄丝袜"})

    # —— 浅色薄料会透：这条不分男女，米白亚麻西裤一样透
    if bot and brightness(bot.get("color")) >= 0.82:
        mat = str(bot.get("material") or "")
        if any(m in mat for m in ("雪纺", "真丝", "亚麻", "薄")):
            issues.append({"code": "sheer_bottom",
                           "item": bot.get("name"),
                           "note": f"{bot.get('name')}是浅色薄料，光线一照会透，"
                                   f"内里换成肤色无痕的"})

    return {"lane": lan, "picked": picked, "issues": issues,
            "needs": needs(chosen, wardrobe, ctx, lan)}


def merge_needs(needs_lists):
    """把几套方案的缺口合并成一份。

    缺口是衣橱的属性，不是某套衣服的属性：三套都缺同一条皮带，
    各说一遍就是同一句话讲三遍，页面上一眼望去全是「还差」。
    合并时按角色去重；只要有一套真需要（required），整体就算真需要——
    另一套恰好穿了外套把腰遮住，不代表皮带可以不系。
    """
    merged, order = {}, []
    for needs in needs_lists:
        for n in needs:
            old = merged.get(n["role"])
            if old is None:
                merged[n["role"]] = dict(n)
                order.append(n["role"])
            elif n["level"] == LEVEL_REQUIRED:
                old["level"] = LEVEL_REQUIRED
    out = [merged[r] for r in order]
    out.sort(key=lambda x: (x["level"] != LEVEL_REQUIRED, x["priority"]))
    return out


def summarize(result, limit=3):
    """给用户看的一句话总结：先说要改的，再说要买的。"""
    notes = [i["note"] for i in result.get("issues", [])]
    for n in result.get("needs", []):
        notes.append(f"还差一件{n['name']}：{n['color_hint']}")
    return notes[:limit]
