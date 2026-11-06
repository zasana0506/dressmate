# -*- coding: utf-8 -*-
"""校验 /api/recommend 的返回是不是真结果。

为什么要单独一个脚本：CI 里内联写 python -c 会被 YAML 的引号处理吃掉转义，
表现为「本地能过、CI 必挂」。逻辑放文件里最省心。

用法：
    python tools/check_rec.py /tmp/rec.json
    curl -s "http://127.0.0.1:8848/api/recommend?city=Beijing" | python tools/check_rec.py -
"""
import json
import sys


def main():
    if len(sys.argv) < 2:
        print("用法：python tools/check_rec.py <json文件路径|->")
        return 2

    src = sys.argv[1]
    if src == "-":
        raw = sys.stdin.read()
    else:
        with open(src, encoding="utf-8") as f:
            raw = f.read()

    try:
        d = json.loads(raw)
    except Exception as exc:
        print(f"失败：返回的不是合法 JSON（{exc}）")
        print(f"  开头：{raw[:200]}")
        return 1

    if "error" in d and not d.get("recommendations"):
        print(f"失败：接口返回了错误：{d['error']}")
        return 1

    recs = d.get("recommendations") or []
    if not recs:
        print("失败：没有产出推荐")
        return 1

    print(f"推荐接口 OK：{len(recs)} 套")

    # 每套都要有单品、有结论
    for i, o in enumerate(recs):
        items = o.get("outfit") or []
        if not items:
            print(f"失败：第 {i + 1} 套没有单品")
            return 1
        names = []
        for part in items:
            it = part.get("item") or {}
            if not it.get("name"):
                print(f"失败：第 {i + 1} 套有单品缺 name")
                return 1
            names.append(it["name"])
        if not o.get("verdict"):
            print(f"失败：第 {i + 1} 套没有 verdict")
            return 1
        print(f"  第 {i + 1} 套：{names}")
        print(f"     {o.get('verdict')} / {o.get('label')}")

    # 三套不能是同一套
    if len(recs) >= 2:
        def sig(o):
            return tuple((p.get("item") or {}).get("name")
                         for p in (o.get("outfit") or []))
        if sig(recs[0]) == sig(recs[1]):
            print("失败：前两套完全相同")
            return 1

    # 天气必须能解析出温度
    w = d.get("weather") or {}
    temp = (w.get("current") or {}).get("temp")
    if temp is None:
        print("失败：天气里没有温度")
        return 1
    print(f"  天气：{temp}℃（{w.get('current', {}).get('desc')}）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
