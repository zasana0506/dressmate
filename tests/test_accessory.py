# -*- coding: utf-8 -*-
"""首饰进方案的回归测试。

核心边界：
1. 首饰只贴在已有搭配上——加分基于场合与命理标签，不碰保暖、不改正式度；
2. 桃花日项链/耳环加分、文昌日手链扣分——和 luck 文案说的是同一件事；
3. 天气类配饰（伞）优先级永远高于装饰类首饰；
4. 没有类型词的「彩色首饰」宁可不上。
"""
import unittest
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: F401  测试环境隔离

from engine import recommend as REC


def wx(pop=0, uv=0, tmin=18):
    return {
        "feel_mean": 20, "feel_min": tmin, "feel_max": 24,
        "daily": {"pop_max": pop, "uv_max": uv},
    }


def jewel(name, color="金"):
    return {"name": name, "slot": "accessory", "category": "jewelry",
            "color": color, "clo": 0.0, "formality": 2, "id": "j" + name}


def cand(item, warm_fit=0.8):
    return {"item": item, "slot": "accessory", "warm_fit": warm_fit,
            "formal": item.get("formality", 2), "formal_gap": 0,
            "state": "clean", "days": 999}


def ctx(formal=2, social=None, study=None):
    c = {"formality": formal, "slot_temp": {}}
    if social:
        c["social"] = social
    if study:
        c["study"] = study
    return c


class TestJewelryType(unittest.TestCase):
    def test_type_words(self):
        self.assertEqual(REC.jewelry_type(jewel("金项链")), "necklace")
        self.assertEqual(REC.jewelry_type(jewel("银手链2")), "bracelet")
        # 耳钉和耳环不是一回事：耳钉日常能戴，耳环只在正式场合成立
        self.assertEqual(REC.jewelry_type(jewel("金耳钉")), "stud")
        self.assertEqual(REC.jewelry_type(jewel("金耳环")), "earring")
        self.assertEqual(REC.jewelry_type(jewel("银戒指3")), "ring")
        self.assertEqual(REC.jewelry_type(jewel("彩色首饰")), "")

    def test_type_from_field(self):
        """导入阶段写好的类型优先于名字推断。"""
        it = jewel("某件首饰")
        it["jewelry_type"] = "brooch"
        self.assertEqual(REC.jewelry_type(it), "brooch")


class TestPick(unittest.TestCase):
    def test_necklace_beats_bracelet_formal(self):
        pools = {"accessory": [cand(jewel("金项链")), cand(jewel("金手链"))]}
        best = REC._best_accessory({}, pools, ctx(formal=3), wx())
        self.assertEqual(best["item"]["name"], "金项链")

    def test_bracelet_ok_casual(self):
        pools = {"accessory": [cand(jewel("银手链"))]}
        best = REC._best_accessory({}, pools, ctx(formal=1), wx())
        self.assertIsNotNone(best)

    def test_bracelet_rejected_formal(self):
        pools = {"accessory": [cand(jewel("银手链"))]}
        best = REC._best_accessory({}, pools, ctx(formal=3), wx())
        self.assertIsNone(best, "正式场合手链扣分后不该过门槛")

    def test_study_day_prefers_ring(self):
        pools = {"accessory": [cand(jewel("金手链")), cand(jewel("银戒指"))]}
        study = {"flag": True, "level": "strong"}
        best = REC._best_accessory({}, pools, ctx(formal=2, study=study), wx())
        self.assertEqual(best["item"]["name"], "银戒指")

    def test_social_boosts_necklace(self):
        # 正式度 2 时项链本身不占优，桃花标签把它抬到戒指之上
        pools = {"accessory": [cand(jewel("金项链")), cand(jewel("银戒指"))]}
        social = {"flag": True, "stars": ["红鸾"]}
        best = REC._best_accessory({}, pools, ctx(formal=2, social=social), wx())
        self.assertEqual(best["item"]["name"], "金项链")

    def test_umbrella_beats_jewelry_on_rain(self):
        umbrella = {"name": "折叠伞", "slot": "accessory", "category": "umbrella",
                    "color": "黑", "clo": 0.0, "formality": 1, "id": "u1"}
        pools = {"accessory": [cand(jewel("金项链")), cand(umbrella)]}
        best = REC._best_accessory({}, pools, ctx(formal=3), wx(pop=60))
        self.assertEqual(best["item"]["name"], "折叠伞")

    def test_generic_jewelry_not_picked(self):
        pools = {"accessory": [cand(jewel("彩色首饰"))]}
        best = REC._best_accessory({}, pools, ctx(formal=2), wx())
        self.assertIsNone(best, "没有类型词的首饰不知道怎么搭，宁缺毋滥")

    def test_silver_neutral_bonus(self):
        # 同为项链，金银中性色加分相同——这测试只保证不炸且能选上
        pools = {"accessory": [cand(jewel("银项链"))]}
        best = REC._best_accessory({}, pools, ctx(formal=3), wx())
        self.assertIsNotNone(best)


