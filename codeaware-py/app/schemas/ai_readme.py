"""AIReadMe API schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AiReadmeResult(BaseModel):
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class AiReadmeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_name: str = Field(min_length=1, max_length=100)
    project_path: str = Field(min_length=1, max_length=4096)


class AiReadmeVO(BaseModel):
    id: int | None = None
    project_name: str
    title: str
    content: str
    version: int = 1
    snapshot_hash: str | None = None
    snapshot_file_count: int | None = None
    snapshot_generated_at: datetime | None = None
    snapshot_truncated: bool | None = None
    ai_model: str = "deepseek-v4-flash"


class AiReadmeCapability(BaseModel):
    enabled: bool
    reason: Literal["available", "disabled", "roots_unavailable"]
