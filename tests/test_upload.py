# -*- coding: utf-8 -*-
"""照片上传链路回归测试（不联网、不碰真实衣橱数据）。

运行：  python -m unittest discover -s tests -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: F401  测试环境隔离（不读本机真实档案）

import server as S                       # noqa: E402
from tools import import_photos as IP    # noqa: E402


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_photo = S.PHOTO_DIR
        self.old_wd = S.WARDROBE_PATH
        S.PHOTO_DIR = os.path.join(self.tmp, "photos")
        S.WARDROBE_PATH = os.path.join(self.tmp, "wardrobe.json")
        os.makedirs(S.PHOTO_DIR, exist_ok=True)
        with open(S.WARDROBE_PATH, "w", encoding="utf-8") as f:
            json.dump({"version": "1.0", "items": []}, f)

    def tearDown(self):
        S.PHOTO_DIR = self.old_photo
        S.WARDROBE_PATH = self.old_wd
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- 文件名安全 ---
    def test_path_traversal_is_stripped(self):
        self.assertEqual(S.safe_filename("../../etc/passwd.jpg"), "passwd.jpg")
        self.assertEqual(S.safe_filename("C:\\Users\\x\\藏青衬衫.jpg"), "藏青衬衫.jpg")

    def test_illegal_chars_and_empty_stem(self):
        self.assertEqual(S.safe_filename('黑:色?衬*衫.jpg'), "黑色衬衫.jpg")
        self.assertEqual(S.safe_filename(".jpg"), "未命名单品.jpg")

    def test_extension_whitelist(self):
        self.assertEqual(S.safe_filename("灰色卫衣.exe"), "灰色卫衣.jpg")
        self.assertEqual(S.safe_filename("米白针织.PNG"), "米白针织.png")

    def test_unique_filename_does_not_overwrite(self):
        with open(os.path.join(S.PHOTO_DIR, "藏青衬衫.jpg"), "wb") as f:
            f.write(b"old")
        got = S.unique_filename("藏青衬衫.jpg")
        self.assertEqual(got, "藏青衬衫_2.jpg")
        with open(os.path.join(S.PHOTO_DIR, got), "wb") as f:
            f.write(b"old2")
        self.assertEqual(S.unique_filename("藏青衬衫.jpg"), "藏青衬衫_3.jpg")
        # 已有文件必须保持原样
        with open(os.path.join(S.PHOTO_DIR, "藏青衬衫.jpg"), "rb") as f:
            self.assertEqual(f.read(), b"old")

    # --- 推断结果结构 ---
    def test_infer_one_shape_and_encoded_url(self):
        r = S.infer_one("黑色厚羽绒服.jpg")
        it = r["item"]
        self.assertEqual(it["slot"], "outer")
        self.assertEqual(it["category"], "down_jacket")
        self.assertGreaterEqual(it["clo"], 0.9)
        self.assertTrue(it["waterproof"] and it["windproof"])
        self.assertEqual(r["confidence"], "高")
        self.assertEqual(r["filename"], "黑色厚羽绒服.jpg")
        self.assertIn("%", r["url"], "中文文件名必须 URL 编码")
        self.assertEqual(it["photo"], "photos/黑色厚羽绒服.jpg")

    def test_uninformative_name_flagged_low_confidence(self):
        r = S.infer_one("IMG_1234.jpg")
        self.assertEqual(r["confidence"], "低")
        self.assertTrue(r["warnings"], "无信息文件名必须给出提醒")

    # --- 未入库扫描 ---
    def test_unimported_photos_excludes_known(self):
        open(os.path.join(S.PHOTO_DIR, "灰色卫衣.jpg"), "wb").write(b"x")
        open(os.path.join(S.PHOTO_DIR, "藏青衬衫.jpg"), "wb").write(b"x")
        with open(S.WARDROBE_PATH, "w", encoding="utf-8") as f:
            json.dump({"items": [{"id": "w1", "photo": "photos/灰色卫衣.jpg"}]}, f)
        pending = S.unimported_photos()
        self.assertEqual([p["filename"] for p in pending], ["藏青衬衫.jpg"])

    # --- 入库去重与编号 ---
    def test_merge_dedup_and_ids(self):
        items = []
        for name in ("藏青衬衫.jpg", "黑色厚羽绒服.jpg"):
            items.append(IP.infer(name)[0])
        data = {"items": []}
        self.assertEqual(IP.merge(data, items), 2)
        self.assertEqual(IP.merge(data, items), 0, "重复照片必须跳过")
        ids = [it["id"] for it in data["items"]]
        self.assertEqual(len(set(ids)), 2, "id 不能重复")
        self.assertEqual(len(data["items"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
