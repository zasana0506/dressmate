# -*- coding: utf-8 -*-
"""报告可选依赖的状态，给 CI 的 step summary 用。

为什么需要：紫微斗数功能要 Node.js + iztro，CI 的 runner 自带 Node
但没装 iztro。这个「本地有、CI 没有」的差异曾经让 CI 连挂四次，
而 GitHub 上看不出到底是哪个测试挂了。把依赖状态直接写进 summary，
下次出问题一眼就能看到。

用法：
    python tools/report_deps.py          # 输出 markdown
"""
import io
import os
import shutil
import sys

# 强制 UTF-8 输出：CI 的 locale 是 C，print 中文会抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def main():
    print("### 可选依赖")
    print()
    print("| 依赖 | 状态 | 说明 |")
    print("|---|---|---|")

    node = shutil.which("node")
    print(f"| Node.js | {'有' if node else '无'} | "
          f"{node or '紫微排盘功能不可用，不影响其它功能'} |")

    try:
        from engine import luck
        iztro = luck.iztro_available()
    except Exception as exc:
        iztro = False
        print(f"| iztro | 探测失败 | {exc} |")
    if iztro:
        print("| iztro | 有 | 紫微排盘可用 |")
    else:
        print("| iztro | 无 | 紫微排盘功能不可用，不影响其它功能 |")

    # 运行时依赖：这个必须齐，不然整个服务起不来
    print()
    print("### 运行时检查")
    print()
    try:
        from engine import styling, extras, city, recommend, weather  # noqa: F401
        print("引擎模块导入正常（纯标准库，无需 pip install）")
    except Exception as exc:
        print(f"引擎导入失败：{exc}")

    p = os.path.join(BASE_DIR, "data", "cities.json")
    if os.path.exists(p):
        print(f"城市表就位（{os.path.getsize(p):,} 字节）")
    else:
        print("城市表缺失 —— 城市查询会走在线兜底")
    return 0


if __name__ == "__main__":
    sys.exit(main())
