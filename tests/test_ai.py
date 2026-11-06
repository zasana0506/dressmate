# -*- coding: utf-8 -*-
"""AI 视觉识别接入相关的回归测试（不联网、不碰真实衣橱数据）。

覆盖：
- 视觉模型返回的「自由文本色名」归一化（否则配色分会整体失真）
- 同名照片重传时的「恢复」识别（照片丢失后的补救路径）
- AI 结果合并进单品时字段类型/范围收敛
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import server as S                       # noqa: E402
from engine import config as C           # noqa: E402
from engine import recommend as REC      # noqa: E402


class ColorNormalizationTests(unittest.TestCase):
    """视觉模型常写「藏青色」「深蓝色」，引擎色表只有「藏青」「深蓝」。"""

    def test_suffix_stripped(self):
        self.assertEqual(C.normalize_color("藏青色"), "藏青")
        self.assertEqual(C.normalize_color("米白色"), "米白")
        self.assertEqual(C.normalize_color("灰色"), "灰")
        self.assertEqual(C.normalize_color("黑色"), "黑")

    def test_exact_passthrough(self):
        for c in ("藏青", "米白", "驼", "酒红", "燕麦"):
            self.assertEqual(C.normalize_color(c), c)

    def test_containment_prefers_longer_match(self):
        # 「深藏青」应落到「藏青」，不能被单个字「米/白」之类抢先
        self.assertEqual(C.normalize_color("深藏青"), "藏青")
        self.assertEqual(C.normalize_color("浅米白"), "米白")
        self.assertEqual(C.normalize_color("暗酒红"), "酒红")

    def test_empty_and_unknown(self):
        self.assertEqual(C.normalize_color(""), "黑")
        self.assertEqual(C.normalize_color(None), "黑")
        # 未知色保持原样，交给配色规则当作点缀色
        self.assertEqual(C.normalize_color("荧光青"), "荧光青")

    def test_harmony_not_broken_by_free_text_colors(self):
        """修复前：全中性色也会被当成多个点缀色系，配色分掉到 0.55 以下。"""
        neutral = ["藏青色", "米白色", "黑色", "深灰色"]
        self.assertEqual(REC.harmony_score(neutral), 1.0)
        # 中性色 + 1 个点缀色，仍应满分
        self.assertEqual(REC.harmony_score(["藏青色", "酒红色"]), 1.0)
        # 两个不同点缀色系 → 0.85
        self.assertEqual(REC.harmony_score(["酒红色", "墨绿色"]), 0.85)


class PhotoRestoreTests(unittest.TestCase):
    """照片文件丢失后，重传同名文件应恢复原条目而不是新增一条。"""

    def setUp(self):
        self.items = [
            {"id": "w001", "name": "藏青衬衫", "photo": "photos/藏青衬衫.jpg"},
            {"id": "w002", "name": "黑色西裤", "photo": "photos/黑西裤.jpg"},
        ]

    def test_match_returns_existing_item(self):
        hit = S.find_photo_owner("藏青衬衫.jpg", self.items)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["id"], "w001")

    def test_no_match_for_new_photo(self):
        self.assertIsNone(S.find_photo_owner("新衣服.jpg", self.items))

    def test_match_ignores_directory_part(self):
        # 条目里存的是 photos/xxx.jpg，比对时必须只看文件名
        hit = S.find_photo_owner("黑西裤.jpg", self.items)
        self.assertEqual(hit["id"], "w002")

    def test_item_without_photo_is_safe(self):
        items = [{"id": "w003", "name": "无照片"}]
        self.assertIsNone(S.find_photo_owner("任意.jpg", items))


class SafeFilenameTests(unittest.TestCase):
    def test_windows_drive_letter_not_eaten(self):
        # 历史缺陷：ntpath.basename 把「黑:」当盘符，吃掉文件名开头
        self.assertEqual(S.safe_filename("黑:色?衬*衫.jpg"), "黑色衬衫.jpg")

    def test_only_extension(self):
        self.assertEqual(S.safe_filename(".jpg"), "未命名单品.jpg")


if __name__ == "__main__":
    unittest.main(verbosity=2)
