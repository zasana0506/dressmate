# -*- coding: utf-8 -*-
"""发布前自检：确认要进仓库的东西齐全，且不含私人数据。

为什么需要这个：仓库一旦推上去，删改都要重写历史，很麻烦。
所以推之前先在这里过一遍——该有的文件在不在，不该有的文件是不是被挡住了。

用法：
    python tools/check_release.py
"""
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 必须进仓库的文件
REQUIRED = [
    "server.py",
    "Dockerfile",
    "docker-compose.yml",
    "docker-entrypoint.sh",
    ".dockerignore",
    ".gitignore",
    "LICENSE",
    "README.md",
    "README.zh-CN.md",
    "CONTRIBUTING.md",
    "samples/wardrobe.json",
    "data/cities.json",
    "web/index.html",
    "engine/styling.py",
    "engine/recommend.py",
    "engine/extras.py",
    "engine/city.py",
    "engine/weather.py",
    "engine/config.py",
    "engine/paths.py",
]

# 绝对不能进仓库的路径
FORBIDDEN_PREFIX = [
    "wardrobe/photos",
    "data/server.log",
    "reports",
]

# 绝对不能出现在仓库里的文件名
FORBIDDEN_NAMES = [
    "wardrobe.json",   # 真实衣橱（samples/ 下的例外）
    "profile.json",    # 含出生日期
    "schedule.json",
    "wear_log.json",
    "cloud-config.js", # 含发布密钥
]


def run_git(args):
    try:
        p = subprocess.run(["git"] + args, cwd=BASE_DIR,
                           capture_output=True, text=True, timeout=60)
        return p.stdout if p.returncode == 0 else None
    except Exception:
        return None


def main():
    print("=== 1. 必需文件 ===")
    missing = []
    for rel in REQUIRED:
        full = os.path.join(BASE_DIR, rel)
        ok = os.path.exists(full)
        size = os.path.getsize(full) if ok else 0
        print(f"  {'OK ' if ok else '缺失'} {rel}" + (f"  ({size:,} 字节)" if ok else ""))
        if not ok:
            missing.append(rel)

    print("\n=== 2. 私人数据是否被挡住 ===")
    leaks = []
    for rel in FORBIDDEN_PREFIX:
        full = os.path.join(BASE_DIR, rel)
        if os.path.exists(full):
            n = sum(len(fs) for _, _, fs in os.walk(full)) if os.path.isdir(full) else 1
            print(f"  警告 {rel} 存在（{n} 个文件），确认它被 .gitignore 挡住")
    for dirpath, dirnames, filenames in os.walk(BASE_DIR):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", "node_modules", ".venv")]
        for fn in filenames:
            if fn in FORBIDDEN_NAMES:
                rel = os.path.relpath(os.path.join(dirpath, fn), BASE_DIR).replace("\\", "/")
                if rel.startswith("samples/"):
                    continue
                print(f"  警告 发现 {rel}")
                leaks.append(rel)

    print("\n=== 3. git 追踪状态 ===")
    tracked = run_git(["ls-files"])
    if tracked is None:
        print("  还没初始化 git，跳过。")
    else:
        files = [f for f in tracked.split("\n") if f.strip()]
        print(f"  已追踪 {len(files)} 个文件")
        bad = [f for f in files
               if any(f.startswith(p) for p in FORBIDDEN_PREFIX)
               or os.path.basename(f) in FORBIDDEN_NAMES]
        for f in bad:
            print(f"  危险 {f} 被追踪了")
        if not bad:
            print("  没有私人文件被追踪")
        big = [f for f in files
               if os.path.exists(os.path.join(BASE_DIR, f))
               and os.path.getsize(os.path.join(BASE_DIR, f)) > 5 * 1024 * 1024]
        for f in big:
            print(f"  过大 {f}（>5MB）")

    print("\n=== 4. 引擎自检 ===")
    sys.path.insert(0, BASE_DIR)
    try:
        from engine import styling, extras, city, recommend  # noqa: F401
        print("  OK 引擎模块导入正常")
    except Exception as exc:
        print(f"  失败 {exc}")

    print("\n=== 5. 样例衣橱 ===")
    try:
        import json
        p = os.path.join(BASE_DIR, "samples", "wardrobe.json")
        d = json.load(open(p, encoding="utf-8"))
        its = d.get("items") or []
        slots = {}
        for it in its:
            slots[it.get("slot")] = slots.get(it.get("slot"), 0) + 1
        print(f"  OK {len(its)} 件，覆盖 " +
              " ".join(f"{k}:{v}" for k, v in sorted(slots.items())))
    except Exception as exc:
        print(f"  失败 {exc}")

    print("\n" + ("全部通过" if not missing and not leaks else
                  f"还有问题：缺 {len(missing)} 个文件，{len(leaks)} 处泄露风险"))


if __name__ == "__main__":
    main()
