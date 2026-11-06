# -*- coding: utf-8 -*-
"""在没有 Docker 的机器上，验证「镜像里到底装了什么」。

为什么需要这个：Dockerfile 写错了，CI 里能发现，但本地要等半小时。
这个脚本按 Dockerfile + .dockerignore 的规则算出最终文件清单，
然后在一个干净目录里按这个清单铺开，真跑一遍服务。

所以它验的是同一件事：镜像里的东西够不够、能不能跑起来。

用法：
    python tools/verify_image.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dockerfile 里 COPY 的内容
COPY_ENTRIES = [
    ("engine/", "engine/"),
    ("tools/", "tools/"),
    ("web/", "web/"),
    ("samples/", "samples/"),
    ("data/cities.json", "data/cities.json"),
    ("data/climate.json", "data/climate.json"),
    ("server.py", "server.py"),
    ("docker-entrypoint.sh", "docker-entrypoint.sh"),
]

# .dockerignore 里排除的
IGNORE_DIRS = {"tests", "docs", ".git", ".github", "__pycache__", ".venv",
               "node_modules", ".idea", ".vscode"}
IGNORE_FILES = {
    "README.md", "README.zh-CN.md", "CONTRIBUTING.md", "LICENSE",
    ".gitignore", ".dockerignore", "docker-compose.yml",
    "start.py", "run.py", "一键启动.bat",
    "server.py.orig",
    "cloud-config.local.js",
}
IGNORE_TOOLS = {
    "feedback.py", "label_photos.py", "import_yfutupian.py", "migrate_meta.py",
    "fix_colors.py", "fix_jewelry.py", "build_cities.py", "check_wardrobe.py",
    "daily_push.py", "make_sample.py", "verify_image.py", "check_release.py",
}


def build_image_list():
    """算出镜像里的文件清单。"""
    files = []
    for src, dst in COPY_ENTRIES:
        full = os.path.join(BASE_DIR, src.rstrip("/").replace("/", os.sep))
        if os.path.isfile(full):
            files.append((full, dst))
            continue
        if not os.path.isdir(full):
            continue
        for dirpath, dirnames, filenames in os.walk(full):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            rel_dir = os.path.relpath(dirpath, BASE_DIR).replace("\\", "/")
            for fn in filenames:
                if fn.endswith(".pyc"):
                    continue
                rel = f"{rel_dir}/{fn}"
                # .dockerignore 里 *.md 排除规则，但 README 之类在 COPY 之外本来就不进
                if rel in IGNORE_FILES or fn in IGNORE_FILES:
                    continue
                if rel_dir == "tools" and fn in IGNORE_TOOLS:
                    continue
                files.append((os.path.join(dirpath, fn),
                              f"{dst}{rel[len(src.rstrip('/')) + 1:]}"))
    return files


def check_no_secrets(files):
    """确认镜像里没有密钥和私人数据。"""
    problems = []
    for src, dst in files:
        base = os.path.basename(src)
        if base in ("cloud-config.js", "cloud-config.local.js"):
            # 模板是空的、允许进镜像；带真实密钥的不行
            try:
                txt = open(src, encoding="utf-8").read()
            except Exception:
                txt = ""
            if re.search(r'publishableKey\s*:\s*"[^"]+"', txt):
                problems.append(f"{dst} 含发布密钥，不能进镜像")
            continue
        # samples/wardrobe.json 是刻意放的虚构样例，不算泄露
        if base in ("wardrobe.json", "profile.json", "schedule.json",
                    "wear_log.json") and not dst.startswith("samples/"):
            problems.append(f"{dst} 是私人数据，不能进镜像")
        if dst.startswith("wardrobe/photos/") or dst.endswith("/photos/"):
            problems.append(f"{dst} 是照片，不能进镜像")
        if dst.endswith(".log"):
            problems.append(f"{dst} 是日志，不能进镜像")
    return problems


def main():
    print("=== 1. 计算镜像文件清单 ===")
    files = build_image_list()
    total = 0
    for src, dst in sorted(files, key=lambda x: x[1]):
        sz = os.path.getsize(src)
        total += sz
    print(f"  {len(files)} 个文件，共 {total / 1024 / 1024:.2f} MB")
    by_top = {}
    for _, dst in files:
        top = dst.split("/")[0]
        by_top[top] = by_top.get(top, 0) + 1
    for k, v in sorted(by_top.items()):
        print(f"    {k}: {v}")

    print("\n=== 2. 检查密钥与私人数据 ===")
    problems = check_no_secrets(files)
    if problems:
        for p in problems:
            print(f"  危险 {p}")
    else:
        print("  OK 没有密钥和私人数据")

    print("\n=== 2b. 检查关键资产是否在镜像里 ===")
    names = {dst for _, dst in files}
    for need in ("data/cities.json", "data/climate.json",
                 "samples/wardrobe.json", "docker-entrypoint.sh"):
        if need in names:
            print(f"  OK {need}")
        else:
            print(f"  危险 {need} 不在镜像里")
            problems.append(f"{need} 缺失")

    print("\n=== 3. 在干净目录模拟镜像 ===")
    tmp = tempfile.mkdtemp(prefix="dressmate-image-")
    app = os.path.join(tmp, "app")
    data = os.path.join(tmp, "data")
    os.makedirs(app)
    os.makedirs(os.path.join(data, "photos"))
    for src, dst in files:
        target = os.path.join(app, dst.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
    print(f"  已铺到 {app}")

    print("\n=== 4. 跑入口脚本（首启播种）===")
    entry = os.path.join(app, "docker-entrypoint.sh")
    if not os.path.exists(entry):
        print("  失败 入口脚本没进镜像")
        return 1
    # Windows 上没有 sh，用 bash 跑；把 PATH 改成只留必要命令
    env = dict(os.environ)
    env.update({
        "APP_DIR": app,
        "DRESSMATE_DATA_DIR": data,
        "DRESSMATE_PHOTO_DIR": os.path.join(data, "photos"),
        "DRESSMATE_WARDROBE_PATH": os.path.join(data, "wardrobe.json"),
        "PORT": "8907",
    })
    # 入口脚本最后会 exec server.py，这里只验证前半段播种逻辑
    src = open(entry, encoding="utf-8").read()
    seed_only = src.split("exec python")[0]
    seed_script = os.path.join(tmp, "seed.sh")
    with open(seed_script, "w", encoding="utf-8", newline="\n") as f:
        f.write(seed_only)
    p = subprocess.run(["bash", seed_script], env=env, capture_output=True,
                       text=True, timeout=60)
    print("  " + (p.stdout.strip() or "(无输出)"))
    if p.stderr.strip():
        print("  stderr: " + p.stderr.strip()[:300])

    print("\n=== 5. 验证播种结果 ===")
    ok = True
    for name in ("cities.json", "wardrobe.json"):
        path = os.path.join(data, name)
        if os.path.exists(path):
            print(f"  OK {name} 已播种 ({os.path.getsize(path):,} 字节)")
        else:
            print(f"  失败 {name} 没播种")
            ok = False
    if os.path.exists(os.path.join(data, "photos")):
        print("  OK photos 目录已建")

    print("\n=== 6. 从模拟镜像起服务并实调推荐 ===")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(app, "server.py"), "8907"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=app,
    )
    try:
        health = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:8907/api/health", timeout=3) as r:
                    health = json.loads(r.read().decode("utf-8"))
                break
            except Exception:
                import time
                time.sleep(0.5)
        if not health:
            print("  失败 服务没起来")
            proc.terminate()
            return 1
        print(f"  OK 健康检查 {health}")

        with urllib.request.urlopen(
                "http://127.0.0.1:8907/api/recommend?city=Beijing",
                timeout=60) as r:
            rec = json.loads(r.read().decode("utf-8"))
        recs = rec.get("recommendations") or []
        if not recs:
            print("  失败 推荐接口没产出结果")
            ok = False
        else:
            names = [x.get("item", {}).get("name")
                     for x in (recs[0].get("outfit") or [])]
            print(f"  OK 推荐 {len(recs)} 套，第一套: {names}")
            print(f"     结论 {recs[0].get('verdict')} / {recs[0].get('label')}")
            if recs[0].get("pitfalls"):
                print(f"     提醒 {recs[0]['pitfalls'][0][:70]}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + ("验证通过" if ok and not problems else "有问题，见上面输出"))
    return 0 if (ok and not problems) else 1


if __name__ == "__main__":
    import json
    sys.exit(main())
