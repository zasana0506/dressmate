# -*- coding: utf-8 -*-
"""穿衣者身份：性别与年龄。

为什么需要这个模块：
「幸运穿搭」那一栏本来就要填出生日期和性别（紫微斗数排盘要用），
但推荐引擎从来不读这些信息。结果就是给女生推荐领带、给小孩推荐西装通勤——
用户上传的照片里明明标了 gender（women 有 178 件、men 有 960 件），
引擎却一条都没用上。

这个模块只做两件事：
1. 读档案，算出年龄与性别
2. 给出「这件单品/这个配件该不该出现在这个人身上」的判断

设计上刻意保守：
- 档案没填 → 什么都不拦，照旧推荐（不能因为没填档案就推不出东西）
- 单品没有性别标签 → 放行（大部分配件都是这样）
- 只在明确冲突时拦（女用户排除标着 men 的，男用户排除标着 women 的）
"""
import datetime
import json
import os

# 童装/成人世界的大致分界。低于这个年龄，正式场合（西装、皮带、领带）
# 基本不成立。
CHILD_AGE = 13
TEEN_AGE = 16


def profile_path(data_dir=None):
    """档案文件路径。data_dir 传了就用传的（测试时用）。"""
    if data_dir:
        return os.path.join(data_dir, "profile.json")
    try:
        from .paths import DATA_DIR
        return os.path.join(DATA_DIR, "profile.json")
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "profile.json")


def load_profile(data_dir=None):
    """读出生日期与性别。读不到就返回空档案，不报错。

    环境变量 DRESSMATE_PROFILE 可以指定档案文件路径。
    设成特殊值 "__none__" 表示「不要读磁盘档案」——测试用这个，
    免得被开发者本机的真实档案影响用例结果。
    """
    env = (os.environ.get("DRESSMATE_PROFILE") or "").strip()
    if env == "__none__":
        return {}
    if env:
        try:
            with open(env, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    try:
        with open(profile_path(data_dir), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def gender_of(profile):
    """档案里的性别，规整成「女」「男」或 None（没填/认不出）。"""
    g = (profile or {}).get("gender")
    if not g:
        return None
    g = str(g).strip()
    if g in ("女", "女性", "female", "f", "F"):
        return "女"
    if g in ("男", "男性", "male", "m", "M"):
        return "男"
    return None


def age_of(profile, today=None):
    """从出生日期算年龄（周岁）。没有出生日期就返回 None。"""
    raw = (profile or {}).get("solar_date") or ""
    if not raw:
        return None
    try:
        y, m, d = [int(x) for x in str(raw).split("-")[:3]]
        born = datetime.date(y, m, d)
    except Exception:
        return None
    now = today or datetime.date.today()
    if born > now:
        return None
    years = now.year - born.year
    # 生日还没到就减一岁
    if (now.month, now.day) < (born.month, born.day):
        years -= 1
    return years if 0 <= years < 130 else None


def is_child(profile, today=None):
    """是不是儿童（未满 CHILD_AGE 岁）。"""
    a = age_of(profile, today)
    return a is not None and a < CHILD_AGE


def is_teen(profile, today=None):
    a = age_of(profile, today)
    return a is not None and CHILD_AGE <= a < TEEN_AGE


def item_gender(item):
    """单品的性别标签，规整成「女」「男」或 None。"""
    g = (item or {}).get("gender")
    if not g:
        return None
    g = str(g).strip().lower()
    if g in ("women", "female", "f", "女", "womens"):
        return "女"
    if g in ("men", "male", "m", "男", "mens"):
        return "男"
    return None


def item_allowed(item, gender=None):
    """这件单品该不该给这个人。

    - 档案没填性别 → 全部放行
    - 单品没有性别标签 → 放行（配件大多没标签，不能一棍子打死）
    - 明确冲突 → 拦掉
    """
    g = gender_of({"gender": gender}) if gender else None
    if not g:
        return True
    ig = item_gender(item)
    if not ig:
        return True
    return ig == g or ig == "neutral"


def accessory_allowed(role, item, gender=None, age=None):
    """这个配件该不该给这个人。

    这里要处理 gender 标签管不了的情况——领带的 gender 全是空的
    （它们是按款式命名的，不是按性别命名的），所以得按角色和品类判。

    规则：
    - 领带/领结：默认是男士正装配饰。女的不要主动配。
      但如果这件单品自己标了 women（有些设计确实是女款），照给。
    - 皮带：成人配件。小孩不配。
    - 其它角色：只按 gender 标签判断。
    """
    g = gender_of({"gender": gender}) if gender else None
    if role in ("tie",):
        cat = (item or {}).get("category") or ""
        tie_cats = ("tie", "necktie", "bow_tie", "knit_tie", "knitted_tie")
        if cat in tie_cats or "领带" in (item or {}).get("name", "") \
                or "领结" in (item or {}).get("name", ""):
            # 单品自己标了女款就照给
            if item_gender(item) == "女":
                return True
            # 女的默认不主动配领带
            if g == "女":
                return False
    if role in ("belt",):
        if age is not None and age < CHILD_AGE:
            return False
    return item_allowed(item, g)


def describe(profile, today=None):
    """给前端用的一句话说明：为什么某些建议被排除/被调整。

    参数既可以传原始档案，也可以传 identity 字典（{"gender":..., "age":...}）。
    """
    g = gender_of(profile)
    a = age_of(profile, today)
    if a is None and isinstance(profile, dict):
        a = profile.get("age")
    bits = []
    if g:
        bits.append(f"{g}性")
    if a is not None:
        bits.append(f"{a} 岁")
    if not bits:
        return ""
    return "、".join(bits)


def formality_ceiling(profile, today=None):
    """这个人能接受的最高正式度。

    小孩不该穿西装打领带去上班；青少年也压一档。
    返回 None 表示不限制。

    参数既可以传原始档案（{"solar_date":..., "gender":...}），
    也可以传 identity 字典（{"gender":..., "age":...}）——
    后者已经有算好的年龄，直接用就行。
    """
    a = age_of(profile, today)
    if a is None and isinstance(profile, dict):
        a = profile.get("age")
    if a is None:
        return None
    if a < CHILD_AGE:
        return 1          # 最多「休闲偏正式」
    if a < TEEN_AGE:
        return 2          # 压一档
    return None
