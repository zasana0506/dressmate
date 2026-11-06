# -*- coding: utf-8 -*-
"""穿出门的规矩：品类禁区、正式度口径、三套差异化、时段自洽。

这些用例对应「引擎算得对，但人穿不出去」的一类缺陷——
分数漂亮、理由通顺，可方案本身是错的（荧光劳保背心配西裤去客户会、
牛仔裤混进正式场合、时间轴两段互相重叠）。
"""
import datetime
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from engine import config as C            # noqa: E402
from engine import context as CTX         # noqa: E402
from engine import recommend as REC       # noqa: E402
from engine import timeline as TL         # noqa: E402

TODAY = datetime.date(2026, 11, 5)


def make_weather(feel_mean=5.0, feel_min=None, feel_max=None, pop=0, wind=8, uv=2):
    feel_min = feel_mean - 4 if feel_min is None else feel_min
    feel_max = feel_mean + 3 if feel_max is None else feel_max
    hours = []
    for h in range(24):
        t = feel_min + (feel_max - feel_min) * max(0.0, min(1.0, (h - 5) / 10.0))
        if h > 15:
            t = feel_min + (feel_max - feel_min) * max(0.0, (23 - h) / 8.0)
        hours.append({"hour": h, "apparent": round(t, 1), "temp": round(t + 1, 1),
                      "pop": pop, "wind": wind, "uv": uv, "code": 0})
    return {
        "date": "2026-11-05",
        "current": {"apparent": feel_mean, "temp": feel_mean + 1, "humidity": 50,
                    "precip": 0, "code": 0, "wind": wind, "desc": "晴"},
        "daily": {"tmax": feel_max + 1, "tmin": feel_min - 1, "feels_max": feel_max,
                  "feels_min": feel_min, "pop_max": pop, "precip_sum": 0,
                  "wind_max": wind, "uv_max": uv, "code": 0, "desc": "晴"},
        "hours": hours, "feel_max": feel_max, "feel_min": feel_min,
        "feel_mean": feel_mean, "stale": False,
    }


def item(iid, slot, category, clo, formality, color="黑", material="棉",
         name=None, photo="", **kw):
    data = {
        "id": iid, "name": name or iid, "slot": slot, "category": category,
        "color": color, "material": material, "clo": clo, "formality": formality,
        "season": ["winter", "autumn"], "status": "clean", "last_worn": None,
        "photo": photo, "waterproof": False, "windproof": False,
        "sun_protective": False, "sport": False, "wear_count": 0,
    }
    data.update(kw)
    return data


def wardrobe():
    """一套冬天的衣柜：够冷、够正式度、外层有三个选择，能凑出三套不同方案。"""
    return [
        item("b1", "base", "shirt", 0.26, 3, "藏青", "羊毛", "藏青羊毛衬衫"),
        item("b2", "base", "shirt", 0.22, 3, "白", "棉", "白衬衫"),
        item("b3", "base", "thermal", 0.26, 0, "黑", "棉", "黑色保暖内衣"),
        item("m1", "mid", "cardigan", 0.42, 3, "驼", "羊绒", "驼色羊绒开衫"),
        item("m2", "mid", "sweater", 0.42, 2, "灰", "羊毛", "灰色羊毛针织衫"),
        item("m3", "mid", "sweater", 0.42, 2, "黑", "羊毛", "黑色羊毛针织衫"),
        # 荧光劳保背心：clo 与中层目标几乎相同，正是「数学最优、现实最错」的陷阱
        item("m4", "mid", "vest_down", 0.46, 2, "绿", "羽绒", "绿马甲2",
             photo="photos/上衣_426_飞翔大雁_高可视警示网眼马甲_一体式件.jpg"),
        item("o1", "outer", "coat", 0.85, 3, "卡其", "加绒", "卡其大衣"),
        item("o2", "outer", "coat", 0.85, 3, "驼", "羊毛", "驼色大衣"),
        item("o3", "outer", "down_jacket", 0.92, 2, "黑", "羽绒", "黑羽绒服"),
        item("p1", "bottom", "dress_pants", 0.26, 4, "黑", "羊毛混纺", "黑西裤"),
        item("p2", "bottom", "trousers", 0.3, 3, "深灰", "羊毛", "深灰长裤"),
        item("p3", "bottom", "jeans", 0.31, 2, "蓝", "牛仔", "蓝牛仔裤"),
        item("s1", "shoes", "shoes_leather", 0.18, 4, "黑", "牛皮", "黑皮鞋"),
        item("s2", "shoes", "shoes_leather", 0.2, 4, "棕", "牛皮", "棕皮鞋"),
        item("s3", "shoes", "boots", 0.24, 3, "黑", "牛皮", "黑短靴"),
        item("a1", "accessory", "jewelry", 0.0, 3, "白", "银", "银项链"),
        item("a2", "accessory", "jewelry", 0.0, 3, "白", "银", "银耳钉"),
    ]


