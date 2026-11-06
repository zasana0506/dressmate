# -*- coding: utf-8 -*-
"""回归测试套件（标准库 unittest，无需 pytest）。

运行：  python -m unittest discover -s tests -v
      或 python tests/test_engine.py

全部用合成天气数据，不依赖网络。每个用例对应一个曾经真实出现过的缺陷。
"""
import copy
import datetime
import json
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: F401  测试环境隔离（不读本机真实档案）
sys.path.insert(0, os.path.join(BASE_DIR, "tools"))

from engine import config as C            # noqa: E402
from engine import context as CTX         # noqa: E402
from engine import recommend as REC       # noqa: E402
from engine import timeline as TL         # noqa: E402

FIXTURE = os.path.join(BASE_DIR, "tests", "fixtures", "wardrobe.json")
WARDROBE = json.load(open(FIXTURE, encoding="utf-8"))["items"]
TODAY = datetime.date(2026, 11, 5)


def make_weather(feel_mean=10.0, feel_min=None, feel_max=None, pop=0,
                 wind=10, uv=2, desc="晴"):
    """构造合成天气，避免测试依赖网络。"""
    feel_min = feel_mean - 4 if feel_min is None else feel_min
    feel_max = feel_mean + 4 if feel_max is None else feel_max
    hours = []
    for h in range(24):
        # 日内曲线：5点最冷，15点最热
        t = feel_min + (feel_max - feel_min) * max(0.0, min(1.0, (h - 5) / 10.0))
        if h > 15:
            t = feel_min + (feel_max - feel_min) * max(0.0, (23 - h) / 8.0)
        hours.append({"hour": h, "apparent": round(t, 1), "temp": round(t + 1, 1),
                      "pop": pop, "wind": wind, "uv": uv, "code": 0})
    return {
        "date": "2026-11-05", "current": {"apparent": feel_mean, "temp": feel_mean + 1,
                                         "humidity": 50, "precip": 0, "code": 0,
                                         "wind": wind, "desc": desc},
        "daily": {"tmax": feel_max + 1, "tmin": feel_min - 1,
                  "feels_max": feel_max, "feels_min": feel_min,
                  "pop_max": pop, "precip_sum": 0, "wind_max": wind,
                  "uv_max": uv, "code": 0, "desc": desc},
        "hours": hours, "feel_max": feel_max, "feel_min": feel_min,
        "feel_mean": feel_mean, "stale": False,
    }


class TestBanding(unittest.TestCase):
    def test_band_boundaries(self):
        self.assertEqual(REC.band_of(28), "hot")
        self.assertEqual(REC.band_of(27.9), "warm")
        self.assertEqual(REC.band_of(22), "warm")
        self.assertEqual(REC.band_of(15), "mild")
        self.assertEqual(REC.band_of(8), "cool")
        self.assertEqual(REC.band_of(7.9), "cold")

    def test_required_layers(self):
        self.assertEqual(C.TEMPERATURE_BANDS["hot"]["required"], ["base"])
        self.assertEqual(C.TEMPERATURE_BANDS["cold"]["required"],
                         ["base", "mid", "outer"])

    def test_lerp_endpoints(self):
        self.assertAlmostEqual(REC._lerp(C.BASE_CLO_KNOTS, 30), 0.15)
        self.assertAlmostEqual(REC._lerp(C.BASE_CLO_KNOTS, 0), 0.32)
        self.assertEqual(REC._lerp(C.BASE_CLO_KNOTS, 99), 0.15)
        self.assertEqual(REC._lerp(C.BASE_CLO_KNOTS, -99), 0.32)


