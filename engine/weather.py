# -*- coding: utf-8 -*-
"""天气抓取与体感温度计算（Open-Meteo，免 key）。"""
import json
import os
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WMO_DESC = {
    0: "晴", 1: "大部晴朗", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛雨", 53: "毛雨", 55: "大毛雨", 56: "冻毛雨", 57: "强冻毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "强阵雨", 82: "暴雨", 85: "阵雪", 86: "强阵雪",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷暴伴冰雹",
}


def fetch(lat, lon, tz="Asia/Shanghai", timeout=15, retries=3):
    """拉取当天逐小时 + 逐日天气。失败时回退到本地缓存。

    带重试：国内网络到 open-meteo 偶发连接被拒。
    """
    params = {
        "latitude": lat, "longitude": lon, "timezone": tz,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,wind_speed_10m,weather_code,uv_index",
        "daily": "temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,"
                 "precipitation_probability_max,precipitation_sum,wind_speed_10m_max,uv_index_max,weather_code",
        "forecast_days": 1,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    last_exc = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dressmate/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            w = _parse(raw)
            _save_cache(w)
            return w
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    # 全部失败 → 用缓存，不让推荐流程挂掉
    cached = _load_cache()
    if cached:
        cached["stale"] = True
        cached["error"] = str(last_exc)
        return cached
    # 连缓存都没有（首次启动就没网）→ 用气候均值兜底，
    # 宁可给一个大致准确的温度，也不要让整个推荐页面报错打不开。
    fb = fallback(lat, lon)
    if fb:
        fb["stale"] = True
        fb["error"] = str(last_exc)
        return fb
    raise last_exc


# 各月平均气温（°C），用于断网时的粗略估算。只用来兜底，不参与精确判断。
_CLIMATE = {
    1: 2, 2: 4, 3: 9, 4: 15, 5: 20, 6: 24,
    7: 27, 8: 26, 9: 22, 10: 16, 11: 10, 12: 5,
}


def fallback(lat, lon):
    """用月份均值 + 纬度修正造一份天气。

    纬度越高越冷：每偏离 30 度均温降约 4 度。
    南北半球月份相反——南半球 7 月是冬天。
    """
    import datetime as _dt
    today = _dt.date.today()
    month = today.month
    # 纬度 < 0 属南半球，月份要翻过来
    if lat < 0:
        month = (month + 6) % 12 + 1
    base = _CLIMATE.get(month, 18)
    adj = -((abs(lat) - 30.0) / 30.0) * 4.0
    temp = round(base + adj, 1)
    hours = []
    for h in range(0, 24):
        # 日变化：凌晨最低，午后最高
        curve = 3.5 * ((6 - abs(h - 14)) / 8.0)
        hours.append({
            "hour": h, "temp": round(temp + curve, 1),
            "apparent": round(temp + curve - 0.5, 1),
            "pop": 0, "precip": 0, "wind": 8.0, "code": 2, "uv": 0,
        })
    feels = [h["apparent"] for h in hours]
    return {
        "date": today.isoformat(),
        "current": {
            "temp": temp, "apparent": temp, "humidity": None,
            "precip": 0, "code": 2, "wind": 8.0, "desc": "按季节估算",
        },
        "daily": {
            "tmax": temp + 3.5, "tmin": temp - 3.5,
            "feels_max": temp + 3.0, "feels_min": temp - 4.0,
            "pop_max": 0, "precip_sum": 0, "wind_max": 15.0, "uv_max": 0,
            "code": 2, "desc": "按季节估算",
        },
        "hours": hours,
        "feel_max": max(feels), "feel_min": min(feels),
        "feel_mean": round(sum(feels) / len(feels), 1),
        "stale": False,
    }


def fetch_days(lat, lon, start_date, end_date, tz="Asia/Shanghai", timeout=15, retries=3):
    """拉取 [start_date, end_date] 区间的逐日预报，用于出差打包。

    Open-Meteo 免费版最多给 16 天，超出部分直接截断并标注，
    避免用户选了半个月后被静默少算几天。
    """
    import datetime as _dt

    today = _dt.date.today()
    end = _dt.date.fromisoformat(str(end_date))
    start = _dt.date.fromisoformat(str(start_date))
    if end < start:
        start, end = end, start
    span = max(1, (end - today).days + 1)          # 从今天算到返程日
    span = min(span, 16)

    params = {
        "latitude": lat, "longitude": lon, "timezone": tz,
        "daily": "temperature_2m_max,temperature_2m_min,apparent_temperature_max,"
                 "apparent_temperature_min,precipitation_probability_max,precipitation_sum,"
                 "wind_speed_10m_max,uv_index_max,weather_code",
        "forecast_days": span,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    last_exc = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dressmate/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            return _parse_days(raw, start, end)
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc


def _parse_days(raw, start, end):
    """把逐日数组拆成 [{date, daily, feel_min/max/mean, ...}]。"""
    d = raw.get("daily", {})
    dates = d.get("time", [])
    out = []
    for i, day in enumerate(dates):
        try:
            if not (start.isoformat() <= day <= end.isoformat()):
                continue
        except Exception:
            continue
        fmax = d.get("apparent_temperature_max", [None] * len(dates))[i]
        fmin = d.get("apparent_temperature_min", [None] * len(dates))[i]
        if fmax is None or fmin is None:
            continue
        code = d.get("weather_code", [0] * len(dates))[i]
        out.append({
            "date": day,
            "feel_max": fmax,
            "feel_min": fmin,
            "feel_mean": round((fmax + fmin) / 2, 1),
            "daily": {
                "tmax": d.get("temperature_2m_max", [None] * len(dates))[i],
                "tmin": d.get("temperature_2m_min", [None] * len(dates))[i],
                "feels_max": fmax, "feels_min": fmin,
                "pop_max": d.get("precipitation_probability_max", [0] * len(dates))[i] or 0,
                "precip_sum": d.get("precipitation_sum", [0] * len(dates))[i] or 0,
                "wind_max": d.get("wind_speed_10m_max", [0] * len(dates))[i] or 0,
                "uv_max": d.get("uv_index_max", [0] * len(dates))[i] or 0,
                "code": code,
                "desc": WMO_DESC.get(code, "—"),
            },
            "hours": [],
            "stale": False,
        })
    if not out:
        raise ValueError("预报区间内没有可用数据（可能超出 16 天预报范围）")
    return out


def _parse(raw):
    cur = raw.get("current", {})
    daily = raw.get("daily", {})
    hourly_raw = raw.get("hourly", {})

    hours = []
    n = len(hourly_raw.get("time", []))
    for i in range(n):
        t = hourly_raw["time"][i]
        hours.append({
            "time": t,
            "hour": int(t[11:13]),
            "temp": hourly_raw["temperature_2m"][i],
            "apparent": hourly_raw["apparent_temperature"][i],
            "pop": hourly_raw.get("precipitation_probability", [0] * n)[i] or 0,
            "precip": hourly_raw.get("precipitation", [0] * n)[i] or 0,
            "wind": hourly_raw.get("wind_speed_10m", [0] * n)[i] or 0,
            "code": hourly_raw.get("weather_code", [0] * n)[i],
            "uv": hourly_raw.get("uv_index", [0] * n)[i] or 0,
        })

    feels = [h["apparent"] for h in hours] or [cur.get("apparent_temperature", 20)]
    day_feel = [
        {"hour": h["hour"], "apparent": h["apparent"], "temp": h["temp"],
         "pop": h["pop"], "wind": h["wind"], "code": h["code"], "uv": h["uv"]}
        for h in hours
    ]
    return {
        "date": daily.get("time", [""])[0],
        "current": {
            "temp": cur.get("temperature_2m"),
            "apparent": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "precip": cur.get("precipitation"),
            "code": cur.get("weather_code"),
            "wind": cur.get("wind_speed_10m"),
            "desc": WMO_DESC.get(cur.get("weather_code"), "—"),
        },
        "daily": {
            "tmax": daily.get("temperature_2m_max", [None])[0],
            "tmin": daily.get("temperature_2m_min", [None])[0],
            "feels_max": daily.get("apparent_temperature_max", [None])[0],
            "feels_min": daily.get("apparent_temperature_min", [None])[0],
            "pop_max": daily.get("precipitation_probability_max", [0])[0],
            "precip_sum": daily.get("precipitation_sum", [0])[0],
            "wind_max": daily.get("wind_speed_10m_max", [0])[0],
            "uv_max": daily.get("uv_index_max", [0])[0],
            "code": daily.get("weather_code", [0])[0],
            "desc": WMO_DESC.get(daily.get("weather_code", [0])[0], "—"),
        },
        "hours": day_feel,
        "feel_max": max(feels),
        "feel_min": min(feels),
        "feel_mean": round(sum(feels) / len(feels), 1),
        "stale": False,
    }


def _cache_path():
    from . import paths
    return paths.WEATHER_CACHE_PATH


def _save_cache(w):
    os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
    with open(_cache_path(), "w", encoding="utf-8") as f:
        json.dump(w, f, ensure_ascii=False, indent=2)


def _load_cache():
    p = _cache_path()
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None