def ctx_for(events=None, w=None):
    w = w or make_weather()
    return CTX.build_context(events or [], w)


class TestCategoryBan(unittest.TestCase):
    def test_hivis_vest_never_enters_dress_pool(self):
        """荧光高可视背心不进候选池：只看 name 会漏，原始商品名在图片文件名里。"""
        w = make_weather()
        ctx = ctx_for([{"title": "客户方案沟通"}], w)
        pools = REC.build_candidates(wardrobe(), ctx, w)
        names = [c["item"]["name"] for c in pools["mid"]]
        self.assertNotIn("绿马甲2", names)
        self.assertEqual(len(pools["mid"]), 3, "禁掉背心后应剩下三件正常的中间层")

    def test_workwear_allowed_only_at_home(self):
        """居家（正式度 0）时不拦：那是它该出现的地方。"""
        w = make_weather()
        ctx = ctx_for([{"title": "居家休息"}], w)
        self.assertEqual(ctx["formality"], 0)
        pools = REC.build_candidates(wardrobe(), ctx, w)
        self.assertIn("绿马甲2", [c["item"]["name"] for c in pools["mid"]])

    def test_vest_down_banned_above_business(self):
        """羽绒马甲正式度标 2 也进不了商务场合：分值分不出「层次」和「邋遢」。"""
        self.assertTrue(REC._banned_for_dress(
            item("x", "mid", "vest_down", 0.46, 2), "mid", need_formal=3))
        self.assertFalse(REC._banned_for_dress(
            item("x", "mid", "vest_down", 0.46, 2), "mid", need_formal=2))
        # 羊绒衫同分同 clo，但它是正经中间层
        self.assertFalse(REC._banned_for_dress(
            item("y", "mid", "cardigan", 0.42, 2), "mid", need_formal=4))

    def test_mid_band_lets_sweater_into_formal(self):
        """中层比其它层松一档：按 (3,4) 卡会把所有羊绒衫挡在门外。"""
        w = make_weather()
        ctx = ctx_for([{"title": "客户方案沟通"}], w)
        self.assertEqual(ctx["formality"], 4)
        pools = REC.build_candidates(wardrobe(), ctx, w)
        mids = [c["item"]["name"] for c in pools["mid"]]
        self.assertIn("驼色羊绒开衫", mids, "正式场合的中层应当有羊绒开衫可选")
        self.assertNotIn("绿马甲2", mids)


class TestFormalityWorstWins(unittest.TestCase):
    def _score(self, formality_map, req=4):
        w = make_weather()
        ctx = {"formality": req, "formality_label": C.FORMALITY_LABELS[req],
               "slot_temp": {"base": 5, "mid": 5, "outer": 1, "bottom": 5, "shoes": 5}}
        chosen = []
        for iid, slot, formal in formality_map:
            chosen.append({"item": item(iid, slot, "x", 0.4, formal), "slot": slot,
                           "warm_fit": 0.9, "formal": formal, "days": 30})
        return REC.score_combo(chosen, ctx, w,
                               ["base", "mid", "outer"], allow_missing=True)

    def test_one_bad_item_drags_score_down(self):
        """七件里一件不达标，不应该被六件稀释掉——正式场合由最差那件决定。"""
        good = self._score([("a", "base", 4), ("b", "mid", 4), ("c", "outer", 4),
                            ("d", "bottom", 4), ("e", "shoes", 4), ("f", "accessory", 4),
                            ("g", "accessory", 4)])
        bad = self._score([("a", "base", 4), ("b", "mid", 4), ("c", "outer", 4),
                           ("d", "bottom", 1), ("e", "shoes", 4), ("f", "accessory", 4),
                           ("g", "accessory", 4)])
        self.assertAlmostEqual(good["parts"]["formality"], 1.0, places=3)
        # 平均口径下这条牛仔裤只扣 0.043（0.9/7），现在必须低于 0.6
        self.assertLess(bad["parts"]["formality"], 0.6,
                        "一条牛仔裤混进正式场合，罚分不能被其它六件摊薄")


