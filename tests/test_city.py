# -*- coding: utf-8 -*-
"""城市解析测试。

这一层要解决的具体问题：Open-Meteo 的地理编码对中文名不可靠——
查「东莞」返回 20.30/109.99（雷州半岛某个镇），真实东莞是 23.02/113.75。
所以不能直接把用户输入丢给在线接口，必须先查本地表；表里没有才联网，
联网也要校验 feature_code 是行政中心。

测试重点：
1. 用户各种写法（北京市 / beijing / 带空格）都能落到同一座城；
2. 已知城市必须返回**正确的坐标**，不是「有个坐标就行」；
3. 表里没有的城市不会瞎猜一个点位，而是返回 None。
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: F401  测试环境隔离（不读本机真实档案）

from engine import city as CITY   # noqa: E402


class TestNormalize(unittest.TestCase):
    def test_strip_city_suffix(self):
        self.assertEqual(CITY.normalize("北京市"), "北京")
        self.assertEqual(CITY.normalize("东莞市"), "东莞")

    def test_old_slug_still_works(self):
        """老版本存在浏览器里的城市是拼音，不能升级后全变无效。"""
        self.assertEqual(CITY.normalize("beijing"), "北京")
        self.assertEqual(CITY.normalize("Harbin"), "哈尔滨")

    def test_spaces_and_empty(self):
        self.assertEqual(CITY.normalize("  上海  "), "上海")
        self.assertEqual(CITY.normalize(""), "")
        self.assertEqual(CITY.normalize(None), "")

    def test_short_name_not_broken(self):
        """「市」只有一个字的地名不能被切成空串。"""
        self.assertEqual(CITY.normalize("市"), "市")


class TestResolve(unittest.TestCase):
    def setUp(self):
        self._orig = CITY._table
        # 用固定表，避免测试依赖 data/cities.json 的抓取进度
        CITY._table = {
            "北京": {"lat": 39.9042, "lon": 116.4074, "province": "北京", "name": "北京市"},
            "东莞": {"lat": 23.018, "lon": 113.7487, "province": "广东", "name": "东莞市"},
            "上海": {"lat": 31.2304, "lon": 121.4737, "province": "上海", "name": "上海市"},
        }

    def tearDown(self):
        CITY._table = self._orig

    def test_resolve_returns_real_coordinates(self):
        """东莞必须是 23.02/113.75，不是在线接口给的 20.30/109.99。"""
        info = CITY.resolve("东莞")
        self.assertAlmostEqual(info["lat"], 23.018, places=2)
        self.assertAlmostEqual(info["lon"], 113.7487, places=2)
        self.assertEqual(info["province"], "广东")

    def test_resolve_accepts_suffix_and_slug(self):
        for name in ("北京市", "北京", "beijing", "  北京 "):
            info = CITY.resolve(name, allow_online=False)
            self.assertIsNotNone(info, f"{name} 应该能解析")
            self.assertEqual(info["key"], "北京")

    def test_unknown_is_none_not_guess(self):
        """表里没有、又不许联网时，宁可返回 None，也不能给一个假坐标。"""
        self.assertIsNone(CITY.resolve("不存在的地名", allow_online=False))

    def test_empty_input(self):
        self.assertIsNone(CITY.resolve("", allow_online=False))


class TestSearch(unittest.TestCase):
    def setUp(self):
        self._orig = CITY._table
        CITY._table = {
            "北京": {"lat": 39.9, "lon": 116.4, "province": "北京", "name": "北京市"},
            "北海": {"lat": 21.48, "lon": 109.12, "province": "广西", "name": "北海市"},
            "东莞": {"lat": 23.02, "lon": 113.75, "province": "广东", "name": "东莞市"},
            "佛山": {"lat": 23.03, "lon": 113.13, "province": "广东", "name": "佛山市"},
            "广州": {"lat": 23.13, "lon": 113.26, "province": "广东", "name": "广州市"},
        }

    def tearDown(self):
        CITY._table = self._orig

    def test_exact_match_first(self):
        """搜「北海」时北海必须排第一，不能被「北京」抢在前面。"""
        hits = CITY.search("北海")
        self.assertEqual(hits[0]["key"], "北海")

    def test_prefix_matches(self):
        keys = [h["key"] for h in CITY.search("北")]
        self.assertIn("北京", keys)
        self.assertIn("北海", keys)

    def test_search_by_province(self):
        """搜「广东」应该把广东的城市都列出来——用户不一定记得市名。"""
        keys = [h["key"] for h in CITY.search("广东")]
        self.assertEqual(set(keys), {"东莞", "佛山", "广州"})

    def test_empty_query_returns_all(self):
        self.assertEqual(len(CITY.all_cities()), 5)

    def test_no_match_returns_empty(self):
        self.assertEqual(CITY.search("多伦多"), [])


class TestTableSafety(unittest.TestCase):
    def test_missing_file_returns_empty_dict(self):
        """数据文件缺失时不能抛异常，否则服务起不来。"""
        self.assertIsInstance(CITY._read(), dict)

    def test_all_cities_shape(self):
        for c in CITY.all_cities():
            self.assertIn("key", c)
            self.assertIn("name", c)
            self.assertIn("lat", c)
            self.assertIn("lon", c)


if __name__ == "__main__":
    unittest.main()
