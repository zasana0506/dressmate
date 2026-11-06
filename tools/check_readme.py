# -*- coding: utf-8 -*-
"""检查中英两版 README 的一致性。

为什么需要这个：README 有中文版和英文版两份，改了一处忘了另一处，
GitHub 上就会出现「英文版说 254 个测试、中文版说 286 个」这种矛盾。
双语文档最容易在数字上打架，所以专门加个检查。

用法：
    python tools/check_readme.py
"""
import io
import os
import re
import sys

# 强制 UTF-8 输出：CI 的 locale 是 C，print 中文会抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZH = os.path.join(BASE_DIR, "README.zh-CN.md")
EN = os.path.join(BASE_DIR, "README.md")

# 两版必须一致的关键数字
KEY_NUMBERS = ["323", "31", "19", "35", "12", "7", "8848", "3.4", "0.40"]

# 两版必须都有的环境变量
ENV_VARS = [
    "DRESSMATE_DATA_DIR",
    "DRESSMATE_PHOTO_DIR",
    "DRESSMATE_WARDROBE_PATH",
    "DRESSMATE_AI_BASE_URL",
    "DRESSMATE_AI_API_KEY",
    "DRESSMATE_AI_MODEL",
    "DRESSMATE_TOKEN",
    "DRESSMATE_ALLOWED_ORIGINS",
    "PORT",
]

# 两版必须都有的规则名
RULE_NAMES = [
    "three_colors", "shoe_jump", "sneaker_dress_pants", "sneaker_tailored_outer",
    "shoe_drops_tier", "outer_drops_tier", "tone_up_dark",
    "belt_mismatch", "sock_contrast", "tie_clash", "bag_jump",
    "skirt_short", "hosiery_gap", "sheer_bottom",
]

# 英文版里不该出现的中文（例外：文件名示例与语言切换）
ZH_ALLOWED_IN_EN = ["简体中文", "一键启动.bat", "藏青长袖衬衫.jpg"]


def count(text, token):
    return len(re.findall(r"(?<![\d.])" + re.escape(token) + r"(?![\d.])", text))


def main():
    zh = io.open(ZH, encoding="utf-8").read()
    en = io.open(EN, encoding="utf-8").read()
    problems = []

    print("=== 1. 关键数字 ===")
    for n in KEY_NUMBERS:
        a, b = count(zh, n), count(en, n)
        ok = a > 0 and b > 0
        print(f"  {'OK ' if ok else '不一致'} {n:<6} 中文 {a} 次, 英文 {b} 次")
        if not ok:
            problems.append(f"数字 {n} 两版不一致")

    print("\n=== 2. 环境变量 ===")
    for v in ENV_VARS:
        a, b = v in zh, v in en
        ok = a and b
        print(f"  {'OK ' if ok else '不一致'} {v}")
        if not ok:
            problems.append(f"环境变量 {v} 缺失")

    print("\n=== 3. 规则名 ===")
    missing = []
    for r in RULE_NAMES:
        a, b = r in zh, r in en
        if not (a and b):
            missing.append(r)
    if missing:
        print(f"  不一致 {missing}")
        problems.append(f"规则名缺失 {missing}")
    else:
        print(f"  OK 全部 {len(RULE_NAMES)} 个规则名两版都有")

    print("\n=== 4. 英文版的中文残留 ===")
    leftovers = []
    for i, line in enumerate(en.split("\n"), 1):
        if not re.search(r"[一-鿿]", line):
            continue
        if any(ok in line for ok in ZH_ALLOWED_IN_EN):
            continue
        leftovers.append(f"{i}: {line.strip()[:70]}")
    if leftovers:
        for x in leftovers:
            print(f"  残留 {x}")
        problems.append(f"英文版有 {len(leftovers)} 处中文残留")
    else:
        print("  OK 只有刻意保留的（语言切换与文件名示例）")

    print("\n=== 5. Markdown 结构 ===")
    for name, text in (("中文版", zh), ("英文版", en)):
        fences = text.count("```")
        links = re.findall(r"\]\((?!https?:)([^)#]+)", text)
        missing_files = [l for l in links if not os.path.exists(os.path.join(BASE_DIR, l))]
        ok = fences % 2 == 0 and not missing_files
        print(f"  {'OK ' if ok else '问题'} {name}: 代码块 {fences} 个, "
              f"链接 {len(links)} 个, 缺失文件 {missing_files or '无'}")
        if not ok:
            problems.append(f"{name} 结构问题")

    print("\n" + ("全部通过" if not problems else
                  "还有问题：\n  - " + "\n  - ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
