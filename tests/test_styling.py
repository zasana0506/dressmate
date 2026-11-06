# -*- coding: utf-8 -*-
"""穿搭铁律测试：三个搭配师技能落到代码上的那几条规矩。

覆盖：色系上限、鞋跳色、运动鞋配西裤/大衣、深褐配黑、绿配红、
内外中间态、上深下浅、配饰堆叠、结论分级，以及与总分的接线。
"""
import datetime
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: F401  测试环境隔离（不读本机真实档案）

from engine import config as C        # noqa: E402
from engine import recommend as REC   # noqa: E402
from engine import styling as STY     # noqa: E402

TODAY = datetime.date(2026, 11, 5)


def item(name, slot, category, color, formality=3, clo=0.3, material="棉"):
    return {"id": name, "name": name, "slot": slot, "category": category,
            "color": color, "material": material, "clo": clo,
            "formality": formality, "season": ["autumn", "winter"],
            "status": "clean", "last_worn": None, "photo": ""}


def chosen(*items):
    """把单品列表包成 audit 要的 chosen 结构。"""
    return [{"slot": it["slot"], "item": it, "warm_fit": 0.9,
             "formal": it["formality"], "days": 30} for it in items]


def ctx(req=2):
    return {"formality": req, "formality_label": C.FORMALITY_LABELS[req],
            "slot_temp": {"base": 8, "mid": 8, "outer": 2, "bottom": 8, "shoes": 8}}


def weather(feel=8.0):
    hours = [{"hour": h, "apparent": feel, "temp": feel + 1, "pop": 0,
              "wind": 6, "uv": 2, "code": 0} for h in range(24)]
    return {"date": "2026-11-05",
            "current": {"apparent": feel, "temp": feel + 1, "humidity": 50,
                        "precip": 0, "code": 0, "wind": 6, "desc": "晴"},
            "daily": {"tmax": feel + 3, "tmin": feel - 3, "feels_max": feel + 3,
                      "feels_min": feel - 3, "pop_max": 0, "precip_sum": 0,
                      "wind_max": 6, "uv_max": 2, "code": 0, "desc": "晴"},
            "hours": hours, "feel_max": feel + 3, "feel_min": feel - 3,
            "feel_mean": feel, "stale": False}


class TestCleanOutfit(unittest.TestCase):
    def test_neutral_three_piece_is_clean(self):
        """藏青+灰+黑：两个无色加一个藏青，不触发任何铁律。"""
        r = STY.audit(chosen(
            item("藏青衬衫", "base", "shirt", "藏青"),
            item("灰西裤", "bottom", "dress_pants", "灰"),
            item("黑皮鞋", "shoes", "shoes_leather", "黑"),
        ), ctx())
        self.assertEqual(r["verdict"], "行")
        self.assertEqual(r["score"], 1.0)

    def test_neutrals_do_not_occupy_color_slots(self):
        """黑白灰是无色系：白衬衫+灰裤+驼鞋+藏青外套不该判成四色。"""
        r = STY.audit(chosen(
            item("白衬衫", "base", "shirt", "白"),
            item("灰西裤", "bottom", "dress_pants", "灰"),
            item("驼鞋", "shoes", "shoes_leather", "驼"),
            item("藏青外套", "outer", "blazer", "藏青"),
        ), ctx())
        self.assertNotIn("three_colors", [i["code"] for i in r["issues"]])