class TestContext(unittest.TestCase):
    def test_keyword_formality(self):
        cases = [("面试", 4), ("客户方案沟通", 4), ("部门例会", 3),
                 ("项目数据整理", 2), ("逛街", 1), ("居家休息", 0)]
        for title, expect in cases:
            lvl, sport, _, _ = CTX.classify_event(title)
            self.assertEqual(lvl, expect, f"{title} 期望正式度 {expect}，实际 {lvl}")

    def test_sport_override(self):
        lvl, sport, tag, _ = CTX.classify_event("健身房 下肢训练")
        self.assertTrue(sport)
        self.assertEqual(lvl, 0)
        self.assertEqual(tag, "运动")

    def test_context_takes_max_formality(self):
        events = [{"start": "09:00", "title": "项目数据整理"},
                  {"start": "11:00", "title": "客户方案沟通"}]
        ctx = CTX.build_context(events, make_weather())
        self.assertEqual(ctx["formality"], 4)
        self.assertTrue(ctx["has_sport"] is False)

    def test_slot_temp_uses_three_points(self):
        w = make_weather(feel_mean=10, feel_min=2, feel_max=18)
        ctx = CTX.build_context([], w)
        self.assertEqual(ctx["slot_temp"]["outer"], 2)   # 最冷定外层
        self.assertEqual(ctx["slot_temp"]["base"], 18)   # 最热定内层
        self.assertEqual(ctx["slot_temp"]["mid"], 10)    # 平均定中层


class TestRecommend(unittest.TestCase):
    """这些用例对应开发中真实踩过的坑。"""

    def recs(self, weather, events=None, wardrobe=None):
        w = weather
        ctx = CTX.build_context(events or [], w)
        results, pools, extra = REC.recommend(wardrobe or WARDROBE, ctx, w,
                                              top_n=3, today=TODAY)
        return results, extra

    def test_cold_day_outer_must_be_warm(self):
        """回归：曾经 2℃ 推荐了 0.32clo 薄西装外套。"""
        w = make_weather(feel_mean=5, feel_min=2, feel_max=9)
        results, _ = self.recs(w, [{"start": "10:00", "title": "办公"}])
        self.assertTrue(results, "冷天不应返回空结果")
        outer = next(o["item"] for o in results[0]["outfit"] if o["slot"] == "outer")
        self.assertGreaterEqual(outer["clo"], 0.45,
                                f"2℃ 外层保暖值不足：{outer['name']} {outer['clo']}")

    def test_formality_degrades_instead_of_empty(self):
        """回归：曾经正式度硬过滤导致推荐结果为空。"""
        w = make_weather(feel_mean=5, feel_min=2, feel_max=9)
        results, extra = self.recs(w, [{"start": "10:00", "title": "董事会汇报"}])
        self.assertTrue(results, "衣橱缺正装外套时应降级，不能返回空")
        self.assertIsNotNone(extra["degraded"], "降级必须明确告知用户")
        self.assertIn("降级", extra["degraded"]["note"])

    def test_hot_day_no_down_jacket(self):
        w = make_weather(feel_mean=30, feel_min=26, feel_max=34)
        results, _ = self.recs(w)
        if results:
            for o in results[0]["outfit"]:
                self.assertLess(o["item"]["clo"], 0.5,
                                f"大热天不应出现 {o['item']['name']}")

    def test_rain_prefers_waterproof_or_umbrella(self):
        w = make_weather(feel_mean=14, feel_min=10, feel_max=18, pop=80)
        results, _ = self.recs(w)
        self.assertTrue(results)
        items = [o["item"] for o in results[0]["outfit"]]
        has = any(i.get("waterproof") for i in items
                  if i["slot"] in ("outer", "shoes")) or any(
                      i.get("category") == "umbrella" for i in items)
        self.assertTrue(has, "高降水概率应推荐防水外层或伞")

    def test_top3_are_diverse(self):
        """回归：曾经三个方案只差一件内层。"""
        w = make_weather(feel_mean=10, feel_min=6, feel_max=14)
        results, _ = self.recs(w)
        if len(results) >= 3:
            sig = set()
            for r in results:
                outer = next((o["item"]["id"] for o in r["outfit"]
                              if o["slot"] == "outer"), None)
                bottom = next((o["item"]["id"] for o in r["outfit"]
                               if o["slot"] == "bottom"), None)
                sig.add((outer, bottom))
            self.assertGreater(len(sig), 1, "Top3 方案缺少差异")

    def test_sport_outfit_has_no_business_wear(self):
        """回归：曾经把衬衫西裤当成运动装备。"""
        w = make_weather(feel_mean=10, feel_min=6, feel_max=14)
        events = [{"start": "17:30", "title": "健身房"}]
        _, extra = self.recs(w, events)
        sport = extra["sport_outfit"]
        self.assertTrue(sport)
        for o in sport:
            self.assertLessEqual(o["item"]["formality"], 1,
                                 f"运动套装混入正装：{o['item']['name']}")

    def test_dirty_items_excluded(self):
        wd = copy.deepcopy(WARDROBE)
        dirty_ids = set()
        for it in wd:
            if it["slot"] == "outer":
                it["status"] = "dirty"
                dirty_ids.add(it["id"])
        w = make_weather(feel_mean=10, feel_min=6, feel_max=14)
        results, _ = self.recs(w, wardrobe=wd)
        if results:
            for r in results:
                for o in r["outfit"]:
                    self.assertNotIn(o["item"]["id"], dirty_ids)

    def test_freshness_penalizes_recent_wear(self):
        wd = copy.deepcopy(WARDROBE)
        for it in wd:
            if it["id"] == "w001":
                it["last_worn"] = "2026-11-05"
        self.assertLess(REC.freshness_score(0), REC.freshness_score(10))

    def test_reasons_present_and_mention_item(self):
        w = make_weather(feel_mean=10, feel_min=6, feel_max=14)
        results, _ = self.recs(w)
        for o in results[0]["outfit"]:
            self.assertTrue(o["reason"])
            self.assertIn(o["item"]["name"], o["reason"])


