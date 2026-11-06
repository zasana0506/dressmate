# -*- coding: utf-8 -*-
"""城市坐标：离线表为主，在线地理编码兜底。

为什么不能全信在线
------------------
Open-Meteo 的地理编码对中文名很不稳：查「东莞」返回 20.30/109.99
（雷州半岛某个镇，真实东莞是 23.02/113.75），查「洛阳」返回福建一个同名
小镇。它按「地名匹配度」排序，不管行政级别。只有
① 加「市」字 ② 校验 feature_code 是 PPLA*（行政中心）③ 名字完全对得上，
三条同时满足才准。

即便这样仍有查不到的（临沂、襄阳直接返回空）。所以第一次跑
`tools/build_cities.py` 把 300 多个城市全量拉下来存进 data/cities.json，
之后一律查本地表——快、稳、断网也能用。表里没有的生僻地名才走在线。
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _table_path():
    """城市表位置。容器里 DATA_DIR 挂卷后，首启拷贝进去的是权威那份。"""
    from . import paths
    return paths.cities_path()


TABLE_PATH = _table_path()

# 老版本城市参数是拼音 slug，存在浏览器的 localStorage 里。
# 换表之后不能让这些用户一打开就变成「城市无效」，所以留着别名。
ALIASES = {
    "beijing": "北京", "shanghai": "上海", "guangzhou": "广州",
    "shenzhen": "深圳", "hangzhou": "杭州", "chengdu": "成都",
    "wuhan": "武汉", "nanjing": "南京", "xian": "西安", "harbin": "哈尔滨",
}

# 只有行政中心才算「这座城市」，普通居民点（PPL）会命中同名的镇
CITY_FEATURES = ("PPLA", "PPLA2", "PPLA3", "PPLC", "PPLA4")

_lock = threading.Lock()
_table = None


def _read():
    if not os.path.exists(TABLE_PATH):
        return {}
    try:
        with open(TABLE_PATH, encoding="utf-8") as f:
            return json.load(f).get("cities") or {}
    except Exception:
        return {}


def table():
    """整张表（进程内缓存）。"""
    global _table
    if _table is None:
        _table = _read()
    return _table


def _save(entry):
    """在线查到的新城市写回表里，下次不用再联网。"""
    global _table
    with _lock:
        data = _read()
        data.update(entry)
        os.makedirs(os.path.dirname(TABLE_PATH), exist_ok=True)
        with open(TABLE_PATH, "w", encoding="utf-8") as f:
            json.dump({"cities": data}, f, ensure_ascii=False, indent=1, sort_keys=True)
        _table = data


def normalize(name):
    """用户输入 → 表里的键。去空格、去「市」，slug 走别名。"""
    s = str(name or "").strip()
    if not s:
        return ""
    if s.lower() in ALIASES:
        return ALIASES[s.lower()]
    for suf in ("市", "地区", "自治州", "盟"):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
            break
    return s


def _norm_name(s):
    """撇号归一。GeoNames 用全角右引号（Tai’an），和键盘打出来的不是同一个字符。"""
    s = str(s or "").rstrip("市")
    for apos in ("’", "‘", "`", "´", "＇"):
        s = s.replace(apos, "'")
    return s.strip().lower()


def _geocode_online(bare):
    """在线兜底：带「市」查，只接受城市级结果。

    这是最后一道，只在本地表里没有时用。宁可返回 None 让用户换写法，
    也不返回一个「看着像」的坐标——天气错了，穿搭整个就错了。
    """
    q = bare + "市"
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": q, "count": 10, "language": "zh", "countryCode": "CN"})
    req = urllib.request.Request(url, headers={"User-Agent": "dressmate/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        results = json.loads(resp.read().decode("utf-8")).get("results") or []
    for r in results:
        if _norm_name(r.get("name")) != _norm_name(bare):
            continue
        if r.get("feature_code") not in CITY_FEATURES:
            continue
        if r.get("country_code") not in (None, "CN"):
            continue
        return {"lat": round(r["latitude"], 4), "lon": round(r["longitude"], 4),
                "province": str(r.get("admin1") or "").rstrip("省"),
                "name": r.get("name") or bare}
    return None


def resolve(name, allow_online=True):
    """城市名 → {key, name, province, lat, lon, source}；解析不出来返回 None。

    显示名用 key（用户输入的那种写法），不用数据源给的 name——
    GeoNames 里泰安存成「Tai’an」、新乡存成「南干道」（市辖区名），
    直接显示出来用户会以为自己选错了城市。
    """
    key = normalize(name)
    if not key:
        return None
    hit = table().get(key)
    if hit:
        return {"key": key, "name": key,
                "province": hit.get("province") or "",
                "lat": hit["lat"], "lon": hit["lon"], "source": "table"}
    if not allow_online:
        return None
    try:
        found = _geocode_online(key)
    except Exception:
        return None
    if not found:
        return None
    _save({key: found})
    return {"key": key, "name": key,
            "province": found.get("province") or "",
            "lat": found["lat"], "lon": found["lon"], "source": "online"}


def search(q="", limit=20):
    """本地模糊搜索：支持中文子串、省份名。"""
    q = normalize(q)
    # name 用 key 而不是数据源里的 name：GeoNames 的写法五花八门
    # （「东莞市」「Tai’an」「南干道」），列表里得是用户认得的那个名字
    items = [{"key": k, "name": k,
              "province": v.get("province") or "",
              "lat": v["lat"], "lon": v["lon"]}
             for k, v in table().items()]
    if not q:
        return items[:limit]
    exact = [it for it in items if it["key"] == q or it["name"] == q or it["name"] == q + "市"]
    starts = [it for it in items if it not in exact and it["key"].startswith(q)]
    contains = [it for it in items if it not in exact and it not in starts and q in it["key"]]
    by_prov = [it for it in items if it not in exact and it not in starts
               and it not in contains and q in it["province"]]
    return (exact + starts + contains + by_prov)[:limit]


def all_cities():
    """全量列表（给前端一次性加载，300 多条不算大）。"""
    return search("", limit=10000)
