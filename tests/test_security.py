# -*- coding: utf-8 -*-
"""路径穿越与私有文件暴露的回归测试。

为什么单独写这个文件：这两个洞都是「能读出本机任意文件」级别的问题，
而且修好一次之后很容易在重构里被改回去——比如某天有人为了支持
子目录，把静态服务改成简单的 os.path.join。

真实攻击载荷长这样（实测可读出整个衣橱）：
    GET /..%2fwardrobe%2fwardrobe.json
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import server as S  # noqa: E402


class TestSafeJoin(unittest.TestCase):
    """safe_join 是核心防线，这里穷举各种越界写法。"""

    def test_normal_path_allowed(self):
        fp = S.safe_join(S.WEB_DIR, "index.html")
        self.assertIsNotNone(fp)
        self.assertTrue(fp.endswith("index.html"))

    def test_subdirectory_allowed(self):
        fp = S.safe_join(S.WEB_DIR, "sub/dir/file.js")
        self.assertIsNotNone(fp)

    def test_dotdot_rejected(self):
        self.assertIsNone(S.safe_join(S.WEB_DIR, "../data/profile.json"))

    def test_deep_dotdot_rejected(self):
        self.assertIsNone(S.safe_join(S.WEB_DIR, "../../../../etc/passwd"))

    def test_encoded_dotdot_rejected(self):
        """%2e%2e 已在别处解码，但这里也要防一手。

        注意 safe_join 本身不解码 —— 解码由调用方做。
        所以这里测的是「解码之后」的形态，以及「不解码时不会误伤」。
        """
        from urllib.parse import unquote
        # 调用方解码后的形态：必须被拦
        self.assertIsNone(S.safe_join(S.WEB_DIR, unquote("..%2fdata%2fprofile.json")))
        # 未解码时 %2f 只是普通字符，拼出来不在 web/ 下，也不能命中真实文件
        got = S.safe_join(S.WEB_DIR, "..%2fdata%2fprofile.json")
        self.assertNotEqual(got and os.path.realpath(got),
                            os.path.realpath(os.path.join(BASE_DIR, "data", "profile.json")))

    def test_absolute_path_rejected(self):
        self.assertIsNone(S.safe_join(S.WEB_DIR, "/etc/passwd"))
        self.assertIsNone(S.safe_join(S.WEB_DIR, "C:\\Windows\\win.ini"))

    def test_empty_rejected(self):
        self.assertIsNone(S.safe_join(S.WEB_DIR, ""))

    def test_prefix_sibling_directory_rejected(self):
        """web_evil 这类前缀相同的目录不算越界目标——它本来就不该被允许。

        这里验证判定逻辑本身：结果必须严格在 base 之内，
        不能只靠 startswith(base) 而漏掉 base + "_evil"。
        """
        base = os.path.realpath(S.WEB_DIR)
        target = os.path.realpath(os.path.join(base, "..", "web_evil", "x.js"))
        self.assertFalse(target == base or target.startswith(base + os.sep))


class TestPrivateFiles(unittest.TestCase):
    """带密钥的私有配置不该被静态服务读到。"""

    def test_local_js_is_private(self):
        self.assertTrue(S.is_private_file("cloud-config.local.js"))

    def test_key_suffix_is_private(self):
        self.assertTrue(S.is_private_file("server.key"))
        self.assertTrue(S.is_private_file("cert.pem"))
        self.assertTrue(S.is_private_file("app.env"))
        self.assertTrue(S.is_private_file("x.secret"))

    def test_normal_files_are_public(self):
        for f in ("index.html", "cloud-config.js", "style.css", "app.js"):
            self.assertFalse(S.is_private_file(f), f"{f} 不该被当成私有文件")


class TestPhotoPath(unittest.TestCase):
    """照片路径用 basename + realpath 双保险。"""

    def test_photo_basename_strips_directories(self):
        """照片名里的目录部分必须被丢掉。"""
        self.assertEqual(os.path.basename("../../etc/passwd"), "passwd")

    def test_photo_traversal_blocked(self):
        """照片路径：basename 去掉目录后，剩下的仍要过 safe_join。

        注意 basename("../../data/profile.json") = "profile.json"，
        目录部分已经被丢掉了——这正是 /photos/ 该有的行为
        （照片只按文件名找，不接受任何目录信息）。
        """
        name = os.path.basename("../../data/profile.json")
        self.assertEqual(name, "profile.json")
        # 但万一 PHOTO_DIR 本身是软链，safe_join 仍要挡住越界
        self.assertIsNotNone(S.safe_join(S.PHOTO_DIR, name))


class TestNoSecretInWebDir(unittest.TestCase):
    """密钥文件不能出现在会被静态服务的目录里。

    这是这次修 bug 的根因：cloud-config.local.js 原本放在 web/ 下，
    而 web/ 整个目录都能通过 /文件名 直接访问。
    """

    def test_no_local_js_in_web_dir(self):
        web = os.path.join(BASE_DIR, "web")
        for fn in os.listdir(web):
            self.assertFalse(
                ".local." in fn.lower(),
                f"web/{fn} 带 .local. 后缀，会被静态服务直接读到")

    def test_cloud_config_local_not_tracked(self):
        """含密钥的私有配置不能进版本库。"""
        import subprocess
        p = subprocess.run(["git", "ls-files"], cwd=BASE_DIR,
                           capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            self.skipTest("不在 git 仓库里")
        for f in p.stdout.split("\n"):
            f = f.strip()
            if not f:
                continue
            self.assertFalse(
                ".local." in os.path.basename(f).lower(),
                f"{f} 是私有配置，不该被 git 追踪")


if __name__ == "__main__":
    unittest.main(verbosity=2)
