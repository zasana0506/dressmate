# -*- coding: utf-8 -*-
"""配件收口层测试：皮带、袜子、包、领带、丝袜。

这一层存在的理由，是这四条礼仪铁律以前**判不了**：
「皮带与皮鞋同色」「深色西装不配白袜」「领带别和裤子一个色」「正式场合裙装要配丝袜」。
不是规则难写，是衣橱里没有能挂靠的字段。

所以测试的重点不是「函数能跑」，而是：
1. 有这件单品时，规则真的会触发（不是写了永远不进的分支）；
2. 没有时，输出的是「还差什么」而不是「你错了」；
3. 品名子串不会把裤子的「系腰带」认成皮带、把鞋的「袜子男鞋」认成袜子。
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from engine import config as C        # noqa: E402
from engine import extras as EX      # noqa: E402
from engine import recommend as REC   # noqa: E402


def item(name, slot, category, color, formality=3, clo=0.3,
         material="皮革", **kw):
    d = {"id": name, "name": name, "slot": slot, "category": category,
         "color": color, "material": material, "clo": clo,
         "formality": formality, "season": ["autumn", "winter"],
         "status": "clean", "last_worn": None, "photo": ""}
    d.update(kw)
    return d


# 一身标准的商务会面：藏青衬衫 + 卡其大衣 + 深灰西裤 + 黑皮鞋
def base_outfit(bottom_color="深灰", bottom_cat="dress_pants"):
    return [
        item("藏青衬衫", "base", "shirt", "藏青", formality=3, clo=0.22, material="棉"),
        item("卡其大衣", "outer", "coat", "卡其", formality=3, clo=0.7, material="羊毛"),
        item("深灰西裤" if bottom_color == "深灰" else "黑西裤",
             "bottom", bottom_cat, bottom_color, formality=3, clo=0.25, material="羊毛"),
        item("黑皮鞋", "shoes", "shoes_leather", "黑", formality=4, clo=0.2),
    ]


def chosen(*items):
    return [{"slot": it["slot"], "item": it, "warm_fit": 0.9,
             "formal": it["formality"], "days": 30} for it in items]


def ctx(req=3):
    return {"formality": req, "formality_label": C.FORMALITY_LABELS[req],
            "slot_temp": {"base": 8, "mid": 8, "outer": 2, "bottom": 8, "shoes": 8}}


class TestRoleOf(unittest.TestCase):
    """角色识别：先卡槽位，再看品名。"""

    def test_belt_recognized(self):
        self.assertEqual(EX.role_of(item("黑皮带", "accessory", "belt", "黑")), "belt")

    def test_sock_recognized(self):
        self.assertEqual(EX.role_of(item("深灰羊毛袜", "accessory", "socks", "深灰")), "sock")

    def test_tie_recognized(self):
        self.assertEqual(EX.role_of(item("酒红领带", "accessory", "tie", "酒红")), "tie")

    def test_bag_recognized(self):
        self.assertEqual(EX.role_of(item("黑公文包", "accessory", "bag", "黑")), "bag")

    def test_hosiery_before_sock(self):
        """「连裤袜」含「袜」，但不该被当成中筒袜——两者规矩不同。"""
        self.assertEqual(EX.role_of(item("肤色连裤袜", "accessory", "hosiery", "米")), "hosiery")

    def test_dress_pants_named_with_belt_is_not_belt(self):
        """回归：商品名「秋季休闲劳保裤潮流系腰带西裤」里写着腰带，它是裤子。"""
        it = item("深灰西裤22", "bottom", "dress_pants", "深灰",
                  photo="photos/裤子_295_秋季休闲劳保裤潮流系腰带西裤简约耐磨.jpg")
        self.assertIsNone(EX.role_of(it))

    def test_shoe_named_with_sock_is_not_sock(self):
        """回归：鞋名「飞织袜子男鞋」里的「袜子」说的是鞋面，不是这件是袜子。"""
        it = item("黑运动鞋146", "shoes", "running_shoes", "黑",
                  photo="photos/鞋_156_飞织八爪鱼运动鞋透气火山袜子男鞋.jpg")
        self.assertIsNone(EX.role_of(it))

    def test_knitwear_is_not_tie(self):
        """回归：「翻领针织」曾被「领针」命中，七件毛衣被当成领带。"""
        it = item("驼针织衫2", "mid", "sweater", "驼",
                  photo="photos/上衣_260_男士翻领针织衫秋冬款纯加厚保暖毛衣.jpg")
        self.assertIsNone(EX.role_of(it))

    def test_explicit_field_wins(self):
        """显式字段优先：用户标了 hosiery，就别再按品名猜成裤子。"""
        it = item("黑长裤37", "bottom", "trousers", "黑", layer_role="hosiery")
        self.assertEqual(EX.role_of(it), "hosiery")


class TestLane(unittest.TestCase):
    def test_women_top_does_not_switch_lane(self):
        """101 件写着「女装」的上衣不等于女装衣橱：没有裙子就还是男装规矩。"""
        wardrobe = [item("白短袖T恤", "base", "tshirt", "白", gender="women"),
                    item("黑西裤", "bottom", "dress_pants", "黑")]
        self.assertEqual(EX.lane(wardrobe), "men")

    def test_skirt_switches_lane(self):
        wardrobe = [item("黑半裙", "bottom", "skirt", "黑"),
                    item("黑西裤", "bottom", "dress_pants", "黑")]
        self.assertEqual(EX.lane(wardrobe), "women")

    def test_lane_of_outfit_follows_the_outfit(self):
        """整橱有裙子，但这一身穿的是西裤——规矩按这身算。"""
        o = chosen(*base_outfit())
        self.assertEqual(EX.lane_of(o), "men")


class TestBeltRule(unittest.TestCase):
    """皮带与皮鞋同色：男装里最硬的一条同色规则。"""

    def test_matching_belt_is_picked(self):
        wardrobe = base_outfit() + [item("黑皮带", "accessory", "belt", "黑")]
        r = EX.check(chosen(*base_outfit()), wardrobe, ctx(3))
        roles = [p["role"] for p in r["picked"]]
        self.assertIn("belt", roles)
        belt = next(p for p in r["picked"] if p["role"] == "belt")
        self.assertIn("同色系", belt["reason"])

    def test_brown_belt_with_black_shoes_is_flagged(self):
        """黑鞋配棕皮带就是错的——不能因为「都是深色」放过。"""
        wardrobe = base_outfit() + [item("棕皮带", "accessory", "belt", "棕")]
        r = EX.check(chosen(*base_outfit()), wardrobe, ctx(3))
        codes = [i["code"] for i in r["issues"]]
        self.assertIn("belt_mismatch", codes)

    def test_no_belt_no_penalty_but_asks(self):
        """衣橱没皮带时不算穿错，只开清单，且颜色跟着皮鞋走。"""
        r = EX.check(chosen(*base_outfit()), base_outfit(), ctx(3))
        self.assertEqual([i for i in r["issues"] if i["code"] == "belt_mismatch"], [])
        need = next(n for n in r["needs"] if n["role"] == "belt")
        self.assertIn("黑", need["color_hint"])

    def test_casual_does_not_ask_for_belt(self):
        """居家/逛街不用皮带，问了反而是废话。"""
        r = EX.check(chosen(*base_outfit()), base_outfit(), ctx(1))
        self.assertEqual([n for n in r["needs"] if n["role"] == "belt"], [])


class TestSockRule(unittest.TestCase):
    """深色西装不配白袜。"""

    def test_white_sock_with_dark_trousers_is_flagged(self):
        wardrobe = base_outfit() + [item("白袜", "accessory", "socks", "白")]
        r = EX.check(chosen(*base_outfit()), wardrobe, ctx(3))
        codes = [i["code"] for i in r["issues"]]
        self.assertIn("sock_contrast", codes)
        note = next(i["note"] for i in r["issues"] if i["code"] == "sock_contrast")
        self.assertIn("白袜", note)

    def test_dark_sock_is_picked(self):
        wardrobe = base_outfit() + [item("黑袜", "accessory", "socks", "黑")]
        r = EX.check(chosen(*base_outfit()), wardrobe, ctx(3))
        self.assertIn("sock", [p["role"] for p in r["picked"]])

    def test_dark_sock_beats_white_when_both_exist(self):
        """两条袜都在时该挑深的那双，不是随便拿一条。"""
        wardrobe = base_outfit() + [item("白袜", "accessory", "socks", "白"),
                                    item("黑袜", "accessory", "socks", "黑")]
        r = EX.check(chosen(*base_outfit()), wardrobe, ctx(3))
        sock = next(p for p in r["picked"] if p["role"] == "sock")
        self.assertEqual(sock["item"]["color"], "黑")

    def test_no_sock_asks_for_one(self):
        r = EX.check(chosen(*base_outfit()), base_outfit(), ctx(3))
        need = next(n for n in r["needs"] if n["role"] == "sock")
        self.assertIn("深", need["color_hint"])


class TestTieRule(unittest.TestCase):
    def test_tie_same_as_trousers_is_flagged(self):
        """领带和西裤同色，上下一条线，看着像制服。"""
        o = base_outfit()
        # 领带撞下装（深灰），不是撞衬衫
        wardrobe = o + [item("深灰领带", "accessory", "tie", "深灰")]
        r = EX.check(chosen(*o), wardrobe, ctx(4))
        codes = [i["code"] for i in r["issues"]]
        self.assertIn("tie_clash", codes)

    def test_tie_matching_shirt_is_flagged(self):
        """领带和衬衫同色系会融进去，正式场合等于没打。"""
        o = base_outfit()
        wardrobe = o + [item("藏青领带", "accessory", "tie", "藏青")]
        r = EX.check(chosen(*o), wardrobe, ctx(4))
        self.assertIn("tie_clash", [i["code"] for i in r["issues"]])

    def test_contrasting_tie_is_picked(self):
        o = base_outfit()
        wardrobe = o + [item("酒红领带", "accessory", "tie", "酒红")]
        r = EX.check(chosen(*o), wardrobe, ctx(4))
        self.assertIn("tie", [p["role"] for p in r["picked"]])

    def test_formal_suit_without_tie_asks(self):
        """西装外套 + 衬衫，正式度也够，才轮到「领带还没买」。"""
        o = [x for x in base_outfit() if x["slot"] != "outer"]
        o.append(item("藏青西装", "outer", "blazer", "藏青", formality=4, clo=0.5, material="羊毛"))
        r = EX.check(chosen(*o), o, ctx(4))
        self.assertIn("tie", [n["role"] for n in r["needs"]])

    def test_coat_is_not_a_suit(self):
        """大衣不是西装外套——它罩在西装外面，单穿大衣配领带不成立。

        今天下午那套就是藏青衬衫 + 白开衫 + 大衣，系统却提示了领带。
        """
        o = base_outfit()          # outer 是卡其大衣
        r = EX.check(chosen(*o), o, ctx(4))
        self.assertNotIn("tie", [n["role"] for n in r["needs"]])

    def test_casual_never_asks_for_tie(self):
        r = EX.check(chosen(*base_outfit()), base_outfit(), ctx(2))
        self.assertNotIn("tie", [n["role"] for n in r["needs"]])


class TestBagRule(unittest.TestCase):
    def test_bag_matching_shoes_is_picked(self):
        wardrobe = base_outfit() + [item("黑公文包", "accessory", "bag", "黑")]
        r = EX.check(chosen(*base_outfit()), wardrobe, ctx(3))
        self.assertIn("bag", [p["role"] for p in r["picked"]])

    def test_red_bag_with_black_shoes_is_flagged(self):
        wardrobe = base_outfit() + [item("红包", "accessory", "bag", "红")]
        r = EX.check(chosen(*base_outfit()), wardrobe, ctx(4))
        self.assertIn("bag_jump", [i["code"] for i in r["issues"]])


class TestWomenRules(unittest.TestCase):
    """女装铁律：裙长、丝袜、浅色薄料。"""

    def women_outfit(self, length="knee"):
        return [
            item("白衬衫", "base", "shirt", "白", formality=3, clo=0.2),
            item("黑半裙", "bottom", "skirt", "黑", formality=3, clo=0.25,
                 material="羊毛", length=length),
            item("黑高跟", "shoes", "heels", "黑", formality=4, clo=0.1),
        ]

    def test_short_skirt_in_formal_is_flagged(self):
        o = self.women_outfit("mini")
        r = EX.check(chosen(*o), o, ctx(4))
        self.assertIn("skirt_short", [i["code"] for i in r["issues"]])

    def test_knee_length_passes(self):
        o = self.women_outfit("knee")
        r = EX.check(chosen(*o), o, ctx(4))
        self.assertNotIn("skirt_short", [i["code"] for i in r["issues"]])

    def test_formal_skirt_without_hosiery_is_flagged(self):
        o = self.women_outfit("knee")
        r = EX.check(chosen(*o), o, ctx(4))
        self.assertIn("hosiery_gap", [i["code"] for i in r["issues"]])

    def test_hosiery_present_clears_the_warning(self):
        o = self.women_outfit("knee")
        wardrobe = o + [item("肤色丝袜", "accessory", "hosiery", "米")]
        r = EX.check(chosen(*o), wardrobe, ctx(4))
        self.assertNotIn("hosiery_gap", [i["code"] for i in r["issues"]])

    def test_women_lane_detected_from_outfit(self):
        o = self.women_outfit()
        self.assertEqual(EX.lane_of(chosen(*o)), "women")

    def test_sheer_light_bottom_is_flagged(self):
        o = [item("白衬衫", "base", "shirt", "白", formality=2, clo=0.2),
             item("米白雪纺裤", "bottom", "trousers", "米白", formality=2,
                  clo=0.15, material="雪纺"),
             item("米白板鞋", "shoes", "shoes_sneakers", "米白", formality=1, clo=0.2)]
        r = EX.check(chosen(*o), o, ctx(2))
        self.assertIn("sheer_bottom", [i["code"] for i in r["issues"]])


class TestNoPenaltyForMissing(unittest.TestCase):
    """缺配件不扣分。缺不是错，是还没买。"""

    def test_needs_do_not_touch_style_score(self):
        o = chosen(*base_outfit())
        before = EX.check(o, base_outfit(), ctx(4))
        self.assertTrue(before["needs"], "正式场合应当列出缺的配件")
        self.assertEqual(before["issues"], [], "缺配件不该产生 issue")


class TestNotInPool(unittest.TestCase):
    """配件不进主候选池：它们没有独立自由度，混进来只会挤掉项链。"""

    def test_belt_excluded_from_candidates(self):
        wardrobe = base_outfit() + [
            item("黑皮带", "accessory", "belt", "黑", formality=3),
            item("银玉项链", "accessory", "jewelry", "白", formality=3),
        ]
        pools = REC.build_candidates(wardrobe, ctx(3), _weather(), formality_slack=2)
        names = [c["item"]["name"] for c in pools.get("accessory", [])]
        self.assertNotIn("黑皮带", names)
        self.assertIn("银玉项链", names)


def _weather(feel=8.0):
    hours = [{"hour": h, "apparent": feel, "temp": feel + 1, "pop": 0,
              "wind": 6, "uv": 2, "code": 0} for h in range(24)]
    return {"date": "2026-11-06",
            "current": {"apparent": feel, "temp": feel + 1, "humidity": 50,
                        "precip": 0, "code": 0, "wind": 6, "desc": "晴"},
            "daily": {"tmax": feel + 2, "tmin": feel - 2,
                      "feels_max": feel + 2, "feels_min": feel - 2,
                      "pop_max": 0, "precip_sum": 0, "wind_max": 6,
                      "uv_max": 2, "code": 0, "desc": "晴"},
            "hours": hours, "feel_max": feel + 2, "feel_min": feel - 2,
            "feel_mean": feel, "stale": False}


class TestNecessity(unittest.TestCase):
    """「缺」和「缺」不一样：一条是穿错，一条只是少层讲究。

    这一组来自真实输出：今天三套方案各列「还差皮带、袜子、领带、包」，
    可其中真正不穿就不成立的是袜子——皮带可以没、领带更可以不系。
    把四件并列写出来，用户会以为系统在催他买一整套。
    """

    def _levels(self, o, req=4, wardrobe=None):
        r = EX.check(chosen(*o), wardrobe or o, ctx(req))
        return {n["role"]: n["level"] for n in r["needs"]}

    def test_sock_is_required_with_leather_shoes(self):
        """皮鞋不穿袜是穿错，不是朴素——这条必须是 required。"""
        lv = self._levels(base_outfit())
        self.assertEqual(lv.get("sock"), EX.LEVEL_REQUIRED)

    def test_tie_and_bag_are_optional(self):
        """领带、包：没有只是少一层讲究，不该催人去买。"""
        o = [x for x in base_outfit() if x["slot"] != "outer"]
        o.append(item("藏青西装", "outer", "blazer", "藏青", formality=4, clo=0.5, material="羊毛"))
        lv = self._levels(o)
        self.assertEqual(lv.get("tie"), EX.LEVEL_OPTIONAL)
        self.assertEqual(lv.get("bag"), EX.LEVEL_OPTIONAL)

    def test_belt_required_when_waist_visible(self):
        """西裤 + 衬衫、外套敞开时，腰上那截露着，皮带是必须的。"""
        o = [x for x in base_outfit() if x["slot"] != "outer"]
        lv = self._levels(o)
        self.assertEqual(lv.get("belt"), EX.LEVEL_REQUIRED)

    def test_belt_downgraded_when_outer_covers_waist(self):
        """外套遮住腰时皮带不露，降级成可选——不是不用系，是别人看不见。"""
        lv = self._levels(base_outfit())
        self.assertEqual(lv.get("belt"), EX.LEVEL_OPTIONAL)

    def test_required_sorts_before_optional(self):
        levels = [n["level"] for n in
                  EX.needs(chosen(*base_outfit()), base_outfit(), ctx(4))]
        self.assertEqual(levels, sorted(levels, key=lambda x: x != EX.LEVEL_REQUIRED),
                         "要补的必须排在可选前面，否则用户先看到的是领带")


class TestTieHasNoBusinessHere(unittest.TestCase):
    """领带不是「有更好」，很多时候是「这身根本不戴领带」。"""

    def test_women_never_get_tie(self):
        """女士不报领带。不是可选，是不在这套规矩里。"""
        o = base_outfit() + [item("藏青西裤", "bottom", "dress_pants", "藏青", formality=4)]
        # 直接把这一身判成女装规矩（真实衣橱里由 lane_of 按裙装/高跟判定）
        r = EX.check(chosen(*o), o, ctx(4), lan="women")
        self.assertNotIn("tie", [n["role"] for n in r["needs"]])
        self.assertNotIn("tie", [p["role"] for p in r["picked"]])

    def test_crew_neck_knit_hides_tie(self):
        """衬衫 + 圆领针织衫 + 大衣：领带套在里面只露一个结，别提。

        这是今天真实数据里的组合（藏青衬衫 / 黑针织衫 / 卡其大衣11），
        系统当时照样提示「还差一条领带」——圆领毛衣下面系领带不是搭配，是没穿对。
        """
        mid = item("黑针织衫", "mid", "sweater", "黑",
                   formality=2, clo=0.28, material="羊毛")
        self.assertTrue(EX._blocks_tie(mid))

    def test_cardigan_also_blocks_tie(self):
        """开衫敞着、领带看得见，但针织 + 领带不是正装组合。

        今天 11:00 那套是藏青衬衫 + 白开衫 + 大衣，领带就是这么被误报出来的。
        """
        mid = item("白开衫", "mid", "cardigan", "白",
                   formality=3, clo=0.3, material="羊毛")
        self.assertTrue(EX._blocks_tie(mid))

    def test_turtleneck_blocks_tie(self):
        mid = item("高领毛衣", "mid", "turtleneck", "黑",
                   formality=3, clo=0.35, material="羊毛")
        self.assertTrue(EX._blocks_tie(mid))

    def test_vest_does_not_block(self):
        """衬衫 + 西装马甲 + 领带是标准三件套，不能当成挡领口。"""
        mid = item("西装马甲", "mid", "vest", "深灰",
                   formality=4, clo=0.25, material="羊毛")
        self.assertFalse(EX._blocks_tie(mid))

    def test_no_mid_means_tie_allowed(self):
        self.assertFalse(EX._blocks_tie(None))


class TestGapsMerged(unittest.TestCase):
    """三套方案缺的是同一条皮带，不该各说一遍。"""

    def test_gaps_deduped_across_outfits(self):
        weather = _weather(8.0)
        c = ctx(4)
        recs, _, extra = REC.recommend(base_outfit(), c, weather, top_n=3)
        roles = [n["role"] for n in extra.get("extras_gaps", [])]
        self.assertEqual(len(roles), len(set(roles)), "同一角色只能出现一次")
        self.assertTrue(roles, "正式场合应当有缺口清单")

    def test_required_wins_when_any_outfit_needs_it(self):
        """一套没穿外套（腰露着，皮带必须），一套穿了大衣（皮带可选）——
        合并后必须是 required：不能因为另一套遮住了就当不用系。"""
        a = [{"role": "belt", "name": "皮带", "why": "", "color_hint": "黑",
              "priority": 1, "level": EX.LEVEL_OPTIONAL}]
        b = [{"role": "belt", "name": "皮带", "why": "", "color_hint": "黑",
              "priority": 1, "level": EX.LEVEL_REQUIRED}]
        merged = EX.merge_needs([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["level"], EX.LEVEL_REQUIRED)

    def test_merge_puts_required_first(self):
        opt = {"role": "tie", "name": "领带", "why": "", "color_hint": "",
               "priority": 3, "level": EX.LEVEL_OPTIONAL}
        req = {"role": "sock", "name": "袜子", "why": "", "color_hint": "",
               "priority": 2, "level": EX.LEVEL_REQUIRED}
        merged = EX.merge_needs([[opt, req]])
        self.assertEqual([n["role"] for n in merged], ["sock", "tie"])


if __name__ == "__main__":
    unittest.main()
