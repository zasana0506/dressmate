# -*- coding: utf-8 -*-
"""衣橱不齐时的「临时方案 + 缺口清单」。

衣服没录全就什么都不给，是这类 App 劝退人的第一大原因：
用户刚装、只传了三五件，一打开就是「请补充单品」，于是再也不打开。
但反过来硬凑一套更糟——15℃ 给一件 0.92 clo 的羽绒服，
用户穿出去一次就知道这 App 不懂衣服。

所以这一层的边界只有两条：
1. 能穿的部分照给，但必须自己承认缺哪几层；
2. 保暖值对不上的单品绝不进方案，宁可说「你有羽绒服但太厚了」。
"""
import json
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from engine import config as C          # noqa: E402
from engine import context as CTX       # noqa: E402
from engine import recommend as REC     # noqa: E402

FIXTURE = os.path.join(BASE_DIR, "tests", "fixtures", "wardrobe.json")


def wx(tmin, tmax):
    return {
        "date": "2026-11-06", "feel_min": tmin, "feel_max": tmax,
        "feel_mean": round((tmin + tmax) / 2, 1),
        "daily": {"tmax": tmax + 2, "tmin": tmin - 2, "feels_max": tmax, "feels_min": tmin,
                  "pop_max": 0, "precip_sum": 0, "wind_max": 8, "uv_max": 2,
                  "code": 0, "desc": "晴"},
        "hours": [], "stale": False,
    }


def item(iid, slot, clo, formality=1, color="黑"):
    return {"id": iid, "name": iid, "slot": slot, "clo": clo, "formality": formality,
            "color": color, "status": "clean", "season": ["spring", "autumn", "winter"]}


def cand(it, fit):
    return {"item": it, "slot": it["slot"], "warm_fit": fit, "formal": it.get("formality", 1),
            "formal_gap": 0, "state": "clean", "days": 5}


def run(items, w):
    ctx = CTX.build_context([], w)
    return REC.recommend(items, ctx, w, top_n=3)


class TestPartialOutfit(unittest.TestCase):
    def test_complete_wardrobe_is_not_partial(self):
        with open(FIXTURE, encoding="utf-8") as f:
            items = json.load(f)["items"]
        recs, _, extra = run(items, wx(14, 21))
        self.assertTrue(recs, "齐套衣橱应该正常出方案")
        self.assertFalse(recs[0]["partial"])
        self.assertEqual(recs[0]["missing"], [])
        self.assertFalse(extra.get("partial"))

    def test_missing_inner_and_shoes_still_gives_outfit(self):
        """只剩外套/中层/下装：给一套能穿的，并标出缺内层和鞋。"""
        items = [
            item("羽绒服", "outer", 0.92), item("卫衣", "mid", 0.38),
            item("长裤", "bottom", 0.22),
        ]
        recs, _, extra = run(items, wx(2, 10))
        self.assertTrue(recs, "缺两层也该给出能穿的部分")
        r = recs[0]
        self.assertTrue(r["partial"])
        self.assertIn("内层", r["missing"])
        self.assertIn("鞋履", r["missing"])
        self.assertIn("临时方案", r["label"])
        self.assertEqual(extra.get("partial"), True)

    def test_two_pieces_are_not_an_outfit(self):
        """两件半套不叫方案：只给缺口清单，不假装有搭配。"""
        items = [item("羽绒服", "outer", 0.92), item("长裤", "bottom", 0.22)]
        recs, _, extra = run(items, wx(2, 10))
        self.assertEqual(recs, [])
        self.assertTrue(extra.get("gaps"))

    def test_too_warm_item_never_used(self):
        """16℃ 只有羽绒服：宁可说「外层太厚」，也不能把它塞进方案。"""
        items = [item("羽绒服", "outer", 0.92), item("长裤", "bottom", 0.22),
                 item("长袖T", "base", 0.20), item("运动鞋", "shoes", 0.2)]
        recs, _, extra = run(items, wx(13, 19))
        for r in recs:
            names = [o["item"]["name"] for o in r["outfit"]]
            self.assertNotIn("羽绒服", names, "0.92 clo 的外套不该出现在 16℃ 的方案里")
        outer = next(g for g in extra["gaps"] if g["slot"] == "outer")
        self.assertEqual(outer["reason"], "mismatch")
        self.assertIn("太厚", outer["note"])
        self.assertIn("羽绒服", outer["note"])


    def test_label_does_not_dress_up_a_hoodie(self):
        """日程要求正式场合、衣橱只到休闲时，标题不能还写「正式场合全套」。"""
        items = [item("卫衣", "mid", 0.38, 1), item("运动裤", "bottom", 0.22, 1),
                 item("长袖T", "base", 0.20, 1), item("运动鞋", "shoes", 0.2, 1),
                 item("薄外套", "outer", 0.42, 1)]
        w = wx(9, 16)
        ctx = CTX.build_context(
            [{"title": "客户方案沟通", "note": "外部客户，需要正式一些",
              "start": "10:00", "end": "11:00"}], w)
        self.assertEqual(ctx["formality"], 4)
        recs, _, _ = REC.recommend(items, ctx, w, top_n=1)
        self.assertTrue(recs)
        self.assertIn("只到", recs[0]["label"], "降级方案要在标题里承认衣橱的上限")
        self.assertNotEqual(recs[0]["label"], "正式场合全套")


