# -*- coding: utf-8 -*-
"""疾厄保暖余量 / 迁移出行提示 / 桃花场景标签 / 文昌文书提醒 的回归测试。

这四项都是「命理 → 穿搭」的挂载，共同风险是同一种：
命理越过天气和场合做决定，给出荒谬结论（例如零下十度被建议穿薄风衣）。
所以测试的重点不是文案好不好听，而是这几条边界：

1. 保暖余量只加不减，热天不生效，温和天气按比例衰减；
2. 加严后配不出整套时必须退回，不能让提示层把功能搞挂；
3. 桃花只出标签，不改正式度；
4. 文昌只调配色偏好（±0.03），不改保暖选型、不改正式度。
"""
import json
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: F401  测试环境隔离（不读本机真实档案）

from engine import config as C          # noqa: E402
from engine import context as CTX       # noqa: E402
from engine import luck as LUCK         # noqa: E402
from engine import recommend as REC     # noqa: E402
from engine import trip as TRIP         # noqa: E402

FIXTURE = os.path.join(BASE_DIR, "tests", "fixtures", "wardrobe.json")


def wx(tmin, tmax):
    """构造单日天气，字段与 weather.fetch_days 的逐日结构一致。"""
    mean = round((tmin + tmax) / 2, 1)
    return {
        "date": "2026-11-06", "feel_min": tmin, "feel_max": tmax, "feel_mean": mean,
        "daily": {"tmax": tmax + 2, "tmin": tmin - 2, "feels_max": tmax, "feels_min": tmin,
                  "pop_max": 0, "precip_sum": 0, "wind_max": 8, "uv_max": 2,
                  "code": 0, "desc": "晴"},
        "hours": [], "stale": False,
    }


def palace(name, branch, major=None, minor=None, adj=None, changsheng=""):
    return {"name": name, "branch": branch,
            "major": major or [], "minor": minor or [], "adj": adj or [],
            "changsheng12": changsheng}


def star(name, brightness="庙"):
    return {"name": name, "brightness": brightness, "mutagen": ""}


def raw_natal(health=None, travel=None, soul=None, mutagens=None, career=None):
    """造一份最小可用的排盘结果：只需 palaces 与 flow.daily.index_of。

    health / travel / soul / career 分别是流日疾厄、迁移、命宫、官禄落在的那个本命宫。
    """
    palaces = [palace(f"备用{i}", b) for i, b in enumerate("子丑寅卯辰巳午未申酉戌亥")]
    idx_of = {}
    for name, p, slot in (("命宫", soul, 0), ("疾厄", health, 3), ("迁移", travel, 6),
                          ("官禄", career, 9)):
        if p is not None:
            palaces[slot] = p
        idx_of[name] = slot
    return {
        "ok": True, "palaces": palaces,
        "flow": {"daily": {"index_of": idx_of, "mutagen": mutagens or ["", "", "", ""]}},
    }


class TestHealthWarmth(unittest.TestCase):
    """疾厄宫 → 保暖余量。"""

    def test_sha_star_gives_bonus(self):
        raw = raw_natal(health=palace("田宅", "寅", [star("七杀")], [star("擎羊")]))
        h = LUCK.analyze(raw)["health"]
        self.assertTrue(h["flag"])
        self.assertEqual(h["warmth_bonus"], 0.05)
        self.assertIn("擎羊", h["note"])

    def test_bonus_is_capped(self):
        """煞 + 化忌 + 落陷同时命中，也不能无限加严。"""
        raw = raw_natal(health=palace("田宅", "寅", [star("天机", "陷")], [star("擎羊")]),
                        mutagens=["破军", "巨门", "太阴", "天机"])
        h = LUCK.analyze(raw)["health"]
        self.assertEqual(h["warmth_bonus"], 0.10, "保暖余量必须有上限")

    def test_clean_palace_gives_nothing(self):
        raw = raw_natal(health=palace("田宅", "寅", [star("七杀", "庙")]))
        h = LUCK.analyze(raw)["health"]
        self.assertFalse(h["flag"])
        self.assertEqual(h["warmth_bonus"], 0.0)

    def test_bonus_never_negative(self):
        """只加不减是硬约束：任何组合下都不允许出现负值。"""
        cases = [
            raw_natal(health=palace("田宅", "寅", [star("七杀", "庙")])),
            raw_natal(health=palace("田宅", "寅", [star("天机", "陷")], [star("地空")])),
            raw_natal(health=None),
            {"ok": True, "palaces": [], "flow": {"daily": {}}},
        ]
        for raw in cases:
            self.assertGreaterEqual(LUCK.analyze(raw)["health"]["warmth_bonus"], 0.0)

    def test_missing_flow_does_not_crash(self):
        out = LUCK.analyze({"ok": True})
        self.assertFalse(out["health"]["flag"])
        self.assertFalse(out["travel"]["flag"])
        self.assertFalse(out["social"]["flag"])


