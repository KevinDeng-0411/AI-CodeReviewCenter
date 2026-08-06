"""任务状态查询 API。"""
from celery.result import AsyncResult
from fastapi import APIRouter
from app.ai.celery_app import celery_app
from app.core.response import Result
from app.schemas.task import TaskStatusVO

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


@router.get("/{task_id}", response_model=Result[TaskStatusVO])
async def get_task_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return Result.ok(TaskStatusVO(
        task_id=task_id,
        status=result.status,
        ready=result.ready(),
        successful=result.successful() if result.ready() else None,
        result=result.result if result.ready() and result.successful() else None,
        error=str(result.result) if result.ready() and not result.successful() else None,
    ))