class TestColorRules(unittest.TestCase):
    def test_four_accents_penalized(self):
        r = STY.audit(chosen(
            item("黄衬衫", "base", "shirt", "黄"),
            item("绿西裤", "bottom", "dress_pants", "绿"),
            item("红外套", "outer", "coat", "红"),
            item("紫鞋", "shoes", "shoes_leather", "紫"),
        ), ctx())
        codes = [i["code"] for i in r["issues"]]
        self.assertIn("three_colors", codes)
        self.assertLess(r["score"], 0.8)
        self.assertTrue(any("色系" in p for p in r["pitfalls"]))

    def test_shoe_jumping_out(self):
        """鞋单独跳一个颜色会散：白衬衫+黑西裤+红鞋。"""
        r = STY.audit(chosen(
            item("白衬衫", "base", "shirt", "白"),
            item("黑西裤", "bottom", "dress_pants", "黑"),
            item("红皮鞋", "shoes", "shoes_leather", "红"),
        ), ctx())
        self.assertIn("shoe_jump", [i["code"] for i in r["issues"]])
        self.assertTrue(any("红皮鞋" in p for p in r["pitfalls"]))

    def test_deep_brown_with_black(self):
        """深褐配黑互相吞掉（色彩铁律第 14 条）。"""
        r = STY.audit(chosen(
            item("褐衬衫", "base", "shirt", "褐"),
            item("黑西裤", "bottom", "dress_pants", "黑"),
            item("黑皮鞋", "shoes", "shoes_leather", "黑"),
        ), ctx())
        self.assertIn("steal_color", [i["code"] for i in r["issues"]])

    def test_green_with_red(self):
        """绿色硬配红属于高风险组合。"""
        r = STY.audit(chosen(
            item("绿针织衫", "base", "shirt", "绿"),
            item("红长裤", "bottom", "trousers", "红"),
            item("黑皮鞋", "shoes", "shoes_leather", "黑"),
        ), ctx())
        self.assertIn("green_risk", [i["code"] for i in r["issues"]])

    def test_middle_tone_outer(self):
        """内外两件套卡在中间态：浅灰配驼，色系不同但明度几乎一样。"""
        r = STY.audit(chosen(
            item("浅灰针织衫", "base", "shirt", "浅灰"),
            item("驼大衣", "outer", "coat", "驼"),
            item("黑西裤", "bottom", "dress_pants", "黑"),
            item("黑皮鞋", "shoes", "shoes_leather", "黑"),
        ), ctx())
        self.assertIn("middle_tone", [i["code"] for i in r["issues"]])

    def test_tone_direction_only_matters_in_formal(self):
        """上深下浅在日常没问题，一档正式场合显得不够正式。"""
        outfit = chosen(
            item("藏青衬衫", "base", "shirt", "藏青"),
            item("浅灰西裤", "bottom", "dress_pants", "浅灰"),
            item("黑皮鞋", "shoes", "shoes_leather", "黑"),
        )
        self.assertNotIn("tone_up_dark", [i["code"] for i in STY.audit(outfit, ctx(2))["issues"]])
        self.assertIn("tone_up_dark", [i["code"] for i in STY.audit(outfit, ctx(4))["issues"]])


class TestShoeFormality(unittest.TestCase):
    def test_sneaker_with_dress_pants(self):
        r = STY.audit(chosen(
            item("白衬衫", "base", "shirt", "白"),
            item("黑西裤", "bottom", "dress_pants", "黑"),
            item("白运动鞋", "shoes", "shoes_sneakers", "白"),
        ), ctx())
        self.assertIn("sneaker_dress_pants", [i["code"] for i in r["issues"]])
        self.assertTrue(any("皮鞋" in p for p in r["pitfalls"]))

    def test_sneaker_with_coat(self):
        r = STY.audit(chosen(
            item("藏青衬衫", "base", "shirt", "藏青"),
            item("黑牛仔裤", "bottom", "jeans", "黑"),
            item("藏青大衣", "outer", "coat", "藏青"),
            item("白运动鞋", "shoes", "shoes_sneakers", "白"),
        ), ctx(2))
        self.assertIn("sneaker_tailored_outer", [i["code"] for i in r["issues"]])

    def test_formal_hits_both_rules(self):
        """西裤+大衣+运动鞋：两条都命中，结论要掉到「将就」。"""
        r = STY.audit(chosen(
            item("藏青衬衫", "base", "shirt", "藏青"),
            item("黑西裤", "bottom", "dress_pants", "黑"),
            item("藏青大衣", "outer", "coat", "藏青"),
            item("白运动鞋", "shoes", "shoes_sneakers", "白"),
        ), ctx(4))
        self.assertEqual(r["verdict"], "这身将就")
        self.assertLess(r["score"], 0.3)


