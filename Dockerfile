# gitmgf — one image for the web app, the scheduler and CLI tasks.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/gitmgf

# Dependencies first for layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN pybabel compile -d app/locales -D messages \
    && useradd --system --uid 10001 --home-dir /srv/gitmgf gitmgf \
    && mkdir -p /data \
    && chown gitmgf:gitmgf /data \
    && chmod +x deploy/entrypoint.sh

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA} \
    APP_ENV=prod \
    DATA_DIR=/data \
    DATABASE_PATH=/data/gitmgf.db

USER gitmgf
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

ENTRYPOINT ["./deploy/entrypoint.sh"]
CMD ["web"]
