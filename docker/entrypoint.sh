#!/bin/sh
# Combined entrypoint: Celery Worker + Flower
celery -A app.ai.celery_app worker --loglevel=info --concurrency=2 --max-tasks-per-child=50 &
celery -A app.ai.celery_app flower --loglevel=info --port=5555 --address=0.0.0.0
wait
