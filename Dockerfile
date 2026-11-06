# dressmate —— 规则驱动的每日穿搭助手
#
# 镜像刻意做得很薄：运行时只用 Python 标准库，不需要 pip install 任何东西。
# 这是这个项目能被别人轻松自托管的主要原因之一。

FROM python:3.12-slim

# 仓库地址。构建时传：docker build --build-arg SOURCE_URL=https://github.com/你的用户名/dressmate .
ARG SOURCE_URL="https://github.com/your-user/dressmate"

LABEL org.opencontainers.image.title="dressmate" \
      org.opencontainers.image.description="规则驱动的每日穿搭助手：拍照建衣橱，按天气与场合给建议" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="${SOURCE_URL}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_DIR=/app \
    DRESSMATE_DATA_DIR=/data \
    DRESSMATE_PHOTO_DIR=/data/photos \
    DRESSMATE_WARDROBE_PATH=/data/wardrobe.json \
    PORT=8848

WORKDIR /app

# 代码：引擎、服务、前端、样例数据
COPY engine/       /app/engine/
# 只拷运行时真正要的那一个：server.py 靠它做文件名属性推断
COPY tools/__init__.py /app/tools/__init__.py
COPY tools/import_photos.py /app/tools/import_photos.py
COPY web/          /app/web/
COPY samples/      /app/samples/
COPY data/cities.json /app/data/cities.json
# 气候参考表：断网时兜底天气要用，漏了会导致断网即崩
COPY data/climate.json /app/data/climate.json
COPY server.py     /app/server.py
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

# 非 root 运行。/data 在运行时挂卷，镜像里先建好并交给这个用户。
RUN chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /data/photos \
    && useradd --system --uid 10001 --create-home dressmate \
    && chown -R dressmate:dressmate /app /data

USER dressmate

VOLUME ["/data"]
EXPOSE 8848

# 健康检查：容器起来了不代表推荐能算，得真打一次接口
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8848/api/health',timeout=4).status==200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
