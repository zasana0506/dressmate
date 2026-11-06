# -*- coding: utf-8 -*-
"""穿衣者身份（性别/年龄）对推荐的影响。

背景：用户问「你不看年龄和性别吗，女孩子需要戴领带吗」。
查下来是——「幸运穿搭」那栏本来就收了出生日期和性别，
但推荐引擎从来不读这些信息。衣橱里明明有 gender 标签
（women 178 件、men 960 件），一条都没用上。

这些用例锁住：
- 性别冲突的单品不进候选池
- 领带不给女生（gender 标签是空的，得按角色规则挡）
- 皮带不给小孩
- 年龄压低正式度上限
- 档案没填时一切照旧（不能因为没档案就推不出东西）
"""
import datetime
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: F401  测试环境隔离

from engine import context as CTX      # noqa: E402
from engine import extras as EXTRAS   # noqa: E402
from engine import identity as ID     # noqa: E402


TODAY = datetime.date(2026, 11, 6)


class TestAgeAndGenderParsing(unittest.TestCase):

    def test_age_from_birthday(self):
        p = {"solar_date": "2018-01-31", "gender": "女"}
        self.assertEqual(ID.age_of(p, TODAY), 8)

    def test_age_before_birthday_in_year(self):
        """生日还没到要减一岁：1 月 20 日生的人，到 11 月 6 日还是 0 岁。"""
        p = {"solar_date": "2026-01-20"}
        self.assertEqual(ID.age_of(p, TODAY), 0)
        # 过了生日就满 1 岁
        after = datetime.date(2027, 1, 21)
        self.assertEqual(ID.age_of(p, after), 1)

    def test_gender_normalized(self):
        for raw, want in [("女", "女"), ("女性", "女"), ("female", "女"),
                          ("男", "男"), ("男性", "男"), ("male", "男"),
                          ("", None), (None, None), ("x", None)]:
            self.assertEqual(ID.gender_of({"gender": raw}), want, raw)

    def test_bad_birthday_returns_none(self):
        self.assertIsNone(ID.age_of({"solar_date": "不是日期"}))
        self.assertIsNone(ID.age_of({}))

    def test_future_birthday_returns_none(self):
        self.assertIsNone(ID.age_of({"solar_date": "2030-01-01"}, TODAY))

    def test_no_profile_env_means_no_profile(self):
        """测试环境里不该读到磁盘档案。"""
        self.assertEqual(ID.load_profile(), {})


class TestItemGenderFilter(unittest.TestCase):

    def test_women_user_excludes_men_items(self):
        self.assertFalse(ID.item_allowed({"gender": "men"}, "女"))

    def test_women_user_keeps_women_items(self):
        self.assertTrue(ID.item_allowed({"gender": "women"}, "女"))

    def test_neutral_always_allowed(self):
        self.assertTrue(ID.item_allowed({"gender": "neutral"}, "女"))
        self.assertTrue(ID.item_allowed({"gender": "neutral"}, "男"))

    def test_untagged_always_allowed(self):
        """大部分配件没有性别标签，不能一棍子打死。"""
        self.assertTrue(ID.item_allowed({}, "女"))
        self.assertTrue(ID.item_allowed({"name": "某配饰"}, "女"))

    def test_no_gender_means_no_filtering(self):
        """档案没填性别就全都放行——不能因为没档案就推不出东西。"""
        self.assertTrue(ID.item_allowed({"gender": "men"}, None))


