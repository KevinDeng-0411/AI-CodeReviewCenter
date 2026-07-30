"""Chat schemas - 请求/响应。"""

from pydantic import BaseModel, Field

from app.schemas.chat_events import Component


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


class ChatWarning(BaseModel):
    component: Component
    code: str
    message: str
    retryable: bool


class ChatResponseVO(BaseModel):
    conversation_id: str
    reply: str
    memory_summary: str | None = None
    warnings: list[ChatWarning] = Field(default_factory=list)
