# -*- coding: utf-8 -*-
"""生成城市坐标表 data/cities.json。

为什么必须离线存一份
--------------------
Open-Meteo 的地理编码对中文**不可靠**：查「东莞」返回 20.30/109.99
（那是雷州半岛某个镇），真实东莞是 23.02/113.75；查「洛阳」返回福建一个
同名小镇。只有加「市」字、再校验 feature_code 是 PPLA* 才准。

但加了「市」也有查不到的（临沂、襄阳返回空）。所以：
1. 这份脚本一次性把地级市全量拉下来，落成离线表——离线表是主数据；
2. 运行时只对表里没有的生僻地名回退到在线查询。

用法：python tools/build_cities.py [--write]
不加 --write 只打印统计，用于抽查。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(BASE_DIR, "data", "cities.json")

# 地级行政区（按省分组，便于人工核对）。末尾是常用的县级市——
# 「市」只到地级不够用，义乌、昆山这些地方问天气的人很多。
PROVINCES = {
    "河北": "石家庄 唐山 秦皇岛 邯郸 邢台 保定 张家口 承德 沧州 廊坊 衡水",
    "山西": "太原 大同 阳泉 长治 晋城 朔州 晋中 运城 忻州 临汾 吕梁",
    "内蒙古": "呼和浩特 包头 乌海 赤峰 通辽 鄂尔多斯 呼伦贝尔 巴彦淖尔 乌兰察布",
    "辽宁": "沈阳 大连 鞍山 抚顺 本溪 丹东 锦州 营口 阜新 辽阳 盘锦 铁岭 朝阳 葫芦岛",
    "吉林": "长春 吉林 四平 辽源 通化 白山 松原 白城",
    "黑龙江": "哈尔滨 齐齐哈尔 鸡西 鹤岗 双鸭山 大庆 伊春 佳木斯 七台河 牡丹江 黑河 绥化",
    "江苏": "南京 无锡 徐州 常州 苏州 南通 连云港 淮安 盐城 扬州 镇江 泰州 宿迁 昆山 常熟 江阴 张家港 宜兴 丹阳 太仓 如皋 启东",
    "浙江": "杭州 宁波 温州 嘉兴 湖州 绍兴 金华 衢州 舟山 台州 丽水 义乌 慈溪 余姚 诸暨 温岭 乐清 瑞安 海宁 桐乡",
    "安徽": "合肥 芜湖 蚌埠 淮南 马鞍山 淮北 铜陵 安庆 黄山 滁州 阜阳 宿州 六安 亳州 池州 宣城",
    "福建": "福州 厦门 莆田 三明 泉州 漳州 南平 龙岩 宁德 晋江",
    "江西": "南昌 景德镇 萍乡 九江 新余 鹰潭 赣州 吉安 宜春 抚州 上饶",
    "山东": "济南 青岛 淄博 枣庄 东营 烟台 潍坊 济宁 泰安 威海 日照 临沂 德州 聊城 滨州 菏泽 胶州 寿光 荣成 蓬莱 龙口",
    "河南": "郑州 开封 洛阳 平顶山 安阳 鹤壁 新乡 焦作 濮阳 许昌 漯河 三门峡 南阳 商丘 信阳 周口 驻马店",
    "湖北": "武汉 黄石 十堰 宜昌 襄阳 鄂州 荆门 孝感 荆州 黄冈 咸宁 随州",
    "湖南": "长沙 株洲 湘潭 衡阳 邵阳 岳阳 常德 张家界 益阳 郴州 永州 怀化 娄底",
    "广东": "广州 韶关 深圳 珠海 汕头 佛山 江门 湛江 茂名 肇庆 惠州 梅州 汕尾 河源 阳江 清远 东莞 中山 潮州 揭阳 云浮",
    "广西": "南宁 柳州 桂林 梧州 北海 防城港 钦州 贵港 玉林 百色 贺州 河池 来宾 崇左",
    "海南": "海口 三亚 儋州 琼海 文昌",
    "四川": "成都 自贡 攀枝花 泸州 德阳 绵阳 广元 遂宁 内江 乐山 南充 眉山 宜宾 广安 达州 雅安 巴中 资阳",
    "贵州": "贵阳 六盘水 遵义 安顺 毕节 铜仁",
    "云南": "昆明 曲靖 玉溪 保山 昭通 丽江 普洱 临沧 大理 西双版纳",
    "西藏": "拉萨 日喀则 昌都 林芝 山南 那曲",
    "陕西": "西安 铜川 宝鸡 咸阳 渭南 延安 汉中 榆林 安康 商洛",
    "甘肃": "兰州 嘉峪关 金昌 白银 天水 武威 张掖 平凉 酒泉 庆阳 定西 陇南",
    "青海": "西宁 海东",
    "宁夏": "银川 石嘴山 吴忠 固原 中卫",
    "新疆": "乌鲁木齐 克拉玛依 吐鲁番 哈密 喀什 和田 阿克苏 伊宁",
    "直辖市": "北京 上海 天津 重庆",
}

# 只有这些 feature_code 是「城市本级」，PPL（普通居民点）不算——
# 东莞那次误命中就是个 PPL 级别的镇
CITY_FEATURES = ("PPLA", "PPLA2", "PPLA3", "PPLC", "PPLA4")

# 少数民族语地名：拼音猜不出 GeoNames 用的写法，单独列。
# 不列也不会错，只是那几座城会被记为「查不到」。
SPECIAL_ASCII = {
    "乌鲁木齐": "Urumqi", "呼和浩特": "Hohhot", "拉萨": "Lhasa",
    "喀什": "Kashgar", "和田": "Hotan", "阿克苏": "Aksu", "伊宁": "Yining",
    "吐鲁番": "Turpan", "哈密": "Hami", "日喀则": "Shigatse", "林芝": "Nyingchi",
    "昌都": "Qamdo", "那曲": "Nagqu", "山南": "Lhoka", "海西": "Haixi",
    "西双版纳": "Xishuangbanna", "大理": "Dali", "鄂尔多斯": "Ordos",
    # 日喀则：GeoNames 用 Xigaze，写 Shigatse 只会命中机场
    "日喀则": "Xigaze",
    # 吕梁要带变音符，写 Lvliang / Luliang 都查不到
    "吕梁": "Lüliang", "巴彦淖尔": "Bayan Nur",
    "呼伦贝尔": "Hulunbuir", "乌兰察布": "Ulanqab",
    # 西安：GeoNames 里带撇号，写成 Xian 会命中湘潭、咸阳、襄阳
    "西安": "Xi'an",
    # 以下都是「拼音拼不出来」的：GeoNames 用的是威妥玛式或带撇号的老写法。
    # 补这些不是洁癖——哈尔滨、齐齐哈尔这种城市查不到，用户会觉得整个功能是坏的。
    "哈尔滨": "Harbin", "齐齐哈尔": "Qiqihar", "长治": "Changzhi",
    "新乡": "Xinxiang", "许昌": "Xuchang", "漯河": "Luohe",
    "泰安": "Tai'an", "六安": "Lu'an", "马鞍山": "Ma'anshan", "吉安": "Ji'an",
    "江阴": "Jiangyin", "晋江": "Jinjiang", "荣成": "Rongcheng",
    "蓬莱": "Penglai", "百色": "Baise", "广安": "Guang'an", "资阳": "Ziyang",
    "普洱": "Pu'er", "延安": "Yan'an", "海东": "Haidong",
}

# 省份名归一：API 给「河北省」「内蒙古」「新疆维吾尔自治区」，名单里写「河北」
PROV_SUFFIX = ("维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "省", "市")


def norm_prov(s):
    s = str(s or "").strip()
    for suf in PROV_SUFFIX:
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def pinyin(name):
    from pypinyin import lazy_pinyin
    return "".join(lazy_pinyin(name)).title()


def geocode(q, timeout=15):
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": q, "count": 20, "language": "zh", "countryCode": "CN"})
    req = urllib.request.Request(url, headers={"User-Agent": "dressmate/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")).get("results") or []
    except Exception:
        return []


def find_city(bare, ascii_name=None, province=None):
    """中文查一次，不成再查拼音。

    注意：中文查到「有结果」不等于查对了。查「上海市」会返回
    「上海市场社区」（河南的一个村），这时不能因为 results 非空就收工，
    必须拿 pick() 校验；不过再换拼音重试。
    """
    for q, is_ascii in ((bare + "市", False), (ascii_name, True)):
        if not q:
            continue
        r = pick(geocode(q), bare, province, ascii_name, allow_district=is_ascii)
        if r:
            return r
        time.sleep(0.35)
    return None


def norm_name(s):
    """名字归一，用来比对。

    两件事：
    1. GeoNames 里的撇号是**全角右引号**（Tai’an / Ma’anshan），
       不是键盘上那个 ASCII 单引号。不统一的话，泰安、马鞍山这种带撇号的
       城市永远匹配不上——查到了结果，却因为一个引号形状不同被判为不匹配。
    2. 行政后缀要去掉：「哈密地区」「吐鲁番县」说的都是那座城。
    """
    s = str(s or "").strip()
    for suf in ("维吾尔自治区", "壮族自治区", "回族自治区", "自治州",
                "地区", "自治区", "盟", "市", "县"):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[:-len(suf)]
            break
    for apos in ("’", "‘", "`", "´", "＇"):
        s = s.replace(apos, "'")
    return s.strip().lower()


def pick(results, bare, province=None, ascii_name=None, allow_district=False):
    """从候选里挑真正的那座城。

    四个条件：名字对得上、在中国、省份对得上、行政级别够。
    只看第一个会踩坑——「东莞」第一个结果是雷州半岛的镇。

    名字有两种写法都要认：GeoNames 里大城市存的是英文（Baoji），
    小城市存的是中文（自贡市）。只比中文名会把宝鸡这类全漏掉。
    """
    want_prov = norm_prov(province) if province and province != "直辖市" else None
    want_names = {norm_name(bare), norm_name(ascii_name)}

    def ok(r):
        if norm_name(r.get("name")) not in want_names:
            return False
        if r.get("country_code") not in (None, "CN"):
            return False
        admin = norm_prov(r.get("admin1"))
        if want_prov and admin and admin != want_prov:
            return False
        return True

    # 第一轮只认行政中心：东莞同时有「镇」和「市」两个同名点，只有 PPLA 那个是对的
    for r in results:
        if r.get("feature_code") in CITY_FEATURES and ok(r):
            return r
    # 第二轮放宽到 PPL：衡阳、自贡在 GeoNames 里只标了 PPL，
    # 不留这一步会有几十个地级市永远查不到。省份已经校验，误命中概率很低
    for r in results:
        if r.get("feature_code") == "PPL" and ok(r):
            return r
    # 第三轮：查的是拼音，而 GeoNames 只存了市辖区名——新乡叫「南干道」、
    # 许昌叫「将官池」、桐乡叫「梧桐」，名字对不上，坐标却是市区。
    # 只在「该省只出现一个行政区级结果」时接受：多于一个说明有歧义，
    # 猜错就是把用户送到别的城市，宁可漏掉。
    if allow_district and want_prov:
        cands = [r for r in results
                 if (r.get("feature_code") or "") in ("PPLA2", "PPLA3", "PPLA4")
                 and norm_prov(r.get("admin1")) == want_prov
                 and r.get("country_code") in (None, "CN")]
        if len(cands) == 1:
            return cands[0]
    return None


def main():
    write = "--write" in sys.argv
    # 增量：已经有了就不再查。前面一次跑可能要五分钟，
    # 中断后重跑不该从头再来，也不该被限流打死。
    table = {}
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, encoding="utf-8") as f:
                table = json.load(f).get("cities") or {}
        except Exception:
            table = {}

    failed = []
    total = 0
    before = len(table)
    for prov, names in PROVINCES.items():
        for bare in names.split():
            total += 1
            if bare in table:
                continue
            ascii_name = SPECIAL_ASCII.get(bare) or pinyin(bare)
            try:
                r = find_city(bare, ascii_name, prov)
            except Exception as exc:
                failed.append((bare, prov, f"请求失败 {exc}"))
                continue
            if not r:
                failed.append((bare, prov, "无城市级结果"))
                continue
            table[bare] = {"lat": round(r["latitude"], 4),
                           "lon": round(r["longitude"], 4),
                           "province": norm_prov(r.get("admin1") or prov),
                           "name": r.get("name") or bare}
            time.sleep(0.5)
    print(f"候选 {total}，本轮新增 {len(table) - before}，表内共 {len(table)}，失败 {len(failed)}")
    if failed:
        print("失败清单：")
        for f in failed:
            print("  ", f)
    if write:
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump({"cities": table}, f, ensure_ascii=False, indent=1, sort_keys=True)
        print("已写入", OUT_PATH, "共", len(table), "条")


if __name__ == "__main__":
    main()
