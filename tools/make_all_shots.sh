#!/bin/sh
# 一键重生成所有展示图。
#
# 为什么要这个脚本：截图流程有五步（起服务 → 截图 → 裁主图 → 生成卡片 →
# 生成），每次手动做一遍很容易漏步骤、或者用错旧图。
#
# 用法：
#   sh tools/make_all_shots.sh
#
# 依赖：Edge（Windows 自带即可）、Pillow
set -e

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE_DIR"

PORT=8959
TMP=".shotgen"
EDGE="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"

echo "=== 1. 准备样例环境 ==="
rm -rf "$TMP"
mkdir -p "$TMP/data" "$TMP/photos"
cp samples/wardrobe.json "$TMP/wardrobe.json"
cp data/cities.json data/climate.json "$TMP/data/"
cp samples/photos/*.jpg "$TMP/photos/" 2>/dev/null || true

echo "=== 2. 起服务 ==="
DRESSMATE_DATA_DIR="$BASE_DIR/$TMP/data" \
DRESSMATE_PHOTO_DIR="$BASE_DIR/$TMP/photos" \
DRESSMATE_WARDROBE_PATH="$BASE_DIR/$TMP/wardrobe.json" \
python server.py "$PORT" > "$TMP/server.log" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
sleep 4

if ! curl -sf -m 5 "http://127.0.0.1:$PORT/api/health" > /dev/null; then
    echo "服务没起来，看 $TMP/server.log"
    exit 1
fi
echo "  OK 服务已就绪 (127.0.0.1:$PORT)"

echo "=== 3. 截图（2 倍分辨率）==="
"$EDGE" --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
    --window-size=760,1180 --force-device-scale-factor=2 \
    --screenshot="$BASE_DIR/$TMP/hires.png" --virtual-time-budget=12000 \
    "http://127.0.0.1:$PORT/" > /dev/null 2>&1
[ -f "$TMP/hires.png" ] || { echo "  截图失败"; exit 1; }
echo "  OK $TMP/hires.png"

echo "=== 4. 生成 README 主图 + 分享卡片 ==="
python tools/make_shot.py "$TMP/hires.png" docs

echo "=== 5. 校验 ==="
python tools/check_readme.py

rm -rf "$TMP"
echo
echo "全部完成："
ls -la docs/*.png docs/*.jpg 2>/dev/null
