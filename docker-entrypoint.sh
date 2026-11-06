#!/bin/sh
# 容器首启：把只读资产播种到可写卷，再起服务。
#
# 为什么需要这一步：镜像里的代码目录是只读的，而衣橱、照片、城市表这些
# 是用户自己的数据，必须住在卷里。首次启动时目录是空的，所以要拷进去。
# 之后重启不覆盖——用户的改动优先。
set -e

DATA_DIR="${DRESSMATE_DATA_DIR:-/data}"
PHOTO_DIR="${DRESSMATE_PHOTO_DIR:-/data/photos}"
WARDROBE_PATH="${DRESSMATE_WARDROBE_PATH:-/data/wardrobe.json}"
APP_DIR="${APP_DIR:-/app}"

mkdir -p "$DATA_DIR" "$PHOTO_DIR" "$(dirname "$WARDROBE_PATH")"

# 城市表：仓库自带的是只读资产，拷进卷里后以卷里那份为准
if [ ! -f "$DATA_DIR/cities.json" ] && [ -f "$APP_DIR/data/cities.json" ]; then
    cp "$APP_DIR/data/cities.json" "$DATA_DIR/cities.json"
    echo "[dressmate] 已播种城市表"
fi

# 样例衣橱：只在用户还没有任何衣橱时放进去，让他一打开就有东西看
if [ ! -f "$WARDROBE_PATH" ] && [ -f "$APP_DIR/samples/wardrobe.json" ]; then
    cp "$APP_DIR/samples/wardrobe.json" "$WARDROBE_PATH"
    echo "[dressmate] 已播种样例衣橱（31 件），可在网页里删掉换成自己的"
fi

exec python "$APP_DIR/server.py" "${PORT:-8848}"
