"""任务基类 — 统一重试策略、日志、监控。"""
import logging
from celery import Task

logger = logging.getLogger(__name__)


class CodeAwareTask(Task):
    """所有业务任务的基类。

    自动处理：
    - 指数退避重试（60s → 120s → 240s）
    - 结构化日志（task_id, task_name, args）
    - 异常时自动 emit Kafka 事件（如果 producer 可用）
    """
    autoretry_for = (Exception,)
    max_retries = 3
    default_retry_delay = 60
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "task failed task_id=%s name=%s args=%s error=%s",
            task_id, self.name, args, exc,
        )
        self._emit_failure_event(task_id, exc)

    @staticmethod
    def _emit_failure_event(task_id: str, exc: Exception) -> None:
        try:
            from app.ai.events.producer import get_producer
            producer = get_producer()
            if producer:
                from app.ai.events.schemas import ErrorEvent
                import uuid
                event = ErrorEvent(
                    event_id=uuid.uuid4().hex,
                    component="task",
                    code="TASK_FAILED",
                    message=str(exc),
                    details={"task_id": task_id},
                )
                from app.ai.events.producer import emit_event
                emit_event("ops.error", key="TASK_FAILED", data=event.model_dump())
        except Exception:
            pass  # Kafka 不可用时不阻塞任务失败
