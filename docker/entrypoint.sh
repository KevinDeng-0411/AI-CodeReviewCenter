#!/bin/sh
# Combined entrypoint: Celery Worker + Flower
celery -A app.ai.celery_app worker --loglevel=info --concurrency=2 --max-tasks-per-child=50 &
# Flower 默认按 UTC 显示事件时间；加 --timezone 对齐本地时区（Asia/Shanghai）
celery -A app.ai.celery_app flower --loglevel=info --port=5555 --address=0.0.0.0 --timezone=Asia/Shanghai
wait
