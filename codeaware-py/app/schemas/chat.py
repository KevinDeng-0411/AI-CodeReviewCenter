"""Chat schemas - 请求/响应。"""

from pydantic import BaseModel, Field, field_validator

from app.schemas.chat_events import Component


class ChatRequest(BaseModel):
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=20_000)

    @field_validator("conversation_id")
    @classmethod
    def conversation_id_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("conversation_id must not be blank")
        return value

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


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


class ConversationItem(BaseModel):
    id: int
    conversation_id: str
    title: str | None = None
    summary: str | None = None


class ChatMessageVO(BaseModel):
    role: str
    content: str