class TestTimeline(unittest.TestCase):
    def test_segments_merge_similar_occasions(self):
        w = make_weather(feel_mean=12, feel_min=8, feel_max=16)
        events = [{"start": "09:30", "end": "10:00", "title": "部门例会"},
                  {"start": "11:00", "end": "12:00", "title": "客户方案沟通"},
                  {"start": "14:00", "end": "16:00", "title": "项目数据整理"},
                  {"start": "17:30", "end": "18:30", "title": "健身房"}]
        segs = TL.build_segments(events, w)
        # 正式段(例会被客户沟通抬到4) / 工位段(2) / 运动段，共3段
        self.assertEqual(len(segs), 3, "相邻相近场合应合并，运动单独成段")
        self.assertEqual(segs[0]["formality"], 4, "合并后正式度应取最高")
        self.assertEqual(segs[0]["tag"], C.FORMALITY_LABELS[4], "合并后标签必须更新")
        self.assertTrue(segs[-1]["sport"])

    def test_window_weather_uses_segment_hours(self):
        w = make_weather(feel_mean=10, feel_min=2, feel_max=18)
        seg = TL.window_weather(w, 9, 12)
        self.assertNotEqual(seg["feel_mean"], w["feel_mean"],
                            "时段天气应区别于全天均温")
        self.assertIn("window_hours", seg)

    def test_no_change_reuses_previous_outfit(self):
        """回归：曾经场合几乎相同的两段选出完全不同的衣服，
        却标记'不用换装'。

        现在进一步要求：判定「不用换」之后，两段要并成一段——
        上午正装穿到下午工位，展示成两张卡等于让用户以为要回家换衣服。"""
        w = make_weather(feel_mean=12, feel_min=9, feel_max=16)
        events = [{"start": "09:30", "end": "10:00", "title": "部门例会"},
                  {"start": "11:00", "end": "12:00", "title": "客户方案沟通"},
                  {"start": "14:00", "end": "16:00", "title": "项目数据整理"},
                  {"start": "17:30", "end": "18:30", "title": "健身房"}]
        plan = TL.plan_day(WARDROBE, events, w)
        self.assertEqual(plan["segment_count"], 2,
                         "上午正装与下午工位同一套，应并为一段；运动单独成段")
        day, sport = plan["segments"]
        self.assertFalse(day["change_needed"], "第一段没有上一套，不该要求换装")
        self.assertEqual(day["time_start"], "09:30")
        self.assertEqual(day["time_end"], "16:00", "合并后应覆盖到最后一段结束")
        self.assertIn("项目数据整理", day["events"], "合并后事件清单要带上后面那段")
        self.assertTrue(sport["change_needed"], "运动段必须换装")
        self.assertTrue(sport["changes"], "换装段应列出逐层变动")

    def test_multi_segment_reuse_when_no_change(self):
        w = make_weather(feel_mean=12, feel_min=9, feel_max=16)
        events = [{"start": "09:00", "end": "10:00", "title": "部门例会"},
                  {"start": "10:30", "end": "11:30", "title": "项目评审"},
                  {"start": "12:00", "end": "13:00", "title": "正式签约"},
                  {"start": "15:00", "end": "16:00", "title": "项目数据整理"}]
        plan = TL.plan_day(WARDROBE, events, w)
        for seg in plan["segments"]:
            if not seg["change_needed"] and seg is not plan["segments"][0]:
                self.assertEqual(seg["changes"], [], "判定不用换时不应还有变动")

    def test_change_detects_temperature_drop(self):
        w = make_weather(feel_mean=15, feel_min=2, feel_max=28)
        events = [{"start": "09:00", "end": "10:00", "title": "部门例会"},
                  {"start": "20:00", "end": "21:00", "title": "散步"}]
        segs = TL.build_segments(events, w)
        if len(segs) >= 2:
            plan = TL.plan_day(WARDROBE, events, w)
            self.assertTrue(any(s["change_needed"] or s["change_reasons"]
                                for s in plan["segments"]))

    def test_empty_schedule_single_segment(self):
        w = make_weather(feel_mean=12)
        plan = TL.plan_day(WARDROBE, [], w)
        self.assertEqual(plan["segment_count"], 1)
        self.assertFalse(plan["needs_change"])


