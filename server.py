# -*- coding: utf-8 -*-
"""本地 Web 服务：给 App 提供衣橱管理 + 今日推荐 API。

启动:  python server.py  →  http://127.0.0.1:8848
"""
import base64
import datetime
import json
import os
import re
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import config as C        # noqa: E402
from engine import city as CITY       # noqa: E402
from engine import paths as PATHS     # noqa: E402
from engine import recommend as REC   # noqa: E402
from engine import weather as WX      # noqa: E402
from tools import import_photos as IP  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
PHOTO_DIR = PATHS.PHOTO_DIR
WARDROBE_PATH = PATHS.WARDROBE_PATH
SCHEDULE_PATH = PATHS.SCHEDULE_PATH
_lock = threading.Lock()
_cache = {}


def load_wardrobe():
    with open(WARDROBE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_wardrobe(data):
    with open(WARDROBE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_schedule():
    if not os.path.exists(SCHEDULE_PATH):
        return []
    with open(SCHEDULE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("events", [])


def save_schedule(events):
    os.makedirs(os.path.dirname(SCHEDULE_PATH), exist_ok=True)
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump({"date": datetime.date.today().isoformat(), "events": events},
                  f, ensure_ascii=False, indent=2)


def get_weather(city):
    """按城市取天气。city 可以是中文名（东莞）、旧 slug（beijing）或带「市」。"""
    info = CITY.resolve(city)
    if not info:
        info = CITY.resolve("北京")          # 兜底，不让整个页面挂掉
    key = info["key"] if info else str(city)
    now = time_now()
    if key in _cache and now - _cache[key][0] < 900:
        return _cache[key][1]
    w = WX.fetch(info["lat"], info["lon"])
    _cache[key] = (now, w)
    return w


def city_of(city):
    """这次请求用的是哪座城——中文名、省份、坐标都给出去，前端好显示。"""
    info = CITY.resolve(city) or CITY.resolve("北京")
    return info or {"key": "北京", "name": "北京", "province": "北京",
                    "lat": 39.9042, "lon": 116.4074}


def time_now():
    import time
    return time.time()


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

# 文昌提示的措辞分两种：日程里真有这类安排时，说「今天就有」；
# 没有时只说「这类事今天好办」。两者的穿衣建议力度不一样。
EXAM_KEYWORDS = ("考试", "面试", "答辩", "笔试", "汇报", "签约", "评审",
                 "述职", "演讲", "路演", "考研", "考公", "雅思", "托福", "开题")


def safe_filename(name):
    """只保留文件名主干，去掉路径与非法字符，扩展名白名单。

    注意：不能直接用 os.path.basename —— Windows 的 ntpath 会把 "黑:"
    当成盘符，导致含冒号的文件名开头被整段吃掉。
    """
    name = str(name).replace("\\", "/").split("/")[-1]
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "", name).strip()
    # ".jpg" 这类只有扩展名的名字，splitext 会把整串当成 stem
    if name.startswith(".") and name.count(".") == 1:
        stem, ext = "", name.lower()
    else:
        stem, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in IMAGE_EXTS:
        ext = ".jpg"
    stem = stem.strip(". ") or "未命名单品"
    return stem[:80] + ext


def unique_filename(name):
    """同名文件自动加序号，不覆盖已有照片。"""
    if not os.path.exists(os.path.join(PHOTO_DIR, name)):
        return name
    stem, ext = os.path.splitext(name)
    for i in range(2, 1000):
        cand = f"{stem}_{i}{ext}"
        if not os.path.exists(os.path.join(PHOTO_DIR, cand)):
            return cand
    return f"{stem}_{int(time_now())}{ext}"


def find_photo_owner(name, items):
    """同名照片已属于某个衣橱条目 → 返回该条目（照片恢复场景，不新增条目）。"""
    for it in items:
        if os.path.basename(it.get("photo", "")) == name:
            return it
    return None


def infer_one(filename):
    item, conf, warns = IP.infer(filename)
    return {"filename": filename, "url": "/photos/" + urllib.parse.quote(filename),
            "item": item, "confidence": conf, "warnings": warns}


def unimported_photos():
    """照片目录里还没进衣橱的图片（用户直接往文件夹丢照片也能在网页里导入）。"""
    data = load_wardrobe()
    known = {os.path.basename(it.get("photo", "")) for it in data["items"]}
    if not os.path.isdir(PHOTO_DIR):
        return []
    names = sorted(f for f in os.listdir(PHOTO_DIR)
                   if os.path.splitext(f)[1].lower() in IMAGE_EXTS)
    return [infer_one(p) for p in names if p not in known]


LOG_PATH = PATHS.LOG_PATH


def _log(line):
    """请求与异常都留痕：上传失败时能在这里查到真实原因。"""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 2 * 1024 * 1024:
            os.replace(LOG_PATH, LOG_PATH + ".1")
        ts = datetime.datetime.now().strftime("%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {line}\n")
    except Exception:
        pass


VISION_PROMPT = """你是服装属性标注器。看图识别图中的单件服装，只输出一个 JSON 对象，不要任何多余文字。
字段与取值：
slot: base(贴身内层:内衣/T恤/衬衫/打底) | mid(中层:毛衣/卫衣/开衫/马甲) | outer(外层:夹克/大衣/羽绒服/风衣/西装) | bottom(下装:裤/裙) | shoes(鞋) | accessory(配饰:帽/围巾/手套/伞/皮带/眼镜)
category: 细分品类英文蛇形命名，如 shirt / tshirt / down_jacket / sweater / hoodie / jeans / dress_pants / running_shoes / boots
name: 8个字以内的中文名，含颜色，如 藏青长袖衬衫
color: 主色中文，如 藏青/白/黑/米白/灰/卡其/棕
material: 材质中文；看不出就写 看不出
clo: 保暖值 clo，参考值：凉鞋0.0 / 短袖T0.15 / 衬衫0.20 / 薄针织0.24 / 保暖内衣0.26 / 卫衣0.38 / 风衣0.40 / 毛衣0.42 / 抓绒0.40 / 厚大衣0.65 / 羽绒服0.92 / 靴0.28。按视觉厚度在参考值附近估计，保留两位小数
formality: 0居家 1休闲 2常规 3商务 4正装，整数
waterproof / windproof / sun_protective / sport: 布尔值
season: 数组，取值 spring / summer / autumn / winter
confidence: 高 / 中 / 低（图片模糊、多件衣服混在一起、看不出材质时给低）
notes: 一句话依据，如 "长袖+衬衫领+硬挺面料"
注意：即使把握不大也要给出具体数值，不要留空；clo 必须是 0~2 之间的两位小数。"""


def cloud_cfg():
    """读视觉模型的 endpoint + publishableKey。

    两个来源，后者覆盖前者：
      web/cloud-config.js        仓库里的模板，默认是空的
      web/cloud-config.local.js  本地私有配置，不进仓库（有密钥的才放这）

    环境变量优先级更高，见 openai_cfg()。
    """
    for fn in ("cloud-config.js", "cloud-config.local.js"):
        try:
            txt = open(os.path.join(WEB_DIR, fn), encoding="utf-8").read()
        except Exception:
            continue
        ep = re.search(r'endpoint\s*:\s*"([^"]+)"', txt)
        key = re.search(r'publishableKey\s*:\s*"([^"]+)"', txt)
        if ep and key and ep.group(1) and key.group(1):
            return ep.group(1).rstrip("/"), key.group(1)
    return None, None


def openai_cfg():
    """通用 OpenAI 兼容端点。

    自托管的人不一定要用官方 OpenAI：Ollama、vLLM、OneAPI、各种中转
    都是同一套 /v1/chat/completions 协议。所以只认一个 base_url +
    一个 api_key，任何兼容的实现都能接上。
    """
    base = (os.environ.get("DRESSMATE_AI_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("DRESSMATE_AI_API_KEY")
           or os.environ.get("OPENAI_API_KEY") or "").strip()
    if base:
        if not base.endswith("/v1") and "/v1" not in base:
            base += "/v1"
        return base, key
    return None, None


def ai_available():
    """有没有可用的视觉模型后端。前端据此决定要不要显示 AI 开关。"""
    return bool(openai_cfg()[0] or cloud_cfg()[0])


def _vision_messages(data_url):
    return [
        {"role": "system", "content": VISION_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "识别图中的服装单品，只输出 JSON。"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]},
    ]


def openai_vision(data_url, model=None):
    """走 OpenAI 兼容协议的非流式调用。"""
    base, key = openai_cfg()
    model = model or os.environ.get("DRESSMATE_AI_MODEL") or "gpt-4o-mini"
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    payload = {"model": model, "stream": False, "messages": _vision_messages(data_url)}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        j = json.loads(resp.read().decode("utf-8"))
    return j["choices"][0]["message"].get("content") or ""


def cloud_vision(data_url, model="hy4free"):
    """服务端代理云端视觉模型。

    浏览器直连会被 Origin 白名单拦住（本地 127.0.0.1 不在白名单），
    服务端请求不带 Origin，因此走这条路本地/线上都通。
    """
    ep, key = cloud_cfg()
    if not ep:
        raise RuntimeError("缺少 cloud-config.js 配置")
    payload = {
        "model": model or "hy4free",
        "stream": True,
        "messages": _vision_messages(data_url),
    }
    req = urllib.request.Request(
        ep + "/.cloud/llm/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-wb-webapp-access-key": key,
            "content-type": "application/json",
            "accept": "text/event-stream",
        },
    )
    out = []
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                j = json.loads(chunk)
                c = j["choices"][0]["delta"].get("content")
                if c:
                    out.append(c)
            except Exception:
                continue
    return "".join(out)


def vision(data_url, model=None):
    """AI 看图识别。

    优先级：显式指定 OpenAI 兼容端点 > WorkBuddy 云 > 报错。
    自托管的人通常配前者，官方演示用的是后者。
    """
    if openai_cfg()[0]:
        return openai_vision(data_url, model)
    if cloud_cfg()[0]:
        return cloud_vision(data_url, model or "hy4free")
    raise RuntimeError(
        "未配置视觉模型。设置环境变量 DRESSMATE_AI_BASE_URL 和 "
        "DRESSMATE_AI_API_KEY（OpenAI 兼容端点，如 Ollama/vLLM/中转服务）"
        "即可启用；不配也能用，手工录入衣橱即可。"
    )


def _read_body(handler):
    te = (handler.headers.get("Transfer-Encoding") or "").lower()
    if "chunked" in te:
        buf = []
        while True:
            line = handler.rfile.readline().strip()
            if not line:
                break
            try:
                size = int(line.split(b";")[0], 16)
            except ValueError:
                break
            if size == 0:
                handler.rfile.readline()
                break
            buf.append(handler.rfile.read(size))
            handler.rfile.readline()
        return b"".join(buf)
    length = int(handler.headers.get("Content-Length", 0) or 0)
    return handler.rfile.read(length) if length else b""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"     # 支持 keep-alive，避免多图连传时连接被反复掐断

    def log_message(self, fmt, *args):
        _log("%s %s" % (self.command, fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)

        if p.path == "/api/health":
            return self._json({"ok": True, "app": "dressmate",
                               "time": datetime.datetime.now().isoformat(timespec="seconds"),
                               "photos": len(os.listdir(PHOTO_DIR)) if os.path.isdir(PHOTO_DIR) else 0,
                               "ai_available": ai_available()})

        if p.path == "/api/profile":
            from engine import luck as LUCK
            return self._json({
                "ok": True,
                "profile": LUCK.load_profile(),
                "times": [{"value": v, "label": t} for v, t in LUCK.TIME_OPTIONS],
                "has_node": shutil.which("node") is not None,
            })

        if p.path == "/api/luck":
            from engine import luck as LUCK
            day = (q.get("date") or [datetime.date.today().isoformat()])[0]
            return self._json(LUCK.daily_luck(LUCK.load_profile(), day))

        if p.path == "/api/wardrobe":
            data = load_wardrobe()
            # 标记照片文件缺失的条目：记录还在但图片丢了，重传同名文件即可恢复。
            # 示例数据的占位图（photo 名与 id 同名，如 w001.jpg）不算缺失。
            for it in data["items"]:
                fn = os.path.basename(it.get("photo", ""))
                stem = os.path.splitext(fn)[0]
                placeholder = bool(fn) and stem == it.get("id")
                it["photo_missing"] = (bool(fn) and not placeholder
                                       and not os.path.exists(os.path.join(PHOTO_DIR, fn)))
            return self._json(data)

        if p.path == "/api/photos/unimported":
            try:
                pending = unimported_photos()
                return self._json({"ok": True, "pending": pending, "count": len(pending)})
            except Exception as exc:
                return self._json({"error": f"{exc}"}, 500)

        if p.path == "/api/recommend":
            city = (q.get("city") or ["北京"])[0]
            # 城市解析不出来就明说，不能悄悄换成北京——
            # 用户会以为看到的是自己那座城的天气，穿错一整天
            if not CITY.resolve(city):
                return self._json(
                    {"error": f"找不到「{city}」这个城市。换个写法试试，"
                              f"比如「东莞」「东莞市」或「Dongguan」。"}, 400)
            try:
                with _lock:
                    wardrobe = load_wardrobe()["items"]
                    events = load_schedule()
                    w = get_weather(city)
                    from engine import context as CTX
                    ctx = CTX.build_context(events, w)
                    # 幸运色是可选的趣味层：只在用户开启时才参与打分
                    luck_data = None
                    if (q.get("lucky") or ["0"])[0] in ("1", "true", "on"):
                        from engine import luck as LUCK
                        lk = LUCK.daily_luck(LUCK.load_profile())
                        if lk.get("ok"):
                            luck_data = lk
                            ctx["luck"] = {
                                "color_family": lk["color_family"],
                                "avoid_families": [
                                    C.COLOR_FAMILY.get(C.normalize_color(c), "")
                                    for c in lk.get("avoid_colors") or []],
                            }
                            # 疾厄宫给的保暖余量交给引擎，只加不减（加严规则在 recommend 里）
                            hp = lk.get("health") or {}
                            ctx["warmth_bonus"] = hp.get("warmth_bonus") or 0.0
                            # 桃花只作场景标签与文案，不改正式度——正式度由日程决定
                            so = lk.get("social") or {}
                            if so.get("flag") and so.get("note"):
                                ctx["social"] = so
                                ctx.setdefault("advice", []).append(so["note"])
                            # 迁移宫的日常措辞（"出门多留时间"）与出差不同，这里用日常版
                            tv = lk.get("travel") or {}
                            if tv.get("flag") and tv.get("note"):
                                ctx["travel"] = tv
                                ctx.setdefault("advice", []).append(tv["note"])
                            # 文昌：今天有考试/面试类安排时换一套措辞，力度更实
                            st = lk.get("study") or {}
                            if st.get("flag") or st.get("careful"):
                                if st.get("flag"):
                                    text = " ".join(f"{e.get('title', '')} {e.get('note', '')}"
                                                    for e in events)
                                    if any(k in text for k in EXAM_KEYWORDS):
                                        st = {**st, "exam_today": True,
                                              "note": st.get("exam_note") or st.get("note")}
                                ctx["study"] = st
                                if st.get("note"):
                                    ctx.setdefault("advice", []).append(st["note"])
                    results, pools, extra = REC.recommend(wardrobe, ctx, w)
                    from engine import timeline as TL
                    from engine import styling as STY
                    from engine import extras as EXTRAS
                    timeline = TL.plan_day(wardrobe, events, w, day_ctx=ctx)
                ci = city_of(city)
                return self._json({
                    "date": datetime.date.today().isoformat(),
                    "city": ci["name"],
                    # 选的是哪一级：省 + 坐标，用户能自己核对「选对城了吗」
                    "city_info": {"key": ci["key"], "name": ci["name"],
                                  "province": ci.get("province") or "",
                                  "lat": ci["lat"], "lon": ci["lon"]},
                    "weather": w,
                    "context": ctx,
                    "band": {"key": REC.band_of(w["feel_mean"]),
                             "label": C.TEMPERATURE_BANDS[REC.band_of(w["feel_mean"])]["label"]},
                    "recommendations": results,
                    # 这轮自检跑的是哪套得体规矩：有裙装走女装铁律，否则走男装礼仪
                    "style_lane": STY.lane(wardrobe),
                    # 配件库存：皮带/袜子/包/领带在衣橱里各有几件。
                    # 全 0 时页面要说清楚「这几条规矩暂时只能给建议」，
                    # 否则用户看到「还差一条皮带」会以为系统在瞎猜
                    "extras_inventory": {
                        "lane": EXTRAS.lane(wardrobe),
                        "have": {EXTRAS.ROLE_NAME[k]: len(v)
                                 for k, v in EXTRAS.index(wardrobe).items()},
                    },
                    # 衣橱缺哪些配件——三套合并后的一份，由页面顶部统一显示。
                    # 分开的 required / optional：只有前者值得催，后者写出来只是提示
                    "extras_gaps": extra.get("extras_gaps") or [],
                    "sport_outfit": extra.get("sport_outfit", []),
                    "degraded": extra.get("degraded"),
                    # 衣橱不齐时的缺口清单：哪一层、该补多少 clo、为什么现在这几件不行
                    "gaps": extra.get("gaps") or [],
                    "partial": bool(extra.get("partial")),
                    "timeline": timeline,
                    "luck": luck_data,
                    "warmth_relaxed": bool(extra.get("warmth_relaxed")),
                    "schedule": events,
                    "pool_stats": {k: len(v) for k, v in pools.items()},
                })
            except Exception as exc:
                import traceback
                traceback.print_exc()
                return self._json({"error": f"{exc}"}, 500)

        if p.path == "/api/cities":
            # 全量城市表（300+ 条，约 30KB）：前端一次拿完，本地过滤，
            # 比每敲一个字都请求一次服务器快，断网也不会卡
            qs = (q.get("q") or [""])[0]
            items = CITY.search(qs, limit=20) if qs else CITY.all_cities()
            return self._json({"count": len(items), "cities": items})

        if p.path == "/api/geocode":
            # 表里没有的生僻地名才走这里：在线查一次，查到就写回本地表
            name = (q.get("name") or [""])[0]
            info = CITY.resolve(name)
            if not info:
                return self._json({"error": f"找不到「{name}」这个地名，换个写法试试"}, 404)
            return self._json(info)

        if p.path == "/api/trip":
            from engine import trip as TRIP
            city = (q.get("city") or ["上海"])[0]
            if not CITY.resolve(city):
                return self._json({"error": f"找不到目的地「{city}」，换个写法试试"}, 400)
            today = datetime.date.today().isoformat()
            start = (q.get("start") or [today])[0]
            end = (q.get("end") or [start])[0]
            purpose = (q.get("purpose") or ["出差"])[0]
            laundry = (q.get("laundry") or ["1"])[0] not in ("0", "false", "no")
            ci = city_of(city)
            lat, lon, cname = ci["lat"], ci["lon"], ci["name"]
            # 先取完衣橱再放锁：拉多日预报要走网络，不能把整个服务堵在这里
            with _lock:
                wardrobe = load_wardrobe()["items"]
            try:
                # 迁移宫的出行提示按出发日取：一次排盘即可，不必逐日排（逐日要起 N 次 Node）
                luck_travel = None
                if (q.get("lucky") or ["0"])[0] in ("1", "true", "on"):
                    try:
                        from engine import luck as LUCK
                        lk = LUCK.daily_luck(LUCK.load_profile(), start)
                        if lk.get("ok"):
                            luck_travel = lk.get("travel")
                    except Exception as exc:
                        _log(f"迁移宫取数失败（不影响打包）: {exc}")
                res = TRIP.plan_for_city(wardrobe, lat, lon, start, end, purpose, laundry,
                                         luck_travel=luck_travel)
                res["city"] = cname
                res["city_key"] = ci["key"]
                res["city_info"] = {"province": ci.get("province") or "",
                                    "lat": ci["lat"], "lon": ci["lon"]}
                return self._json(res)
            except Exception as exc:
                _log(f"出差打包失败: {exc}")
                return self._json({"error": f"取不到{cname}的天气预报：{exc}"}, 502)

        if p.path.startswith("/photos/"):
            raw = p.path[len("/photos/"):]
            name = os.path.basename(urllib.parse.unquote(raw))
            fp = os.path.join(PHOTO_DIR, name)
            if os.path.exists(fp):
                ext = os.path.splitext(fp)[1].lower()
                ct = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                      ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "application/octet-stream")
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), ct)
            return self._send(404, "not found", "text/plain")

        # 静态文件
        rel = "index.html" if p.path == "/" else urllib.parse.unquote(p.path.lstrip("/"))
        fp = os.path.join(WEB_DIR, rel)
        if os.path.exists(fp) and os.path.isfile(fp):
            ext = os.path.splitext(fp)[1].lower()
            ct = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8"}.get(
                      ext, "application/octet-stream")
            with open(fp, "rb") as f:
                return self._send(200, f.read(), ct)
        return self._send(404, "not found", "text/plain")

    def do_POST(self):
        p = urlparse(self.path)
        try:
            raw = _read_body(self)
        except Exception as exc:
            _log(f"读取请求体失败 {p.path}: {exc}")
            return self._json({"error": f"读取请求体失败: {exc}"}, 400)
        if not raw:
            raw = b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            _log(f"JSON 解析失败 {p.path}: {exc}; 前80字节={raw[:80]!r}")
            return self._json({"error": "bad json"}, 400)

        if p.path == "/api/profile":
            from engine import luck as LUCK
            solar = str(body.get("solar_date") or "").strip()
            if not re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", solar):
                return self._json({"ok": False, "error": "出生日期格式应为 YYYY-MM-DD"}, 400)
            try:
                ti = int(body.get("time_index", 6))
            except Exception:
                ti = 6
            ti = max(0, min(12, ti))
            prof = {
                "solar_date": solar,
                "time_index": ti,
                "gender": "女" if body.get("gender") == "女" else "男",
            }
            LUCK.save_profile(prof)
            return self._json({"ok": True, "profile": prof,
                               "luck": LUCK.daily_luck(prof, use_cache=False)})

        if p.path == "/api/ai-recognize":
            data_url = body.get("data") or ""
            if not str(data_url).startswith("data:image/"):
                return self._json({"ok": False, "error": "缺少图片数据"}, 400)
            try:
                raw = vision(data_url, body.get("model"))
                _log(f"AI识别成功 长度{len(raw)}")
                return self._json({"ok": True, "raw": raw})
            except Exception as exc:
                _log(f"AI识别失败: {exc}")
                return self._json({"ok": False, "error": f"{exc}"}, 502)

        if p.path == "/api/upload":
            """接收浏览器压缩后的 dataURL，落盘到 wardrobe/photos/ 并推断属性。"""
            files = body.get("files") or []
            if not files:
                return self._json({"error": "没有收到文件"}, 400)
            os.makedirs(PHOTO_DIR, exist_ok=True)
            existing_items = load_wardrobe()["items"]
            saved, errors = [], []
            for idx, f in enumerate(files[:50]):
                try:
                    name = safe_filename(f.get("name", ""))
                    dataurl = f.get("data", "")
                    if "," not in dataurl:
                        raise ValueError("图片数据格式不对")
                    blob = base64.b64decode(dataurl.split(",", 1)[1], validate=False)
                    if not blob:
                        raise ValueError("图片内容为空")
                    if len(blob) > 12 * 1024 * 1024:
                        raise ValueError("单张超过 12MB")
                    name = unique_filename(name)
                    with open(os.path.join(PHOTO_DIR, name), "wb") as fh:
                        fh.write(blob)
                    # srcIndex 让前端把原图数据对回具体文件（同名加序号后仍能对上）
                    entry = {**infer_one(name), "srcIndex": idx}
                    # 同名照片已存在衣橱条目 → 视为恢复，不需要新增
                    hit = find_photo_owner(name, existing_items)
                    if hit:
                        entry["restored"] = {"id": hit["id"], "name": hit["name"]}
                    saved.append(entry)
                except Exception as exc:
                    _log(f"上传单项失败 {f.get('name', '?')}: {exc}")
                    errors.append(f"{f.get('name', '?')}: {exc}")
            _log(f"上传完成 成功{len(saved)} 失败{len(errors)}")
            return self._json({"ok": True, "saved": saved, "errors": errors,
                               "count": len(saved)})

        if p.path == "/api/import":
            """把校对过的单品批量写入衣橱（按照片名去重、自动分配 id）。"""
            items = body.get("items") or []
            if not items:
                return self._json({"error": "没有待导入的单品"}, 400)
            clean = []
            for it in items:
                if not isinstance(it, dict) or not it.get("photo"):
                    continue
                try:
                    it["clo"] = float(it.get("clo") or 0.2)
                    it["formality"] = int(it.get("formality") or 2)
                except (TypeError, ValueError):
                    continue
                it.setdefault("status", "clean")
                it.setdefault("last_worn", None)
                it.setdefault("wear_count", 0)
                clean.append(it)
            with _lock:
                data = load_wardrobe()
                added = IP.merge(data, clean)
                save_wardrobe(data)
            return self._json({"ok": True, "added": added, "skipped": len(clean) - added})

        if p.path == "/api/item-delete":
            bid = body.get("id")
            with _lock:
                data = load_wardrobe()
                before = len(data["items"])
                data["items"] = [it for it in data["items"] if it["id"] != bid]
                save_wardrobe(data)
            return self._json({"ok": True, "removed": before - len(data["items"])})

        if p.path == "/api/clear-demo":
            """清掉照片文件不存在的示例条目，给真实衣橱腾位置。"""
            if not body.get("confirm"):
                return self._json({"error": "需要 confirm=true"}, 400)
            with _lock:
                data = load_wardrobe()
                before = len(data["items"])
                data["items"] = [it for it in data["items"]
                                 if os.path.exists(os.path.join(
                                     PHOTO_DIR, os.path.basename(it.get("photo", ""))))]
                save_wardrobe(data)
                # 顺带把天气缓存置空，让推荐结果立即按新衣橱重算
                _cache.clear()
            return self._json({"ok": True, "removed": before - len(data["items"])})

        if p.path == "/api/toggle":
            with _lock:
                data = load_wardrobe()
                order = ["clean", "dirty", "laundry", "dryclean", "stored"]
                for it in data["items"]:
                    if it["id"] == body.get("id"):
                        cur = it.get("status", "clean")
                        it["status"] = order[(order.index(cur) + 1) % len(order)] if cur in order else "dirty"
                        break
                save_wardrobe(data)
            return self._json({"ok": True})

        if p.path == "/api/schedule":
            with _lock:
                save_schedule(body if isinstance(body, list) else body.get("events", []))
            return self._json({"ok": True})

        if p.path == "/api/item":
            with _lock:
                data = load_wardrobe()
                items = data["items"]
                bid = body.get("id")
                for i, it in enumerate(items):
                    if it["id"] == bid:
                        body.pop("id", None)
                        items[i] = {**it, **body}
                        break
                else:
                    items.append(body)
                save_wardrobe(data)
            return self._json({"ok": True})

        if p.path == "/api/wear":
            """记录实际穿着 → 回写 last_worn / wear_count，驱动轮换分。"""
            ids = body.get("ids") or []
            if not ids:
                return self._json({"error": "缺少 ids"}, 400)
            today = body.get("date") or datetime.date.today().isoformat()
            updated = []
            with _lock:
                data = load_wardrobe()
                for it in data["items"]:
                    if it["id"] in ids:
                        it["last_worn"] = today
                        it["wear_count"] = it.get("wear_count", 0) + 1
                        if it.get("status") != "clean":
                            it["status"] = "clean"
                        updated.append(it["name"])
                save_wardrobe(data)
                log_path = PATHS.WEAR_LOG_PATH
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                log = []
                if os.path.exists(log_path):
                    with open(log_path, encoding="utf-8") as f:
                        log = json.load(f)
                log.append({"date": today, "items": ids})
                with open(log_path, "w", encoding="utf-8") as f:
                    json.dump(log, f, ensure_ascii=False, indent=2)
            return self._json({"ok": True, "updated": updated, "count": len(updated)})

        return self._json({"error": "not found"}, 404)


def main():
    # 本地运行：127.0.0.1:8848；云端发布：监听 $PORT 且绑 0.0.0.0
    env_port = os.environ.get("PORT")
    port = int(env_port or (sys.argv[1] if len(sys.argv) > 1 else 8848))
    host = "0.0.0.0" if env_port else "127.0.0.1"
    os.makedirs(PHOTO_DIR, exist_ok=True)
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"dressmate 已启动  →  http://{host}:{port}")
    if not env_port:
        print("手机访问：确保与电脑同一 WiFi，用本机局域网 IP + 端口")
    print("Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
