# dressmate —— 规则驱动的每日穿搭助手
#
# 镜像刻意做得很薄：运行时只用 Python 标准库，不需要 pip install 任何东西。
# 这是这个项目能被别人轻松自托管的主要原因之一。

FROM python:3.12-slim

LABEL org.opencontainers.image.title="dressmate" \
      org.opencontainers.image.description="规则驱动的每日穿搭助手：拍照建衣橱，按天气与场合给建议" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/YOUR_USER/dressmate"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_DIR=/app \
    DRESSMATE_DATA_DIR=/data \
    DRESSMATE_PHOTO_DIR=/data/photos \
    DRESSMATE_WARDROBE_PATH=/data/wardrobe.json \
    PORT=8848

WORKDIR /app

# 代码：引擎、服务、前端、工具、样例数据
COPY engine/       /app/engine/
COPY tools/        /app/tools/
COPY web/          /app/web/
COPY samples/      /app/samples/
COPY data/cities.json /app/data/cities.json
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