class TestPhotoImport(unittest.TestCase):
    """文件名启发式推断。不写真实衣橱。"""
    def setUp(self):
        import import_photos as IP
        self.IP = IP

    def test_common_items(self):
        cases = [
            ("藏青长袖衬衫.jpg", "base", "shirt", 0.20, 3),
            ("黑色厚羽绒服.jpg", "outer", "down_jacket", 1.20, 2),
            ("米白薄针织衫.jpg", "mid", "sweater", 0.24, 2),
            ("灰色卫衣.jpg", "mid", "hoodie", 0.38, 1),
            ("黑色皮质德比鞋.jpg", "shoes", "shoes_leather", 0.18, 4),
        ]
        for fn, slot, cat, clo, fml in cases:
            it, conf, _ = self.IP.infer(fn)
            self.assertEqual(it["slot"], slot, fn)
            self.assertEqual(it["category"], cat, fn)
            self.assertAlmostEqual(it["clo"], clo, places=2, msg=fn)
            self.assertEqual(it["formality"], fml, fn)
            self.assertEqual(conf, "高", fn)

    def test_thickness_not_double_counted(self):
        """回归：'厚毛衣' 曾被品类基准和厚度系数连乘两次。"""
        it, _, _ = self.IP.infer("黑色厚毛衣.jpg")
        self.assertAlmostEqual(it["clo"], 0.50, places=2)

    def test_black_not_false_warned(self):
        """回归：真正的黑色被误报'未识别颜色'。"""
        _, conf, warns = self.IP.infer("黑色羽绒服.jpg")
        self.assertEqual(conf, "高")
        self.assertFalse(any("颜色" in w for w in warns))

    def test_uninformative_filename_flagged(self):
        it, conf, warns = self.IP.infer("IMG_1234.jpg")
        self.assertEqual(conf, "低")
        self.assertEqual(it["category"], "unknown")
        self.assertTrue(warns)
        self.assertTrue(it["needs_review"])

    def test_waterproof_flags(self):
        it, _, _ = self.IP.infer("藏青防风冲锋衣.jpg")
        self.assertTrue(it["waterproof"])
        self.assertTrue(it["windproof"])


class TestPayload(unittest.TestCase):
    def test_build_payload_complete(self):
        import run
        w = make_weather(feel_mean=10, feel_min=5, feel_max=15)
        payload = run.build_payload(WARDROBE, [], w, today=TODAY)
        for key in ("date", "weather", "context", "band", "recommendations",
                    "timeline", "sport_outfit", "wardrobe_count"):
            self.assertIn(key, payload)
        self.assertEqual(payload["band"]["label"], "8 – 15℃")
        self.assertEqual(payload["wardrobe_count"], len(WARDROBE))
        self.assertTrue(payload["timeline"]["segments"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
