# -*- coding: utf-8 -*-
"""AI 识别链路的错误可读性测试。

背景：用户报「AI 识别失败」，但界面上只有四个字，没有原因。
排查了两轮才发现：错误在两层被吞掉了——

1. 前端 `fetchAsDataUrl` 里 `fr.onerror = rej` 用事件对象 reject，
   事件没有 `.message`，上层 catch 拿到的是 undefined。
2. 服务端把 urllib 的 HTTPError 原样抛出，
   用户看到「HTTP Error 400: Bad Request」这种天书。

这两个都要锁住，否则以后重构又会退回去。
"""
import io
import os
import re
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import server as S  # noqa: E402


def read_web():
    with io.open(os.path.join(BASE_DIR, "web", "index.html"), encoding="utf-8") as f:
        return f.read()


class TestErrorMessagesVisible(unittest.TestCase):
    """前端：错误必须能显示出来，不能被吞掉。"""

    def test_fetch_as_data_url_rejects_with_error(self):
        """fr.onerror 必须 reject(new Error(...))，不能直接 reject 事件对象。"""
        html = read_web()
        m = re.search(r"async function fetchAsDataUrl\(url\)\{(.*?)\n\}", html, re.S)
        self.assertIsNotNone(m, "找不到 fetchAsDataUrl")
        body = m.group(1)
        self.assertIn("fr.onerror", body)
        # 直接 rej(事件) 会让上层拿不到 message
        self.assertNotRegex(body, r"fr\.onerror\s*=\s*rej\s*;",
                            "fr.onerror 不能直接 reject 事件对象，错误信息会全丢")
        self.assertRegex(body, r"fr\.onerror\s*=\s*\(\)\s*=>\s*rej\(new Error",
                         "fr.onerror 必须用 Error 对象 reject")

    def test_catch_block_has_fallback_with_model(self):
        """兜底文案里要带上模型名——不然用户不知道该换哪个模型试。"""
        html = read_web()
        i = html.index("p.ai = \"err\"")
        block = html[i:i + 400]
        self.assertIn("p.aiNotes", block)
        self.assertIn("aiModel()", block,
                      "错误兜底文案里应该带上模型名，方便用户换模型重试")


class TestServerErrorMessages(unittest.TestCase):
    """服务端：HTTP 错误要翻译成能看懂的中文。"""

    def test_http_error_is_translated(self):
        """HTTPError 必须被捕获并转成可读信息。"""
        import inspect
        src = inspect.getsource(S.cloud_vision)
        self.assertIn("HTTPError", src,
                      "cloud_vision 必须捕获 HTTPError，否则用户看到的是天书")
        self.assertIn("云端返回", src)
        # 关键：不能只靠原样抛出
        self.assertNotIn("raise exc", src)

    def test_common_status_codes_have_hints(self):
        """常见状态码要有中文说明。"""
        import inspect
        src = inspect.getsource(S.cloud_vision)
        for code in ("400", "401", "429", "500"):
            self.assertIn(code, src, f"状态码 {code} 应该有中文说明")

    def test_empty_result_is_error(self):
        """云端返回空结果要报错，不能返回空字符串让前端解析失败。"""
        import inspect
        src = inspect.getsource(S.cloud_vision)
        self.assertIn("空结果", src)

    def test_log_includes_model_name(self):
        """日志要带模型名——排查时最缺的就是这个。"""
        import inspect
        src = inspect.getsource(S)
        self.assertIn("AI识别失败 模型", src)


class TestReRecognizeButton(unittest.TestCase):
    """「重新识别」按钮：AI 开关关着时不能静默失效。"""

    def test_reai_checks_toggle(self):
        html = read_web()
        i = html.index('box.querySelectorAll("[data-reai]")')
        block = html[i:i + 700]
        self.assertIn("aiEnabled()", block,
                      "重新识别按钮必须检查 AI 开关状态")
        self.assertIn("aiToggle", block,
                      "开关关着时要帮忙打开，而不是点了没反应")


if __name__ == "__main__":
    unittest.main(verbosity=2)