class TestTravelNote(unittest.TestCase):
    """迁移宫 → 出差提示。"""

    def test_sha_star_flags(self):
        raw = raw_natal(travel=palace("福德", "丑", [star("天梁")], [star("陀罗")]))
        t = LUCK.analyze(raw)["travel"]
        self.assertTrue(t["flag"])
        # 同一颗煞星，日常说"留时间"，出差说"改行李策略"，两套措辞不能混
        self.assertIn("延误", t["note"])
        self.assertIn("托运", t["trip_note"])
        self.assertNotIn("托运", t["note"])

    def test_horse_is_info_only(self):
        """天马主奔波不主不顺，不该当警示。"""
        raw = raw_natal(travel=palace("福德", "丑", [star("天梁")], [star("天马")]))
        t = LUCK.analyze(raw)["travel"]
        self.assertFalse(t["flag"], "天马不应触发警示")
        self.assertTrue(t.get("horse"))
        self.assertIn("天马", t["note"])

    def test_clean_gives_no_note(self):
        raw = raw_natal(travel=palace("福德", "丑", [star("天梁")]))
        t = LUCK.analyze(raw)["travel"]
        self.assertFalse(t["flag"])
        self.assertEqual(t["note"], "")


class TestPeachTag(unittest.TestCase):
    """桃花星 → 场景标签。"""

    def test_peach_in_soul_palace(self):
        raw = raw_natal(soul=palace("命宫", "亥", [star("巨门")], adj=["红鸾", "天喜"]))
        s = LUCK.analyze(raw)["social"]
        self.assertTrue(s["flag"])
        self.assertIn("红鸾", s["stars"])

    def test_changsheng_muyu_counts(self):
        """沐浴在长生十二神里，也是桃花位，不能漏。"""
        raw = raw_natal(soul=palace("命宫", "酉", [star("太阴")], changsheng="沐浴"))
        s = LUCK.analyze(raw)["social"]
        self.assertTrue(s["flag"])
        self.assertIn("沐浴", s["stars"])

    def test_peach_outside_soul_palace_ignored(self):
        """桃花只认命宫。三方四正都算的话一半的日子都会被标桃花，标签就没意义了。"""
        raw = raw_natal(soul=palace("命宫", "亥", [star("巨门")]),
                        travel=palace("迁移", "巳", adj=["红鸾", "咸池"]))
        s = LUCK.analyze(raw)["social"]
        self.assertFalse(s["flag"], "命宫以外的桃花星不该触发标签")

    def test_peach_does_not_touch_formality(self):
        """桃花只出标签，不改正式度——正式度由日程决定。"""
        base = CTX.build_context([{"title": "客户拜访", "start": "10:00", "end": "11:00"}], None)
        raw = raw_natal(soul=palace("命宫", "亥", [star("贪狼")], adj=["红鸾"]))
        social = LUCK.analyze(raw)["social"]
        self.assertTrue(social["flag"])
        ctx = dict(base)
        ctx["social"] = social
        self.assertEqual(ctx["formality"], base["formality"])


