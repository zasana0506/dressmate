# -*- coding: utf-8 -*-
"""每日推送：早上把今天的穿搭方案推到邮箱/企业微信。

配合 WorkBuddy 定时任务，每天 07:00 调用本脚本即可。
也支持手动运行：python tools/daily_push.py --city beijing
"""
import argparse
import datetime
import json
import os
import smtplib
import ssl
import sys
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from engine import context as CTX   # noqa: E402
from engine import recommend as REC  # noqa: E402
from engine import weather as WX     # noqa: E402

CITIES = {
    "beijing": (39.9042, 116.4074, "北京"), "shanghai": (31.2304, 121.4737, "上海"),
    "guangzhou": (23.1291, 113.2644, "广州"), "shenzhen": (22.5431, 114.0579, "深圳"),
    "hangzhou": (30.2741, 120.1551, "杭州"), "chengdu": (30.5728, 104.0668, "成都"),
    "wuhan": (30.5928, 114.3055, "武汉"), "nanjing": (32.0603, 118.7969, "南京"),
    "xian": (34.3416, 108.9398, "西安"), "harbin": (45.8038, 126.5350, "哈尔滨"),
}


def build_report(city, top=2):
    lat, lon, cname = CITIES.get(city, CITIES["beijing"])
    w = WX.fetch(lat, lon)
    with open(os.path.join(BASE_DIR, "wardrobe", "wardrobe.json"), encoding="utf-8") as f:
        wardrobe = json.load(f)["items"]
    sp = os.path.join(BASE_DIR, "data", "schedule.json")
    events = []
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            events = json.load(f).get("events", [])

    ctx = CTX.build_context(events, w)
    results, _, extra = REC.recommend(wardrobe, ctx, w, top_n=top)

    lines = []
    lines.append(f"{cname}今日穿搭建议")
    lines.append("=" * 40)
    lines.append(f"天气：{w['daily']['desc']}  {w['daily']['tmin']:.0f}~{w['daily']['tmax']:.0f}℃"
                 f"  体感 {w['feel_min']:.0f}~{w['feel_max']:.0f}℃")
    lines.append(f"降水 {w['daily']['pop_max']}%   风 {w['daily']['wind_max']:.0f}km/h"
                 f"   紫外 {w['daily']['uv_max']:.0f}")
    if events:
        lines.append("日程：" + " | ".join(f"{e.get('start','')} {e['title']}" for e in events))
    lines.append("")
    for r in results:
        lines.append(f"【{r['label']}】综合分 {r['score']:.3f}")
        for o in r["outfit"]:
            lines.append(f"  {o['slot_name']}：{o['item']['name']}")
            lines.append(f"    {o['reason']}")
        lines.append("")
    if extra.get("sport_outfit"):
        lines.append("【运动装备】" + " / ".join(
            o["item"]["name"] for o in extra["sport_outfit"]))
        lines.append("")

    from engine import timeline as TL
    plan = TL.plan_day(wardrobe, events, w)
    if plan["segments"]:
        lines.append("")
        lines.append("分时段计划")
        lines.append("-" * 40)
        for idx, s in enumerate(plan["segments"]):
            if s["change_needed"]:
                flag = "需换装"
            elif idx == 0:
                flag = "出门穿这套"
            else:
                flag = "沿用上一套"
            lines.append(f"{s['label']}  {s['occasion']}  体感{s['weather']['feel_mean']:.0f}℃  [{flag}]")
            lines.append("  穿：" + " + ".join(o["item"]["name"] for o in s["recommendation"]["outfit"]))
            if s["change_needed"] and s["changes"]:
                lines.append("  变动：" + "、".join(
                    f"{c['slot_name']}{c['action']}{c['item'] or ''}" for c in s["changes"]))
            if s["change_reasons"]:
                lines.append("  " + "；".join(s["change_reasons"]))
            lines.append("")
        for a in plan["day_advice"]:
            lines.append("全天：" + a)

    if extra.get("degraded") and extra["degraded"].get("note"):
        lines.append("注意：" + extra["degraded"]["note"])
    if ctx["advice"]:
        lines.append("提示：" + "；".join(ctx["advice"]))
    return "\n".join(lines)


def send_email(subject, body, to_addr, smtp_host, smtp_port, user, password, use_ssl=True):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("穿搭助手", "utf-8")), user))
    msg["To"] = to_addr
    msg["Date"] = formatdate()

    ctx = ssl.create_default_context()
    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx, timeout=20) as s:
            s.login(user, password)
            s.sendmail(user, [to_addr], msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as s:
            s.starttls(context=ctx)
            s.login(user, password)
            s.sendmail(user, [to_addr], msg.as_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default=os.environ.get("DRESSMATE_CITY", "beijing"))
    ap.add_argument("--print-only", action="store_true", help="只打印不发邮件")
    ap.add_argument("--save", action="store_true",
                    help="保存 Markdown 日报到 reports/YYYY-MM-DD.md（无需邮箱配置）")
    ap.add_argument("--to", default=os.environ.get("DRESSMATE_MAIL_TO", ""))
    ap.add_argument("--smtp-host", default=os.environ.get("DRESSMATE_SMTP_HOST", ""))
    ap.add_argument("--smtp-port", type=int, default=int(os.environ.get("DRESSMATE_SMTP_PORT", "465")))
    ap.add_argument("--user", default=os.environ.get("DRESSMATE_MAIL_USER", ""))
    ap.add_argument("--password", default=os.environ.get("DRESSMATE_MAIL_PASS", ""))
    args = ap.parse_args()

    report = build_report(args.city)
    print(report)

    if args.save:
        rdir = os.path.join(BASE_DIR, "reports")
        os.makedirs(rdir, exist_ok=True)
        day = datetime.date.today().isoformat()
        path = os.path.join(rdir, f"{day}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 今日穿搭 · {day}\n\n```\n{report}\n```\n")
        print(f"\n[已保存] {path}")

    if args.print_only:
        return
    if not all([args.to, args.smtp_host, args.user, args.password]):
        print("\n[未发送] 缺少邮件配置。可用 --print-only 只打印，"
              "或设置 DRESSMATE_MAIL_TO / SMTP_HOST / MAIL_USER / MAIL_PASS 环境变量。")
        return
    try:
        send_email("今日穿搭建议", report, args.to, args.smtp_host,
                   args.smtp_port, args.user, args.password)
        print(f"\n[已发送] → {args.to}")
    except Exception as exc:
        print(f"\n[发送失败] {exc}")


if __name__ == "__main__":
    main()
