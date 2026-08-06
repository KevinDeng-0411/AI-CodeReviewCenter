from typing import Any

from pydantic import BaseModel


class TaskStatusVO(BaseModel):
    task_id: str
    status: str
    ready: bool
    successful: bool | None = None
    result: Any = None
    error: str | None = None
