# -*- coding: utf-8 -*-
"""命令行入口：生成今日穿搭推荐。

用法:
    python run.py                     # 用默认日程 + 实时天气
    python run.py --city Beijing      # 指定城市
    python run.py --schedule schedule.json
    python run.py --json              # 输出机器可读 JSON
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import config as C          # noqa: E402
from engine import context as CTX      # noqa: E402
from engine import recommend as REC    # noqa: E402
from engine import timeline as TL      # noqa: E402
from engine import weather as WX       # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WARDROBE_PATH = os.path.join(BASE_DIR, "wardrobe", "wardrobe.json")
SCHEDULE_PATH = os.path.join(BASE_DIR, "data", "schedule.json")

CITIES = {
    "beijing": (39.9042, 116.4074, "北京"),
    "shanghai": (31.2304, 121.4737, "上海"),
    "guangzhou": (23.1291, 113.2644, "广州"),
    "shenzhen": (22.5431, 114.0579, "深圳"),
    "hangzhou": (30.2741, 120.1551, "杭州"),
    "chengdu": (30.5728, 104.0668, "成都"),
    "wuhan": (30.5928, 114.3055, "武汉"),
    "nanjing": (32.0603, 118.7969, "南京"),
    "xian": (34.3416, 108.9398, "西安"),
    "harbin": (45.8038, 126.5350, "哈尔滨"),
}


def load_wardrobe(path=WARDROBE_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["items"]


def load_schedule(path=SCHEDULE_PATH):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("events", data if isinstance(data, list) else [])


def build_payload(wardrobe, events, weather, today=None, top_n=3):
    today = today or datetime.date.today()
    ctx = CTX.build_context(events, weather)
    results, pools, extra = REC.recommend(wardrobe, ctx, weather, top_n=top_n, today=today)
    band = REC.band_of(weather["feel_mean"])
    return {
        "date": str(today),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "weather": weather,
        "context": ctx,
        "band": {"key": band, "label": C.TEMPERATURE_BANDS[band]["label"],
                 "required_layers": C.TEMPERATURE_BANDS[band]["required"]},
        "recommendations": results,
        "sport_outfit": extra.get("sport_outfit", []),
        "degraded": extra.get("degraded"),
        "pool_stats": {k: len(v) for k, v in pools.items()},
        "wardrobe_count": len(wardrobe),
        "timeline": TL.plan_day(wardrobe, events, weather),
    }


def print_human(payload):
    w = payload["weather"]
    ctx = payload["context"]
    band = payload["band"]
    print("=" * 62)
    print(f"  {payload['date']}  今日穿搭建议")
    print("=" * 62)
    print(f"天气   {w['daily']['desc']}  气温 {w['daily']['tmin']:.0f}~{w['daily']['tmax']:.0f}℃"
          f"  体感 {w['feel_min']:.0f}~{w['feel_max']:.0f}℃")
    print(f"       降水概率 {w['daily']['pop_max']}%   风速 {w['daily']['wind_max']:.0f}km/h"
          f"   紫外线 {w['daily']['uv_max']:.0f}")
    print(f"温度档 {band['label']}   场合 {ctx['formality_label']}"
          f"   需穿层数 {len(band['required_layers'])}")
    if ctx["events"]:
        print("日程   " + " | ".join(f"{e['start']} {e['title']}({e['tag']})" for e in ctx["events"]))
    print("-" * 62)

    for rec in payload["recommendations"]:
        print(f"\n【方案 {rec['rank']}】{rec['label']}   综合分 {rec['score']:.3f}")
        p = rec["parts"]
        print(f"  保暖 {p['warmth']:.2f} | 正式度 {p['formality']:.2f} | "
              f"配色 {p['harmony']:.2f} | 轮换 {p['freshness']:.2f} | 天气 {p['weather']:.2f}")
        for o in rec["outfit"]:
            print(f"    · {o['slot_name']}  {o['item']['name']}")
            print(f"      {o['reason']}")
    if payload.get("degraded"):
        print("\n注意   " + payload["degraded"]["note"])
    if payload.get("sport_outfit"):
        print("\n【运动装备】")
        for o in payload["sport_outfit"]:
            print(f"    · {o['slot_name']}  {o['item']['name']}")
    tl = payload.get("timeline")
    if tl and tl["segments"]:
        print("\n" + "-" * 62)
        print("  分时段计划")
        print("-" * 62)
        for idx, s in enumerate(tl["segments"]):
            head = f"{s['label']}  {s['occasion']}  体感{s['weather']['feel_mean']:.0f}℃"
            if s["change_needed"]:
                head += "  【需换装】"
            elif idx > 0:
                head += "  【沿用上一套】"
            print(f"\n{head}")
            print("  " + "；".join(s["change_reasons"]))
            if s["change_needed"] and s["changes"]:
                print("  变动：" + "、".join(
                    f"{c['slot_name']}{c['action']}{c['item'] or ''}" for c in s["changes"]))
            print("  穿：" + " + ".join(o["item"]["name"] for o in s["recommendation"]["outfit"]))
        for a in tl["day_advice"]:
            print("\n全天   " + a)
    if ctx["advice"]:
        print("\n提示   " + "；".join(ctx["advice"]))
    print("=" * 62)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="beijing", choices=sorted(CITIES))
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--schedule", default=SCHEDULE_PATH)
    ap.add_argument("--wardrobe", default=WARDROBE_PATH)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=3)
    args = ap.parse_args()

    lat, lon, city_name = CITIES.get(args.city, CITIES["beijing"])
    lat = args.lat if args.lat is not None else lat
    lon = args.lon if args.lon is not None else lon

    wardrobe = load_wardrobe(args.wardrobe)
    events = load_schedule(args.schedule)
    weather = WX.fetch(lat, lon)

    payload = build_payload(wardrobe, events, weather, top_n=args.top)
    payload["city"] = city_name

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return payload


if __name__ == "__main__":
    main()
