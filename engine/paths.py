# -*- coding: utf-8 -*-
"""运行时路径：默认全部落在仓库内，容器里用环境变量把可变部分挪到卷上。

为什么要有这层：代码目录在容器里是只读的、随镜像发布的那一份，
而衣橱、照片、日程这些是每个用户自己的东西，必须活得比容器久。
所以把「会变的东西」和「代码」分开，容器里把前者挂成卷。

三个环境变量：
  DRESSMATE_DATA_DIR       可变状态：profile / schedule / wear_log / weather_cache / 日志
  DRESSMATE_PHOTO_DIR      衣服照片
  DRESSMATE_WARDROBE_PATH  衣橱条目 json

不设这三个变量时，一切与直接跑 server.py 完全一致。

cities.json 是只读资产（323 个地级市），默认留在仓库里；
容器启动时首启会把它拷进 DATA_DIR，之后就以 DATA_DIR 里那份为准。
"""
import os

# 仓库根目录：engine/ 的上一级
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_path(name, default):
    """读环境变量里的路径；没设就用默认值。两边都转成绝对路径。"""
    v = os.environ.get(name)
    if not v:
        return default
    return os.path.abspath(os.path.expanduser(v))


DATA_DIR = _env_path("DRESSMATE_DATA_DIR", os.path.join(ROOT, "data"))
PHOTO_DIR = _env_path("DRESSMATE_PHOTO_DIR", os.path.join(ROOT, "wardrobe", "photos"))
WARDROBE_PATH = _env_path(
    "DRESSMATE_WARDROBE_PATH", os.path.join(ROOT, "wardrobe", "wardrobe.json")
)

# DATA_DIR 下的具体文件
PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")
WEAR_LOG_PATH = os.path.join(DATA_DIR, "wear_log.json")
WEATHER_CACHE_PATH = os.path.join(DATA_DIR, "weather_cache.json")
LOG_PATH = os.path.join(DATA_DIR, "server.log")

# 仓库内的只读资产
REPO_CITIES_PATH = os.path.join(ROOT, "data", "cities.json")


def cities_path():
    """城市表位置。

    优先级：显式环境变量 > DATA_DIR 里已存在的那份 > 仓库自带那份。
    这样容器里首启拷贝之后，读的是 DATA_DIR，行为与本地一致。
    """
    v = os.environ.get("DRESSMATE_CITIES_PATH")
    if v:
        return os.path.abspath(os.path.expanduser(v))
    local = os.path.join(DATA_DIR, "cities.json")
    if os.path.exists(local):
        return local
    return REPO_CITIES_PATH


def ensure_dirs():
    """建好所有需要写入的目录。容器里挂卷后目录可能不存在。"""
    for d in (DATA_DIR, PHOTO_DIR, os.path.dirname(WARDROBE_PATH)):
        if d:
            os.makedirs(d, exist_ok=True)
