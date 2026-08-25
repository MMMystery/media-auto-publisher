FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MAPUB_DATA_DIR=/data

WORKDIR /app

COPY . /app

RUN test -f third_party/social-auto-upload/pyproject.toml \
    && test -f third_party/xianyu-auto-reply/LICENSE \
    && if [ ! -f third_party/social-auto-upload/conf.py ]; then \
         cp third_party/social-auto-upload/conf.example.py third_party/social-auto-upload/conf.py; \
       fi \
    && python -m pip install --no-cache-dir -e . -e third_party/social-auto-upload \
    && python -m pip install --no-cache-dir \
         "aiohttp>=3.9,<4" "httpx>=0.27,<1" "loguru>=0.7,<1" \
         "playwright==1.58.0" "qrcode[pil]>=8,<9" \
    && python -m playwright install --with-deps chromium \
    && patchright install chromium \
    && mkdir -p /data/accounts /data/uploads third_party/social-auto-upload/cookies

EXPOSE 8765

CMD ["mapub", "web", "--host", "0.0.0.0", "--port", "8765"]
