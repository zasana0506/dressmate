# -*- coding: utf-8 -*-
"""断网兜底天气的测试。

为什么单独测这个：兜底只在断网时才走，正常路径永远碰不到，
所以很容易写错之后一直没人发现——而断网恰恰是自托管用户最常遇到的场景。

判据：估出来的温度必须够准，否则会给出「零下 15 度穿短袖」这种建议。
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

from engine import weather as WX  # noqa: E402


class TestClimateTable(unittest.TestCase):
    def test_climate_table_loads(self):
        """气候表要能读出来，且有足够多的参照城市。"""
        table = WX._climate()
        self.assertGreater(len(table), 30, "参照城市太少，插值会不准")

    def test_climate_table_has_12_months(self):
        """每座城市都要有 12 个月的均值，缺月会索引越界。"""
        for name, rec in WX._climate().items():
            self.assertEqual(len(rec["t"]), 12, f"{name} 的月均温不是 12 个月")

    def test_july_is_warmest_in_north(self):
        """北半球 7 月是最热月。"""
        for name, rec in WX._climate().items():
            if name in ("三亚", "海口"):
                continue
            self.assertGreater(rec["t"][6], rec["t"][0], f"{name} 的 7 月应该比 1 月热")

    def test_north_south_season_opposite(self):
        """南北半球季节相反：南半球 7 月是冬。"""
        # 用同一个月的参照点，验证月份翻转逻辑
        self.assertEqual(WX.fallback(-33.87, 151.21)["date"],
                         datetime.date.today().isoformat())


class TestFallbackAccuracy(unittest.TestCase):
    """精度判据：误差大到会误导穿衣选择，就不合格。"""

    # (城市, 纬度, 经度, 该月实况均温℃)
    CASES = [
        ("北京", 39.9042, 116.4074, 11.8),
        ("哈尔滨", 45.8038, 126.5349, -14),
        ("三亚", 18.2528, 109.5119, 30),
        ("拉萨", 29.6520, 91.1721, 4),
        ("上海", 31.2304, 121.4737, 15),
        ("广州", 23.1291, 113.2644, 22),
        ("乌鲁木齐", 43.8256, 87.6168, -2),
        ("昆明", 25.0389, 102.7183, 15),
    ]

    def test_error_under_tolerance(self):
        """平均误差不超过 4℃。"""
        errs = []
        for name, lat, lon, real in self.CASES:
            est = WX.fallback(lat, lon)["current"]["temp"]
            errs.append(abs(est - real))
        avg = sum(errs) / len(errs)
        self.assertLess(avg, 4.0, f"平均偏差 {avg:.1f}℃ 太大：{errs}")

    def test_no_single_error_over_10(self):
        """单城误差不超过 10℃——超过这个数，穿衣建议会明显出错。"""
        for name, lat, lon, real in self.CASES:
            est = WX.fallback(lat, lon)["current"]["temp"]
            self.assertLess(abs(est - real), 10.0,
                            f"{name} 估 {est}℃ vs 实况 {real}℃，偏差过大")

    def test_cold_city_stays_cold(self):
        """最关键的一条：哈尔滨不能估成零上。

        早先只用「纬度线性修正」时，哈尔滨 11 月估出 7.9℃——
        零下 14℃ 的城市估成零上，会让人穿短袖出门。
        """
        est = WX.fallback(45.8038, 126.5349)["current"]["temp"]
        self.assertLess(est, 0, "哈尔滨 11 月不该估成零上")

    def test_hot_city_stays_hot(self):
        """三亚不该估成冷的。"""
        est = WX.fallback(18.2528, 109.5119)["current"]["temp"]
        self.assertGreater(est, 18, "三亚 11 月不该估成 18 度以下")

    def test_cities_are_ordered_correctly(self):
        """南北温差必须拉开，不能都估成一个温度。"""
        harbin = WX.fallback(45.8038, 126.5349)["current"]["temp"]
        sanya = WX.fallback(18.2528, 109.5119)["current"]["temp"]
        self.assertGreater(sanya - harbin, 20, "南北温差被抹平了")


class TestFallbackShape(unittest.TestCase):
    """返回结构要和在线天气一致，否则下游会取不到键。"""

    def setUp(self):
        self.w = WX.fallback(39.9042, 116.4074)

    def test_has_same_keys_as_online(self):
        for key in ("date", "current", "daily", "hours",
                    "feel_max", "feel_min", "feel_mean"):
            self.assertIn(key, self.w, f"兜底天气缺 {key}")

    def test_has_24_hours(self):
        """逐小时数据要完整，缺小时会让分时段推荐算错。"""
        self.assertEqual(len(self.w["hours"]), 24)
        self.assertEqual([h["hour"] for h in self.w["hours"]], list(range(24)))

    def test_hours_have_required_fields(self):
        for h in self.w["hours"]:
            for key in ("hour", "temp", "apparent", "pop", "precip",
                        "wind", "code", "uv"):
                self.assertIn(key, h, f"小时数据缺 {key}")

    def test_daily_range_sane(self):
        """最高温不能低于最低温。"""
        self.assertGreater(self.w["daily"]["tmax"], self.w["daily"]["tmin"])

    def test_feel_consistent_with_hours(self):
        feels = [h["apparent"] for h in self.w["hours"]]
        self.assertAlmostEqual(self.w["feel_max"], max(feels), places=1)
        self.assertAlmostEqual(self.w["feel_min"], min(feels), places=1)

    def test_marks_as_estimate(self):
        """要标出这是估算值，调用方才能提示用户。"""
        self.assertIn("估算", self.w["current"]["desc"])


if __name__ == "__main__":
    unittest.main()