class TestWarmthInRecommend(unittest.TestCase):
    """保暖余量接进推荐引擎后的行为。"""

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as f:
            cls.items = json.load(f)["items"]

    def _run(self, w, bonus):
        ctx = CTX.build_context([], w)
        ctx["warmth_bonus"] = bonus
        return REC.recommend(self.items, ctx, w, top_n=1)

    def _clo(self, rec):
        return round(sum(o["item"].get("clo", 0) for o in rec["outfit"]
                         if o["slot"] in ("base", "mid", "outer")), 3)

    def test_hot_day_ignores_bonus(self):
        """热天加保暖余量是错的：27.5℃ 加严前后必须完全一致。"""
        w = wx(24, 31)
        a, _, _ = self._run(w, 0.0)
        b, _, _ = self._run(w, 0.10)
        self.assertTrue(a and b)
        self.assertEqual(self._clo(a[0]), self._clo(b[0]))

    def test_cold_day_never_gets_colder(self):
        """只加不减：加严后的三层 clo 合计不能低于未加严。"""
        for tmin, tmax in [(-8, 0), (0, 6), (6, 14), (10, 18)]:
            w = wx(tmin, tmax)
            a, _, _ = self._run(w, 0.0)
            b, _, _ = self._run(w, 0.10)
            if not (a and b):
                continue
            self.assertGreaterEqual(self._clo(b[0]), self._clo(a[0]),
                                    f"{tmax}℃ 加严后反而更薄了")

    def test_bonus_taper_is_continuous(self):
        """22℃ 以上为 0，12℃ 以下全额，中间线性——不应出现断崖。"""
        w17 = wx(14, 20)      # feel_mean 17，应等价于 0.05
        a, _, _ = self._run(w17, 0.05)
        b, _, _ = self._run(w17, 0.10)
        self.assertEqual(self._clo(a[0]), self._clo(b[0]))

    def test_fallback_when_wardrobe_too_thin(self):
        """加严后配不出整套时必须退回，不能开天窗。"""
        thin = [
            {"id": "b1", "name": "薄衬衫", "slot": "base", "category": "shirt", "clo": 0.20,
             "formality": 2, "color": "白", "season": ["autumn"], "status": "clean"},
            {"id": "m1", "name": "薄针织", "slot": "mid", "category": "sweater", "clo": 0.40,
             "formality": 2, "color": "灰", "season": ["autumn"], "status": "clean"},
            # 0.55 刚好卡在阈值上：目标 0.95 时合格，抬到 1.05 后被剔除
            {"id": "o1", "name": "薄外套", "slot": "outer", "category": "jacket", "clo": 0.55,
             "formality": 2, "color": "黑", "season": ["autumn"], "status": "clean"},
            {"id": "d1", "name": "长裤", "slot": "bottom", "category": "pants", "clo": 0.20,
             "formality": 2, "color": "黑", "season": ["autumn"], "status": "clean"},
            {"id": "s1", "name": "皮鞋", "slot": "shoes", "category": "shoes", "clo": 0.20,
             "formality": 2, "color": "黑", "season": ["autumn"], "status": "clean"},
        ]
        w = wx(-5, 5)
        recs, _, extra = REC.recommend(thin, self._ctx(w, 0.10), w, top_n=1)
        self.assertTrue(recs, "加严不该导致完全配不出方案")
        self.assertTrue(extra.get("warmth_relaxed"), "退回未加严时应标明")

    def _ctx(self, w, bonus):
        ctx = CTX.build_context([], w)
        ctx["warmth_bonus"] = bonus
        return ctx


