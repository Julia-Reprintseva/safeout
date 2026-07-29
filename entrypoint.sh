#!/bin/sh
set -e

case "$SERVICE_ROLE" in
  bot)
    exec python main.py
    ;;
  worker)
    exec celery -A core.tasks.celery_app worker --loglevel=info
    ;;
  api)
    exec uvicorn api.routes:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  *)
    echo "SERVICE_ROLE must be one of: bot, worker, api (got: '$SERVICE_ROLE')" >&2
    exit 1
    ;;
esac