class TestVerdictLevel(unittest.TestCase):
    def test_single_minor_issue_is_change_one_item(self):
        r = STY.audit(chosen(
            item("黑衬衫", "base", "shirt", "黑"),
            item("藏青长裤", "bottom", "trousers", "藏青"),
            item("红皮鞋", "shoes", "shoes_leather", "红"),
        ), ctx())
        self.assertEqual(r["verdict"], "换一件就行")
        self.assertLessEqual(len(r["pitfalls"]), 3, "坑不超过三条，改不完等于没改")


class TestFormalityZero(unittest.TestCase):
    def test_home_is_zero_not_two(self):
        """正式度 0 是合法值：写成 `int(ctx.get('formality') or 2)` 会把居家当成办公。"""
        r = STY.audit(chosen(
            item("藏青衬衫", "base", "shirt", "藏青"),
            item("黑运动裤", "bottom", "gym_pants", "黑"),
            item("卡其大衣", "outer", "coat", "卡其"),
            item("白运动鞋", "shoes", "running_shoes", "白"),
        ), ctx(0))
        self.assertNotIn("sneaker_tailored_outer", [i["code"] for i in r["issues"]])


class TestTierDrop(unittest.TestCase):
    """两个技能都点名：鞋和外套最容易掉档，要单独查。"""

    def test_shoe_drops_tier(self):
        r = STY.audit(chosen(
            item("白衬衫", "base", "shirt", "白", 4),
            item("黑西裤", "bottom", "dress_pants", "黑", 4),
            item("灰板鞋", "shoes", "shoes_sneakers", "灰", 1),
        ), ctx(4))
        self.assertIn("shoe_drops_tier", [i["code"] for i in r["issues"]])
        self.assertTrue(any("一双鞋" in p for p in r["pitfalls"]))

    def test_formal_shoe_is_fine(self):
        r = STY.audit(chosen(
            item("白衬衫", "base", "shirt", "白", 4),
            item("黑西裤", "bottom", "dress_pants", "黑", 4),
            item("黑皮鞋", "shoes", "shoes_leather", "黑", 4),
        ), ctx(4))
        self.assertNotIn("shoe_drops_tier", [i["code"] for i in r["issues"]])


class TestLane(unittest.TestCase):
    def test_lane_follows_wardrobe(self):
        self.assertEqual(STY.lane([item("半裙", "bottom", "skirt", "灰")]), "women")
        self.assertEqual(STY.lane([item("西裤", "bottom", "dress_pants", "黑")]), "men")


class TestWiring(unittest.TestCase):
    """铁律必须真的进总分，否则只是摆设。"""

    def _score(self, sneaker):
        chosen_list = chosen(
            item("白衬衫", "base", "shirt", "白"),
            item("黑西裤", "bottom", "dress_pants", "黑"),
            item("灰针织衫", "mid", "sweater", "灰"),
            item("藏青大衣", "outer", "coat", "藏青"),
            item("白运动鞋" if sneaker else "黑皮鞋", "shoes",
                 "shoes_sneakers" if sneaker else "shoes_leather",
                 "白" if sneaker else "黑"),
        )
        return REC.score_combo(chosen_list, ctx(3), weather(),
                               ["base", "mid", "outer"], allow_missing=True)

    def test_style_enters_total_score(self):
        leather = self._score(False)
        sneaker = self._score(True)
        self.assertIn("style", leather["parts"])
        self.assertEqual(leather["parts"]["style"], 1.0)
        self.assertLess(sneaker["parts"]["style"], 0.5)
        self.assertLess(sneaker["score"], leather["score"],
                        "运动鞋配西裤必须真的拉低总分")


    def test_violation_is_not_rounding_error(self):
        """一条硬伤要值 8% 以上：减法口径下它只值 0.03，会被保暖的细微差异顶掉。"""
        leather = self._score(False)
        sneaker = self._score(True)
        self.assertLess(sneaker["score"], leather["score"] * 0.92)


if __name__ == "__main__":
    unittest.main()