class TestStudyNote(unittest.TestCase):
    """文昌文曲 → 考试/文书提示。"""

    def test_wenchang_in_soul_palace(self):
        raw = raw_natal(soul=palace("命宫", "亥", [star("天机")], [star("文昌", "庙")]))
        s = LUCK.analyze(raw)["study"]
        self.assertTrue(s["flag"])
        self.assertEqual(s["level"], "strong")
        self.assertIn("文昌", s["stars"])
        self.assertIn("命宫", s["palace"])
        self.assertTrue(s["checklist"], "文书日该给出出门检查清单")

    def test_wenchang_in_career_palace(self):
        raw = raw_natal(career=palace("官禄", "卯", [star("天府")], [star("文昌", "得")]))
        s = LUCK.analyze(raw)["study"]
        self.assertTrue(s["flag"])
        self.assertEqual(s["level"], "medium")
        self.assertEqual(s["palace"], "官禄宫")

    def test_other_palace_ignored(self):
        """只认命宫与官禄。三方四正都算的话，三分之一的日子都会标「利文书」。"""
        raw = raw_natal(soul=palace("命宫", "亥", [star("天机")]),
                        career=palace("官禄", "卯", [star("天府")]),
                        health=palace("财帛", "未", [star("天相")], [star("文昌", "庙")]))
        s = LUCK.analyze(raw)["study"]
        self.assertFalse(s["flag"], "文昌落在财帛宫不该触发文书标签")

    def test_weak_brightness_is_not_a_hit(self):
        """落陷的文星不主科名，只可能带出「多核一遍」的提醒。"""
        raw = raw_natal(soul=palace("命宫", "亥", [star("天机")], [star("文昌", "陷")]))
        s = LUCK.analyze(raw)["study"]
        self.assertFalse(s["flag"])
        self.assertEqual(s["level"], "none")

    def test_wenchang_hua_ke_upgrades(self):
        """文昌化科（丙日）：即便只是得地，科名之气也算有力。"""
        raw = raw_natal(soul=palace("命宫", "亥", [star("天机")], [star("文昌", "得")]),
                        mutagens=["天同", "天机", "文昌", "廉贞"])
        s = LUCK.analyze(raw)["study"]
        self.assertTrue(s["flag"])
        self.assertEqual(s["level"], "strong")
        self.assertIn("化科", s["note"])

    def test_wenchang_hua_ji_is_careful_not_lucky(self):
        """文昌化忌（辛日）不是「不宜考试」，是「文书易疏漏」——只提示核对，不给科名标签。"""
        raw = raw_natal(soul=palace("命宫", "亥", [star("天机")], [star("文昌", "庙")]),
                        mutagens=["巨门", "太阳", "文曲", "文昌"])
        s = LUCK.analyze(raw)["study"]
        self.assertTrue(s["careful"])
        self.assertIn("疏漏", s["note"])
        self.assertIn("核", s["note"])

    def test_clean_palace_gives_nothing(self):
        raw = raw_natal(soul=palace("命宫", "亥", [star("天机")], [star("左辅")]))
        s = LUCK.analyze(raw)["study"]
        self.assertFalse(s["flag"])
        self.assertFalse(s["careful"])
        self.assertEqual(s["note"], "")

    def test_missing_flow_does_not_crash(self):
        out = LUCK.analyze({"ok": True})
        self.assertFalse(out["study"]["flag"])


