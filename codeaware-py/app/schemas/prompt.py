"""Prompt management API contracts."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import PromptType


class PromptCreateRequest(BaseModel):
    type: PromptType
    name: str = Field(min_length=1, max_length=100)
    role_setting: str = Field(min_length=1, max_length=10_000)
    template_body: str = Field(min_length=1, max_length=60_000)
    review_dimensions: str | None = Field(default=None, max_length=255)
    severity_levels: str | None = Field(default=None, max_length=100)

    @field_validator(
        "name",
        "role_setting",
        "template_body",
        "review_dimensions",
        "severity_levels",
    )
    @classmethod
    def strip_nonblank_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class PromptTemplateVO(BaseModel):
    id: int
    type: PromptType
    version: int
    name: str
    role_setting: str
    template_body: str
    review_dimensions: str | None = None
    severity_levels: str | None = None
    is_active: bool
    created_at: datetime


class PromptPreviewVO(BaseModel):
    rendered: str
