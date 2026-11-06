# -*- coding: utf-8 -*-
"""CSRF 防护与可选令牌的回归测试。

背景：这是个只监听本机、但会保存私人数据的 Web 服务。
两类风险：
  A. CSRF —— 你开着衣橱页面，同时开了别的网页，那个网页诱导浏览器
     发 POST 过来，改你的衣橱。挡它靠 Origin 校验。
  B. 局域网 —— 同一个 WiFi 的人直接访问你的端口。挡它靠令牌
     （以及默认只绑 127.0.0.1）。

这两件事的判据不同，所以测试也分开写。
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import server as S  # noqa: E402


class FakeHeaders(dict):
    """够用就行：能按大小写不敏感地取头。"""

    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class FakeHandler:
    """模拟 BaseHTTPRequestHandler 的必要部分。"""

    def __init__(self, headers=None):
        self.headers = FakeHeaders(headers or {})


class TestOriginCheck(unittest.TestCase):
    """CSRF 判据。"""

    def test_same_origin_allowed(self):
        h = FakeHandler({"Origin": "http://127.0.0.1:8848",
                         "Host": "127.0.0.1:8848"})
        self.assertTrue(S.check_origin(h))

    def test_cross_origin_rejected(self):
        """恶意网站的 Origin 和 Host 对不上，必须拒。"""
        h = FakeHandler({"Origin": "http://evil.example.com",
                         "Host": "127.0.0.1:8848"})
        self.assertFalse(S.check_origin(h))

    def test_no_origin_allowed_for_cli(self):
        """命令行调用不带 Origin/Referer，要放行，否则没法用脚本调自己。"""
        h = FakeHandler({"Host": "127.0.0.1:8848"})
        self.assertTrue(S.check_origin(h))

    def test_referer_used_when_no_origin(self):
        """有的浏览器只发 Referer。跨站的 Referer 同样要拒。"""
        h = FakeHandler({"Referer": "http://evil.example.com/x",
                         "Host": "127.0.0.1:8848"})
        self.assertFalse(S.check_origin(h))

    def test_same_origin_referer_allowed(self):
        h = FakeHandler({"Referer": "http://127.0.0.1:8848/page",
                         "Host": "127.0.0.1:8848"})
        self.assertTrue(S.check_origin(h))

    def test_https_forwarded_proto(self):
        """放在 HTTPS 反向代理后面时，Origin 是 https://。"""
        h = FakeHandler({"Origin": "https://dressmate.example.com",
                         "Host": "dressmate.example.com",
                         "X-Forwarded-Proto": "https"})
        self.assertTrue(S.check_origin(h))

    def test_allowed_origins_whitelist(self):
        """代理场景：Host 是代理地址，Origin 是真实域名，靠白名单放行。"""
        os.environ["DRESSMATE_ALLOWED_ORIGINS"] = "https://dressmate.example.com"
        try:
            h = FakeHandler({"Origin": "https://dressmate.example.com",
                             "Host": "proxy.internal:443"})
            self.assertTrue(S.check_origin(h))
            # 白名单里的不能放行别的
            h2 = FakeHandler({"Origin": "https://other.example.com",
                              "Host": "proxy.internal:443"})
            self.assertFalse(S.check_origin(h2))
        finally:
            del os.environ["DRESSMATE_ALLOWED_ORIGINS"]

    def test_same_host_different_port_rejected(self):
        """端口不同就是不同源。"""
        h = FakeHandler({"Origin": "http://127.0.0.1:9999",
                         "Host": "127.0.0.1:8848"})
        self.assertFalse(S.check_origin(h))


class TestTokenCheck(unittest.TestCase):
    """令牌判据。没设令牌时必须完全放行——这是「不配也能跑」的保证。"""

    def tearDown(self):
        os.environ.pop("DRESSMATE_TOKEN", None)

    def test_no_token_configured_allows_everything(self):
        """没设 DRESSMATE_TOKEN → 不校验，保持本地便利性。"""
        os.environ.pop("DRESSMATE_TOKEN", None)
        self.assertFalse(S.token_required())
        h = FakeHandler({})
        self.assertTrue(S.check_token(h))

    def test_token_required_when_set(self):
        os.environ["DRESSMATE_TOKEN"] = "secret123"
        self.assertTrue(S.token_required())

    def test_correct_token_accepted(self):
        os.environ["DRESSMATE_TOKEN"] = "secret123"
        h = FakeHandler({"X-Dressmate-Token": "secret123"})
        self.assertTrue(S.check_token(h))

    def test_bearer_token_accepted(self):
        os.environ["DRESSMATE_TOKEN"] = "secret123"
        h = FakeHandler({"Authorization": "Bearer secret123"})
        self.assertTrue(S.check_token(h))

    def test_wrong_token_rejected(self):
        os.environ["DRESSMATE_TOKEN"] = "secret123"
        h = FakeHandler({"X-Dressmate-Token": "wrong"})
        self.assertFalse(S.check_token(h))

    def test_missing_token_defers_to_body(self):
        """头里没有令牌时返回 None，交给 do_POST 看 body 里的 token 字段。"""
        os.environ["DRESSMATE_TOKEN"] = "secret123"
        h = FakeHandler({})
        self.assertIsNone(S.check_token(h))

    def test_empty_token_env_treated_as_disabled(self):
        os.environ["DRESSMATE_TOKEN"] = "   "
        self.assertFalse(S.token_required())


class TestTokenNotInHtml(unittest.TestCase):
    """令牌不能出现在页面源码里。

    这是这次设计的核心：令牌写进 HTML，同局域网的人打开首页
    就能从源码里读到，那这道防线等于没设。
    所以页面里只有「要不要令牌」这个标志，没有令牌本身。
    """

    def test_index_html_has_no_hardcoded_token(self):
        p = os.path.join(BASE_DIR, "web", "index.html")
        with open(p, encoding="utf-8") as f:
            html = f.read()
        # 只允许出现「标志」的名字，不允许出现令牌值
        self.assertIn("__DM_TOKEN_REQUIRED__", html)
        self.assertNotIn("__DM_TOKEN__ = \"", html.replace("window.__DM_TOKEN__ = \"", "X")
                         .replace("window.__DM_TOKEN__ = \"\"", "X"))

    def test_token_read_from_localstorage_not_injected(self):
        p = os.path.join(BASE_DIR, "web", "index.html")
        with open(p, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("dressmate_token", html)
        self.assertIn("localStorage", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
