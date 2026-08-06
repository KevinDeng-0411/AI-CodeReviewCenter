"""Celery 应用定义 — 任务队列入口。

使用 Redis 作为 Broker 和 Result Backend（复用现有 Redis）。
所有任务定义在 app.ai.tasks 模块下，自动注册。
"""
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "codeaware",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=60,
    task_max_retries=3,
    result_expires=3600,
)

celery_app.autodiscover_tasks(["app.ai.tasks"])