class TestGaps(unittest.TestCase):
    def pools(self, **slots):
        p = {s: [] for s in C.SLOT_ORDER}
        p.update(slots)
        return p

    def test_only_reports_layers_needed_today(self):
        """30℃ 只需要内层+下装+鞋，不该催人买大衣。"""
        w = wx(26, 32)
        ctx = CTX.build_context([], w)
        gaps = REC.slot_gaps(self.pools(), ctx, w)
        slots = {g["slot"] for g in gaps}
        self.assertNotIn("outer", slots)
        self.assertNotIn("mid", slots)
        self.assertIn("base", gaps and slots)

    def test_empty_vs_mismatch(self):
        w = wx(2, 10)
        ctx = CTX.build_context([], w)
        p = self.pools(outer=[cand(item("羽绒服", "outer", 0.92), 0.0)])
        gaps = {g["slot"]: g for g in REC.slot_gaps(p, ctx, w)}
        self.assertEqual(gaps["base"]["reason"], "empty")
        self.assertEqual(gaps["outer"]["reason"], "mismatch")
        self.assertEqual(gaps["outer"]["have"], ["羽绒服"])
        self.assertTrue(gaps["outer"]["range"][0] < gaps["outer"]["range"][1])

    def test_hint_wording_follows_temperature(self):
        """30℃ 说短袖，0℃ 说保暖内衣，不能全年一套话术。"""
        words = {t: REC.slot_gaps(self.pools(), CTX.build_context([], wx(*t)), wx(*t))
                 for t in ((26, 32), (-3, 4))}
        hot = next(g for g in words[(26, 32)] if g["slot"] == "base")["hint"]
        cold = next(g for g in words[(-3, 4)] if g["slot"] == "base")["hint"]
        self.assertIn("短袖", hot)
        self.assertIn("保暖内衣", cold)

    def test_slot_gaps_never_crashes_on_empty_pools(self):
        """空池也要给出缺口，不能抛异常——这是打开就崩的那类 bug。"""
        gaps = REC.slot_gaps({}, {}, {"feel_mean": 10, "daily": {}})
        self.assertTrue(gaps)
        self.assertTrue(all(g["reason"] == "empty" for g in gaps))

    def test_gaps_note_mentions_count(self):
        w = wx(2, 10)
        gaps = REC.slot_gaps(self.pools(), CTX.build_context([], w), w)
        note = REC.gaps_note(gaps)
        self.assertIn(str(len(gaps)), note)
        self.assertIn("clo", note)


if __name__ == "__main__":
    unittest.main()
