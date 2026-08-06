from pydantic import BaseModel


class TaskStatusVO(BaseModel):
    task_id: str
    status: str
    ready: bool
    successful: bool | None = None
    result: dict | list | str | None = None
    error: str | None = None