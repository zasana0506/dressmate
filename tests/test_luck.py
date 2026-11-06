# -*- coding: utf-8 -*-
"""紫微斗数幸运穿搭的回归测试。

排盘本身交给 iztro，这里只测「盘 → 颜色/款式」的翻译层，
以及一条硬要求：**主色和避讳色不能是同一个颜色**——
早期版本真出现过「建议穿墨绿，同时建议避开墨绿」，用户只会觉得在胡扯。
"""
import os
import shutil
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from engine import luck as LUCK  # noqa: E402


def raw_with(star="天机", brightness="旺", branch="未", mutagen=None,
             soul_stars=None, opposite=None):
    return {
        "ok": True,
        "soul": "巨门",
        "five_elements_class": "土五局",
        "lunar_date": "二〇二六年九月廿七",
        "daily": {
            "stem": "癸", "branch": branch, "palace_branch": branch,
            "mutagen": mutagen if mutagen is not None else ["破军", "巨门", "太阴", "贪狼"],
            "soul_stars": soul_stars if soul_stars is not None else [
                {"name": star, "brightness": brightness, "mutagen": ""}],
            "opposite_stars": opposite or [],
        },
    }


class TestMappingTables(unittest.TestCase):
    def test_all_main_stars_mapped(self):
        stars = ["紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府",
                 "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军"]
        for s in stars:
            self.assertIn(s, LUCK.STAR_ELEMENT, f"{s} 缺五行映射")
            self.assertIn(s, LUCK.STAR_STYLE, f"{s} 缺款式映射")
            self.assertIn(LUCK.STAR_ELEMENT[s], LUCK.ELEMENT_COLORS,
                          f"{s} 的五行没有对应颜色")

    def test_all_branches_mapped(self):
        for b in "子丑寅卯辰巳午未申酉戌亥":
            self.assertIn(b, LUCK.BRANCH_ELEMENT)

    def test_colors_use_known_families(self):
        """颜色 family 必须是衣橱配色表认识的，否则加权永远不命中。"""
        from engine import config as C
        for el, info in LUCK.ELEMENT_COLORS.items():
            self.assertIn(info["family"], C.COLOR_FAMILY.values(),
                          f"{el} 的 family「{info['family']}」不在衣橱色系表里")


class TestTranslate(unittest.TestCase):
    def test_basic(self):
        r = LUCK.translate(raw_with(), "2026-11-05")
        self.assertTrue(r["ok"])
        self.assertEqual(r["star"], "天机")
        self.assertEqual(r["star_element"], "木")
        self.assertTrue(r["lucky_colors"])
        self.assertTrue(r["style_tip"])
        self.assertIn("参考", r["disclaimer"])

    def test_main_never_equals_avoid(self):
        """主色与避讳色撞车时必须自动改道。"""
        # 天机属木，贪狼也属木 → 化忌落在同一五行
        r = LUCK.translate(raw_with(star="天机",
                                    mutagen=["破军", "巨门", "太阴", "贪狼"]), "2026-11-05")
        self.assertTrue(r["ok"])
        if r.get("avoid_desc"):
            self.assertNotEqual(r["lucky_desc"], r["avoid_desc"],
                                "主色和避讳色成了同一个，建议自相矛盾")

    def test_borrow_opposite_when_empty(self):
        r = LUCK.translate(raw_with(soul_stars=[],
                                    opposite=[{"name": "天梁", "brightness": "旺"}]), "2026-11-05")
        self.assertTrue(r["ok"])
        self.assertTrue(r["borrowed"], "空宫应借对宫并标注")
        self.assertEqual(r["star"], "天梁")

    def test_brightness_strength(self):
        self.assertEqual(LUCK.translate(raw_with(brightness="庙"), "2026-11-05")["strength"], "strong")
        self.assertEqual(LUCK.translate(raw_with(brightness="陷"), "2026-11-05")["strength"], "weak")

    def test_bad_raw(self):
        r = LUCK.translate({"ok": False, "error": "排盘失败"}, "2026-11-05")
        self.assertFalse(r["ok"])
        self.assertIn("失败", r["error"])

    def test_tips_are_strings(self):
        r = LUCK.translate(raw_with(), "2026-11-05")
        for t in r["tips"]:
            self.assertIsInstance(t, str)
            self.assertTrue(t.strip())


class TestProfile(unittest.TestCase):
    def test_no_profile(self):
        r = LUCK.daily_luck({})
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("need_profile"))


@unittest.skipUnless(shutil.which("node"), "需要 Node.js 才能排盘")
class TestBridge(unittest.TestCase):
    """真排一次盘，确认桥接与 iztro 的接口没变。"""

    def test_real_chart(self):
        raw = LUCK.run_bridge("1990-05-05", 6, "男", "2026-11-05")
        self.assertTrue(raw.get("ok"), raw.get("error"))
        self.assertEqual(raw["soul"], "巨门")
        self.assertTrue(raw["daily"]["palace_branch"])
        self.assertIn("二〇二六", raw["lunar_date"],
                      "农历日期应是今天，不是出生那天")

    def test_bad_date(self):
        raw = LUCK.run_bridge("不是日期", 6, "男", "2026-11-05")
        self.assertFalse(raw.get("ok"))


if __name__ == "__main__":
    unittest.main()