class TestReason(unittest.TestCase):
    def test_accessory_reasons(self):
        r = REC._accessory_reason(cand(jewel("金项链")), ctx(formal=3))
        self.assertIn("领口", r)
        r = REC._accessory_reason(cand(jewel("金手链")), ctx(formal=2, study={"flag": True}))
        self.assertIn("手腕", r)   # 文昌日手链：叮当的别戴
        r = REC._accessory_reason(
            cand(jewel("金项链")), ctx(formal=2, social={"flag": True}))
        self.assertIn("存在感", r)
        # 非首饰配饰沿用点睛说法
        umbrella = {"name": "折叠伞", "category": "umbrella"}
        r = REC._accessory_reason({"item": umbrella}, ctx())
        self.assertIn("点睛", r)

    def test_color_reason_attached(self):
        """颜色理由来自这套衣服，要出现在文案里。"""
        c = cand(jewel("金项链"))
        c["harmony_note"] = "和上衣同一个色系，看着成套"
        r = REC._accessory_reason(c, ctx(formal=3))
        self.assertIn("成套", r)

    def test_bad_color_reason_hidden(self):
        """撞色是扣分项，不能写成卖点。"""
        c = cand(jewel("金项链"))
        c["harmony_note"] = "和身上的颜色不同路，容易显杂"
        r = REC._accessory_reason(c, ctx(formal=3))
        self.assertNotIn("不同路", r)
        self.assertIn("领口", r)


def cloth(slot, color, name=""):
    return {"slot": slot, "item": {"name": name or f"{color}{slot}", "color": color,
                                   "slot": slot}}


class TestColorHarmony(unittest.TestCase):
    """首饰的颜色合理性：它是点缀，判断标准和衣服互搭不同。"""

    def test_same_family_scores_best(self):
        chosen = [cloth("base", "绿", "绿衬衫"), cloth("bottom", "黑", "黑裤")]
        good, _ = REC._jewelry_harmony(jewel("绿项链", "绿"), chosen, {})
        off, _ = REC._jewelry_harmony(jewel("红项链", "红"), chosen, {})
        self.assertGreater(good, off)
        self.assertGreater(good, 0.10)
        self.assertLess(off, 0)

    def test_metal_is_neutral_not_a_color(self):
        """金银不是颜色：不该被当成一个色系去跟衣服撞色。"""
        chosen = [cloth("base", "绿"), cloth("bottom", "黑")]
        gold, _ = REC._jewelry_harmony(jewel("金项链", "金"), chosen, {})
        silver, _ = REC._jewelry_harmony(jewel("银项链", "银"), chosen, {})
        red, _ = REC._jewelry_harmony(jewel("红项链", "红"), chosen, {})
        self.assertGreaterEqual(gold, 0)
        self.assertGreaterEqual(silver, 0)
        self.assertGreater(gold, red)   # 金属色安全，撞色扣分

    def test_all_neutral_outfit_gives_jewelry_the_stage(self):
        """全身素色时首饰是唯一亮点，该加分。"""
        chosen = [cloth("base", "白"), cloth("bottom", "黑")]
        metal, note = REC._jewelry_harmony(jewel("金项链", "金"), chosen, {})
        colored, note2 = REC._jewelry_harmony(jewel("红项链", "红"), chosen, {})
        self.assertIn("亮点", note)
        self.assertGreaterEqual(metal, colored)

    def test_warm_outfit_pairs_with_gold(self):
        """金配暖、银配冷——这是真的搭配常识，不是随机加分。"""
        warm = [cloth("mid", "红", "红毛衣")]
        g_gold, _ = REC._jewelry_harmony(jewel("金项链", "金"), warm, {})
        g_silver, _ = REC._jewelry_harmony(jewel("银项链", "银"), warm, {})
        self.assertGreater(g_gold, g_silver)

    def test_cool_outfit_pairs_with_silver(self):
        cool = [cloth("mid", "蓝", "蓝毛衣")]
        g_silver, _ = REC._jewelry_harmony(jewel("银项链", "银"), cool, {})
        g_gold, _ = REC._jewelry_harmony(jewel("金项链", "金"), cool, {})
        self.assertGreater(g_silver, g_gold)

    def test_lucky_color_on_jewelry(self):
        chosen = [cloth("base", "黑")]
        ctxd = {"luck": {"color_family": "绿"}}
        hit, note = REC._jewelry_harmony(jewel("绿项链", "绿"), chosen, ctxd)
        miss, _ = REC._jewelry_harmony(jewel("蓝项链", "蓝"), chosen, ctxd)
        self.assertGreater(hit, miss)
        self.assertIn("幸运色", note)