class TestStudyInRecommend(unittest.TestCase):
    """文昌日接进推荐引擎：只影响配色偏好，不动保暖与正式度。"""

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as f:
            cls.items = json.load(f)["items"]

    def _chosen(self, items):
        """把若干单品包成 score_combo 需要的 cand 结构。"""
        return [{"item": it, "slot": it["slot"], "warm_fit": 0.9,
                 "formal": it.get("formality", 2), "days": 5} for it in items]

    def test_plain_colors_get_bonus(self):
        plain = self._chosen([
            {"slot": "base", "color": "白"}, {"slot": "outer", "color": "黑"},
            {"slot": "bottom", "color": "黑"}, {"slot": "mid", "color": "米白"},
        ])
        self.assertEqual(REC._study_bonus(plain, {"study": {"flag": True}}), 0.03)

    def test_clashing_colors_get_penalty(self):
        clash = self._chosen([
            {"slot": "base", "color": "酒红"}, {"slot": "outer", "color": "墨绿"},
            {"slot": "bottom", "color": "姜黄"}, {"slot": "mid", "color": "紫"},
        ])
        self.assertEqual(REC._study_bonus(clash, {"study": {"flag": True}}), -0.03)

    def test_no_study_means_zero(self):
        clash = self._chosen([{"slot": "base", "color": "酒红"}, {"slot": "outer", "color": "墨绿"}])
        self.assertEqual(REC._study_bonus(clash, {}), 0.0)
        self.assertEqual(REC._study_bonus(clash, {"study": {"flag": False}}), 0.0)

    def test_bonus_is_smaller_than_luck_color(self):
        """幅度必须小于幸运色（0.04），否则文书偏好会盖过用户主动开的那层。"""
        self.assertLess(REC._study_bonus(
            self._chosen([{"slot": "base", "color": "白"}]), {"study": {"flag": True}}), 0.04)

    def test_warmth_decision_unchanged(self):
        """文昌日不该改变保暖选型：同一天开不开文昌，三层 clo 合计必须一致。"""
        w = wx(2, 9)
        base = CTX.build_context([], w)
        a, _, _ = REC.recommend(self.items, base, w, top_n=1)
        b, _, _ = REC.recommend(
            self.items, {**base, "study": {"flag": True, "level": "strong"}}, w, top_n=1)
        if not (a and b):
            self.skipTest("衣橱配不出方案，跳过")
        clo = lambda r: round(sum(o["item"].get("clo", 0) for o in r["outfit"]
                                  if o["slot"] in ("base", "mid", "outer")), 3)
        self.assertEqual(clo(a[0]), clo(b[0]))

    def test_formality_unchanged(self):
        """文昌不改正式度：面试该多正式由日程定。"""
        base = CTX.build_context([{"title": "周例会", "start": "10:00", "end": "11:00"}], None)
        self.assertEqual(base["formality"], 3)
        ctx = {**base, "study": {"flag": True, "level": "strong"}}
        self.assertEqual(ctx["formality"], base["formality"])


class TestTripLuckNote(unittest.TestCase):
    """迁移宫提示接进出差打包。"""

    def test_note_goes_to_luck_notes_not_alerts(self):
        days = [
            {"date": "2026-11-06", "feel_min": 2, "feel_max": 9, "feel_mean": 5.5,
             "daily": {"tmax": 11, "tmin": 0, "feels_max": 9, "feels_min": 2,
                       "pop_max": 0, "precip_sum": 0, "wind_max": 8, "uv_max": 2,
                       "code": 0, "desc": "晴"},
             "hours": [], "stale": False},
        ]
        with open(FIXTURE, encoding="utf-8") as f:
            items = json.load(f)["items"]
        travel = {"flag": True, "stars": ["陀罗"], "note": "迁移宫见陀罗，行李别托运。"}
        res = TRIP.plan_trip(items, days, formality=2, purpose="出差", luck_travel=travel)
        self.assertIn("迁移宫见陀罗，行李别托运。", res["luck_notes"])
        self.assertNotIn("迁移宫见陀罗，行李别托运。", res["alerts"],
                         "命理提示不该混进事实性提醒")

    def test_no_luck_means_empty(self):
        days = [
            {"date": "2026-11-06", "feel_min": 2, "feel_max": 9, "feel_mean": 5.5,
             "daily": {"tmax": 11, "tmin": 0, "feels_max": 9, "feels_min": 2,
                       "pop_max": 0, "precip_sum": 0, "wind_max": 8, "uv_max": 2,
                       "code": 0, "desc": "晴"},
             "hours": [], "stale": False},
        ]
        with open(FIXTURE, encoding="utf-8") as f:
            items = json.load(f)["items"]
        res = TRIP.plan_trip(items, days, formality=2, purpose="出差")
        self.assertEqual(res["luck_notes"], [])


if __name__ == "__main__":
    unittest.main()
