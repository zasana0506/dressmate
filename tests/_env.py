# -*- coding: utf-8 -*-
"""测试环境隔离。

为什么要这个：推荐引擎会读 data/profile.json（出生日期+性别）。
那是**开发者本机的真实档案**，内容会变——比如档案里写了「8 岁」，
正式度就被封顶到休闲档，用例里断言的正式度自然对不上。

所以测试必须保证：
1. 读不到磁盘上的真实档案（除非用例显式要测档案）
2. 不写脏真实衣橱

做法是设一个环境变量，让 identity 模块主动放弃读磁盘档案。
用例要测具体身份时，调用 identity 的函数直接传档案，不走磁盘。
"""
import os

# 让 identity.load_profile() 读不到磁盘档案
os.environ.setdefault("DRESSMATE_PROFILE", "__none__")

# 测试期间不要把衣橱写到真实位置
os.environ.setdefault("DRESSMATE_DATA_DIR", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_tmp_data"))
os.environ.setdefault("DRESSMATE_WARDROBE_PATH", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "_tmp_wardrobe.json"))
