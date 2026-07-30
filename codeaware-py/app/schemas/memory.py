"""Memory API 与长期记忆抽取契约。"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.enums import MemoryType


class MemorySaveRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4_000)
    memory_type: Literal[MemoryType.REFERENCE] = MemoryType.REFERENCE
    conversation_id: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class MemorySaveVO(BaseModel):
    id: int
    content: str


class MemoryHit(BaseModel):
    id: int
    content: str
    memory_type: MemoryType
    conversation_id: str | None = None
    source: str
    similarity: float


class ExtractedFacts(BaseModel):
    """LLM 从对话中抽取的原子事实契约（json_mode 结构化输出）。"""

    facts: list[str] = Field(default_factory=list)
