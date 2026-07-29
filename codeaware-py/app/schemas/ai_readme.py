"""AIReadMe schemas。"""

from pydantic import BaseModel


class AiReadmeResult(BaseModel):
    content: str


class AiReadmeRequest(BaseModel):
    project_name: str
    project_path: str


class AiReadmeVO(BaseModel):
    id: int | None = None
    project_name: str
    title: str
    content: str
    ai_model: str = "deepseek-v4-flash"