class TestDiversity(unittest.TestCase):
    def test_three_sets_differ_in_core_slots(self):
        """三套方案不能只换一件外套的颜色。"""
        w = make_weather()
        ctx = ctx_for([{"title": "客户方案沟通"}], w)
        recs, _, _ = REC.recommend(wardrobe(), ctx, w, top_n=3, today=TODAY)
        self.assertEqual(len(recs), 3)
        sigs = [{o["slot"]: o["item"]["id"] for o in r["outfit"]
                 if o["slot"] in REC.CORE_SLOTS} for r in recs]
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                diff = sum(1 for s in REC.CORE_SLOTS if sigs[i].get(s) != sigs[j].get(s))
                self.assertGreaterEqual(diff, 2,
                                        f"第{i + 1}套与第{j + 1}套几乎一样（只差 {diff} 层）")


class TestTimelineConsistency(unittest.TestCase):
    def test_overlapping_events_are_clipped(self):
        """考试 9-12 与客户沟通 11-12 重叠，前一段必须在 11:00 收尾。"""
        w = make_weather()
        segs = TL.build_segments([
            {"start": "09:00", "end": "12:00", "title": "考试"},
            {"start": "11:00", "end": "12:00", "title": "客户方案沟通"},
        ], w)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0]["end"], segs[1]["start"], "两段不能互相覆盖")
        for a, b in zip(segs, segs[1:]):
            self.assertLessEqual(a["end"], b["start"], "时间轴必须单向不重叠")

    def test_same_outfit_segments_merge(self):
        """同一身衣服穿到下午，应该并成一段，而不是两张卡让人以为要换装。"""
        w = make_weather(feel_mean=12, feel_min=9, feel_max=16)
        plan = TL.plan_day(wardrobe(), [
            {"start": "09:00", "end": "10:00", "title": "部门例会"},
            {"start": "14:00", "end": "16:00", "title": "项目数据整理"},
        ], w)
        self.assertEqual(plan["segment_count"], 1)
        seg = plan["segments"][0]
        self.assertEqual(seg["time_end"], "16:00")
        self.assertIn("项目数据整理", seg["events"])


class TestAccessoryCapOnStudyDay(unittest.TestCase):
    def test_study_day_allows_single_accessory(self):
        """文昌日 advice 说「配饰最多一件」，代码就得只给一件。"""
        w = make_weather()
        ctx = ctx_for([{"title": "客户方案沟通"}], w)
        base, _, _ = REC.recommend(wardrobe(), ctx, w, top_n=1, today=TODAY)
        acc_base = [o for o in base[0]["outfit"] if o["slot"] == "accessory"]

        ctx2 = {**ctx, "study": {"flag": True, "careful": False, "level": "strong",
                                 "note": "文昌日", "exam_note": "配饰最多一件"}}
        recs, _, _ = REC.recommend(wardrobe(), ctx2, w, top_n=1, today=TODAY)
        acc = [o for o in recs[0]["outfit"] if o["slot"] == "accessory"]
        self.assertLessEqual(len(acc), 1)
        self.assertGreaterEqual(len(acc_base), 1, "普通日子项链+耳钉的组合不该被误删")


class TestReasonMatchesItem(unittest.TestCase):
    def test_heavy_base_not_called_light(self):
        """加绒加厚保暖衬衫不能说「要轻要透气」——那是模板句在打自己。"""
        w = make_weather()
        ctx = ctx_for([{"title": "办公"}], w)
        heavy = item("h1", "base", "shirt", 0.26, 3, "藏青", "羊毛",
                     "藏青羊毛加绒保暖衬衫")
        text = REC.explain({"item": heavy, "slot": "base", "warm_fit": 0.9,
                            "formal": 3, "days": 3}, ctx, w)
        self.assertNotIn("轻要透气", text)
        self.assertIn("锁温", text)


if __name__ == "__main__":
    unittest.main()
