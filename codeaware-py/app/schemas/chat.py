"""Chat schemas - 请求/响应。"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


class ChatResponseVO(BaseModel):
    conversation_id: str
    reply: str
    memory_summary: str | None = None
