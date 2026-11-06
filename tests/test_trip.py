# -*- coding: utf-8 -*-
"""出差打包引擎的回归测试。

重点保护一个不变量：**逐日方案里出现的每一件，都必须在你带的清单里**。
否则用户会拿到「清单说带 3 件、方案却让你穿第 4 件」的矛盾结果。
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: F401  测试环境隔离（不读本机真实档案）

from engine import trip as TRIP  # noqa: E402
from engine import config as C   # noqa: E402


def load_wardrobe():
    import json
    p = os.path.join(BASE_DIR, "tests", "fixtures", "wardrobe.json")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data["items"] if isinstance(data, dict) else data


def fake_day(date, fmin, fmax, pop=0, wind=10, uv=3, code=0):
    """构造一天的天气，避免测试依赖网络。"""
    return {
        "date": date,
        "feel_min": fmin, "feel_max": fmax,
        "feel_mean": round((fmin + fmax) / 2, 1),
        "daily": {"tmax": fmax + 2, "tmin": fmin - 2,
                  "feels_max": fmax, "feels_min": fmin,
                  "pop_max": pop, "precip_sum": 0, "wind_max": wind,
                  "uv_max": uv, "code": code, "desc": "多云"},
        "hours": [], "stale": False,
    }


def cold_trip(days=5):
    return [fake_day(f"2026-11-{6+i:02d}", -16, -10 + i) for i in range(days)]


class TestQuota(unittest.TestCase):
    def test_base_grows_with_days(self):
        a = TRIP.quota_of("base", 2, True)
        b = TRIP.quota_of("base", 5, True)
        self.assertLess(a, b, "天数多，内层配额应该增加")

    def test_no_laundry_needs_more(self):
        wash = TRIP.quota_of("base", 5, True)
        nowash = TRIP.quota_of("base", 5, False)
        self.assertGreater(nowash, wash, "不洗衣时内层要多带")

    def test_outer_follows_temp_span_not_days(self):
        """外套一件能穿到底，除非温差大需要薄厚各一件。"""
        self.assertEqual(TRIP.quota_of("outer", 3, True, span=5), 1)
        self.assertEqual(TRIP.quota_of("outer", 9, True, span=5), 1)
        self.assertEqual(TRIP.quota_of("outer", 9, True, span=15), 2)

    def test_shoes_always_one(self):
        for d in (1, 3, 8):
            self.assertEqual(TRIP.quota_of("shoes", d, True), 1)


class TestPlanTrip(unittest.TestCase):
    def setUp(self):
        self.items = load_wardrobe()

    def test_basic_shape(self):
        res = TRIP.plan_trip(self.items, cold_trip(3), formality=3, purpose="客户拜访")
        self.assertNotIn("error", res)
        self.assertEqual(res["days"], 3)
        self.assertTrue(res["packing"], "应该有打包清单")
        self.assertTrue(res["daily_plans"], "应该有逐日方案")
        self.assertGreater(res["total_items"], 0)

    def test_plan_items_always_in_packing(self):
        """核心不变量：方案里每件都得在清单里，否则用户带不够。"""
        for days, fml in [(2, 2), (5, 3)]:
            res = TRIP.plan_trip(self.items, cold_trip(days), formality=fml, purpose="出差")
            packed = {}
            for p in res["packing"]:
                packed[p["slot"]] = {i["id"] for i in p["items"]}
            for plan in res["daily_plans"]:
                for o in plan["recommendation"]["outfit"]:
                    ids = packed.get(o["slot"], set())
                    self.assertIn(o["item"]["id"], ids,
                                  f"{plan['date']} 的{o['slot_name']}「{o['item']['name']}」不在清单里")

    def test_no_item_repeats_within_slot(self):
        res = TRIP.plan_trip(self.items, cold_trip(4), formality=2, purpose="出差")
        for p in res["packing"]:
            ids = [i["id"] for i in p["items"]]
            self.assertEqual(len(ids), len(set(ids)), f"{p['slot_name']}出现重复件")

    def test_spare_marked(self):
        """换洗备用件要标出来，不能和主穿件混为一谈。"""
        res = TRIP.plan_trip(self.items, cold_trip(5), formality=2, purpose="出差")
        base = next((p for p in res["packing"] if p["slot"] == "base"), None)
        self.assertIsNotNone(base)
        if base["count"] > 1:
            spares = [i for i in base["items"] if i.get("spare")]
            prim = [i for i in base["items"] if not i.get("spare")]
            self.assertTrue(prim, "至少要有一件是主穿件")
            self.assertEqual(len(spares) + len(prim), base["count"])

    def test_rain_alert(self):
        days = [fake_day("2026-11-06", 10, 16, pop=80),
                fake_day("2026-11-07", 9, 15, pop=70)]
        res = TRIP.plan_trip(self.items, days, formality=2, purpose="出差")
        joined = " ".join(res["alerts"])
        self.assertIn("降水概率", joined)

    def test_snow_alert(self):
        days = [fake_day("2026-11-06", -8, -2, code=71)]
        res = TRIP.plan_trip(self.items, days, formality=2, purpose="出差")
        self.assertIn("降雪", " ".join(res["alerts"]))

    def test_big_span_suggests_layering(self):
        days = [fake_day("2026-11-06", -5, 2), fake_day("2026-11-07", -6, 14)]
        res = TRIP.plan_trip(self.items, days, formality=2, purpose="出差")
        self.assertGreaterEqual(res["temp_span"], 12)
        self.assertIn("叠穿", " ".join(res["advice"]))

    def test_empty_wardrobe_reports_gap(self):
        res = TRIP.plan_trip([], cold_trip(3), formality=2, purpose="出差")
        self.assertIn("error", res)
        self.assertTrue(res["alerts"])

    def test_empty_weather(self):
        res = TRIP.plan_trip(self.items, [], formality=2, purpose="出差")
        self.assertIn("error", res)

    def test_luggage_estimate(self):
        res = TRIP.plan_trip(self.items, cold_trip(2), formality=2, purpose="出差")
        self.assertTrue(any("箱" in a for a in res["advice"]), "应该估算行李大小")

    def test_base_shortfall_flagged(self):
        """衣橱里撑得住场合的内层不够时，必须显式报缺口。"""
        res = TRIP.plan_trip(self.items, cold_trip(5), formality=3, purpose="客户拜访")
        base = next((p for p in res["packing"] if p["slot"] == "base"), None)
        self.assertIsNotNone(base)
        if base["count"] < base["want"]:
            self.assertGreater(base["shortfall"], 0)
            self.assertIn("内层", " ".join(res["alerts"]))


if __name__ == "__main__":
    unittest.main()
