#!/bin/sh
# Container entrypoint: web | scheduler | dev | cli <args> | <any command>
set -e

prepare() {
    alembic upgrade head
    python -m app.cli seed categories --if-empty
    python -m app.cli seed certifications --if-empty
}

case "$1" in
    web)
        prepare
        exec uvicorn app.main:app \
            --host 0.0.0.0 --port 8000 \
            --workers "${WEB_CONCURRENCY:-2}" \
            --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}" \
            --no-server-header
        ;;
    scheduler)
        exec python -m app.scheduler
        ;;
    dev)
        pybabel compile -d app/locales -D messages >/dev/null
        prepare
        exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
        ;;
    cli)
        shift
        exec python -m app.cli "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