class TestAccessoryGenderRules(unittest.TestCase):
    """领带这类「gender 标签是空的」配件，只能按角色规则挡。"""

    TIE = {"category": "necktie", "name": "金黄斜纹领带", "gender": None}

    def test_tie_not_given_to_woman(self):
        self.assertFalse(ID.accessory_allowed("tie", self.TIE, "女", 20))

    def test_tie_given_to_man(self):
        self.assertTrue(ID.accessory_allowed("tie", self.TIE, "男", 20))

    def test_tie_marked_women_is_allowed(self):
        t = {"category": "necktie", "name": "某女款领带", "gender": "women"}
        self.assertTrue(ID.accessory_allowed("tie", t, "女", 20))

    def test_belt_not_given_to_child(self):
        belt = {"category": "belt", "name": "棕色皮带"}
        self.assertFalse(ID.accessory_allowed("belt", belt, "女", 8))
        self.assertTrue(ID.accessory_allowed("belt", belt, "女", 30))

    def test_socks_allowed_for_child(self):
        sock = {"category": "crew_socks", "name": "灰色中筒袜"}
        self.assertTrue(ID.accessory_allowed("sock", sock, "女", 8))

    def test_no_gender_no_filtering(self):
        self.assertTrue(ID.accessory_allowed("tie", self.TIE, None, None))


class TestFormalityCeiling(unittest.TestCase):

    def test_child_capped_at_casual(self):
        self.assertEqual(ID.formality_ceiling({"age": 8}), 1)

    def test_teen_capped_one_step(self):
        self.assertEqual(ID.formality_ceiling({"age": 14}), 2)

    def test_adult_uncapped(self):
        self.assertIsNone(ID.formality_ceiling({"age": 30}))

    def test_works_with_raw_profile(self):
        self.assertEqual(
            ID.formality_ceiling({"solar_date": "2018-01-31"}, TODAY), 1)


class TestContextIntegration(unittest.TestCase):
    """身份要真的进到 ctx 里，否则引擎拿不到。"""

    def test_identity_in_context(self):
        ctx = CTX.build_context([], None, profile={"gender": "女", "solar_date": "2018-01-31"})
        self.assertEqual(ctx["identity"]["gender"], "女")
        self.assertEqual(ctx["identity"]["age"], 8)

    def test_child_formality_capped(self):
        ctx = CTX.build_context(
            [{"title": "客户拜访", "start": "10:00", "end": "11:00"}], None,
            profile={"gender": "女", "solar_date": "2018-01-31"})
        self.assertLessEqual(ctx["formality"], 1)
        self.assertTrue(ctx.get("formality_capped"))

    def test_adult_formality_unchanged(self):
        ctx = CTX.build_context(
            [{"title": "客户拜访", "start": "10:00", "end": "11:00"}], None,
            profile={"gender": "男", "solar_date": "1990-01-01"})
        self.assertEqual(ctx["formality"], 4)
        self.assertFalse(ctx.get("formality_capped"))

    def test_no_profile_keeps_formality(self):
        ctx = CTX.build_context(
            [{"title": "客户拜访", "start": "10:00", "end": "11:00"}], None,
            profile={})
        self.assertEqual(ctx["formality"], 4)


class TestCandidateFiltering(unittest.TestCase):
    """候选池里不该出现性别冲突的单品。"""

    def _ctx(self, gender, age=None):
        return CTX.build_context([], None, profile={
            "gender": gender, "solar_date": "1990-01-01" if not age else "2018-01-31"})

    def test_men_items_excluded_for_woman(self):
        from engine import recommend as REC
        wardrobe = [
            {"id": "m1", "name": "男士衬衫", "slot": "base", "category": "shirt",
             "color": "白", "material": "棉", "clo": 0.2, "formality": 3,
             "gender": "men", "status": "clean", "season": ["spring", "summer"]},
            {"id": "w1", "name": "女士衬衫", "slot": "base", "category": "shirt",
             "color": "白", "material": "棉", "clo": 0.2, "formality": 3,
             "gender": "women", "status": "clean", "season": ["spring", "summer"]},
        ]
        ctx = self._ctx("女")
        ctx["slot_temp"] = {"base": 20, "mid": 18, "outer": 15,
                            "bottom": 18, "shoes": 18}
        pools = REC.build_candidates(wardrobe, ctx, {
            "feel_mean": 18, "feel_max": 20, "feel_min": 15,
            "daily": {"tmax": 20, "tmin": 15}}, None, TODAY)
        names = [c["item"]["name"] for c in pools.get("base", [])]
        self.assertNotIn("男士衬衫", names, "gender=men 的不该给女用户")
        self.assertIn("女士衬衫", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