class TestAllowed(unittest.TestCase):
    """款式成不成立是硬约束，不靠扣分竞争。"""

    def test_brooch_needs_outer(self):
        no_outer = [cloth("base", "白"), cloth("bottom", "黑")]
        with_outer = no_outer + [cloth("outer", "黑", "黑西装")]
        b = jewel("银胸针")
        self.assertFalse(REC._jewelry_allowed(b, "brooch", ctx(formal=3), no_outer, wx()))
        self.assertTrue(REC._jewelry_allowed(b, "brooch", ctx(formal=3), with_outer, wx()))

    def test_brooch_not_picked_without_outer(self):
        pools = {"accessory": [cand(jewel("银胸针")), cand(jewel("金项链"))]}
        chosen = [cloth("base", "白"), cloth("bottom", "黑")]
        best = REC._best_accessory({"chosen": chosen}, pools, ctx(formal=3), wx())
        self.assertEqual(best["item"]["name"], "金项链")

    def test_earring_not_everyday(self):
        e = jewel("金耳环")
        self.assertFalse(REC._jewelry_allowed(e, "earring", ctx(formal=1), [], wx()))
        self.assertTrue(REC._jewelry_allowed(e, "earring", ctx(formal=3), [], wx()))

    def test_stud_works_everyday(self):
        s = jewel("金耳钉")
        self.assertTrue(REC._jewelry_allowed(s, "stud", ctx(formal=1), [], wx()))
        self.assertTrue(REC._jewelry_allowed(s, "stud", ctx(formal=3), [], wx()))

    def test_anklet_only_when_bare_ankles(self):
        a = jewel("银脚链")
        self.assertFalse(REC._jewelry_allowed(a, "anklet", ctx(formal=1), [], wx(tmin=8)))
        self.assertTrue(REC._jewelry_allowed(a, "anklet", ctx(formal=1), [], wx(tmin=24)))


class TestNoNoteLeak(unittest.TestCase):
    def test_note_not_shared_across_outfits(self):
        """候选对象被所有方案共用，写回 note 会串味。

        真 bug：先算的方案把 harmony_note 写进共享候选，
        后算的方案再覆盖它，页面上的搭配和理由就对不上
        （衣服是黄鞋，理由却说「全身没彩色」）。
        """
        pools = {"accessory": [cand(jewel("绿项链", "绿"))]}
        green = [cloth("base", "绿", "绿衬衫")]
        dark = [cloth("base", "黑", "黑衬衫")]
        a = REC._best_accessory({"chosen": green}, pools, ctx(formal=3), wx())
        note_a = a["harmony_note"]
        self.assertIn("成套", note_a)
        b = REC._best_accessory({"chosen": dark}, pools, ctx(formal=3), wx())
        self.assertIn("提气", b["harmony_note"])
        # 第二次调用不能改掉第一次返回的结果
        self.assertIn("成套", a["harmony_note"])


class TestEarringSlot(unittest.TestCase):
    """正式场合的耳机位：项链配耳钉是标准组合。"""

    def setUp(self):
        self.pools = {
            "accessory": [cand(jewel("银钻项链", "白")), cand(jewel("金耳钉", "金"))],
        }
        self.formal = [cloth("base", "白"), cloth("outer", "黑"), cloth("bottom", "黑")]

    def test_formal_gets_necklace_and_stud(self):
        r = {"chosen": list(self.formal)}
        c = ctx(formal=3)
        main = REC._best_accessory(r, self.pools, c, wx())
        r["chosen"].append(main)
        side = REC._side_earring(r, self.pools, c, wx(), main)
        self.assertEqual(REC.jewelry_type(main["item"]), "necklace")
        self.assertEqual(REC.jewelry_type(side["item"]), "stud")

    def test_casual_gets_one_piece(self):
        r = {"chosen": list(self.formal)}
        c = ctx(formal=2)
        main = REC._best_accessory(r, self.pools, c, wx())
        r["chosen"].append(main)
        self.assertIsNone(REC._side_earring(r, self.pools, c, wx(), main),
                          "日常一件就够，没必要耳机位")

    def test_no_second_earring_when_main_is_earring(self):
        r = {"chosen": list(self.formal)}
        c = ctx(formal=3)
        main = cand(jewel("金耳钉", "金"))
        self.assertIsNone(REC._side_earring(r, self.pools, c, wx(), main))

    def test_hat_blocks_earring(self):
        """冷天戴帽子就别再塞耳钉，压着耳朵不舒服。"""
        r = {"chosen": list(self.formal)}
        hat = {"item": {"name": "毛线帽", "category": "hat", "slot": "accessory"},
               "slot": "accessory", "warm_fit": 0.8}
        self.assertIsNone(REC._side_earring(r, self.pools, ctx(formal=3), wx(), hat))


class TestTrim(unittest.TestCase):
    def test_keeps_variety(self):
        """截断不能把五百件首饰压成十几条同名手链。"""
        cands = [cand(jewel(f"银手链{i}")) for i in range(40)]
        cands += [cand(jewel("金项链")), cand(jewel("金耳钉"))]
        kept = REC._trim_accessories(cands)
        types = {REC.jewelry_type(c["item"]) for c in kept}
        self.assertIn("necklace", types)
        self.assertIn("stud", types)
        self.assertLess(len(kept), len(cands))


if __name__ == "__main__":
    unittest.main()
