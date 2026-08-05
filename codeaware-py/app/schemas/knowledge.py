"""Knowledge upload/search API contracts."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class KnowledgeUploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=200_000)
    source_type: Literal["MANUAL", "DOC"] = "MANUAL"
    project_name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("title", "project_name")
    @classmethod
    def strip_nonblank_label(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1_000)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class KnowledgeDocumentVO(BaseModel):
    id: int
    title: str


class KnowledgeSearchHit(BaseModel):
    score: float
    match_type: Literal["vector", "keyword", "both"]
    document_id: int
    chunk_content: str


class DocumentVO(BaseModel):
    """文档列表项（ADR-0013 文档管理）。"""

    id: int
    title: str
    source_type: str
    project_name: str | None = None
    status: str  # ACTIVE / DELETED
    chunk_count: int
    created_at: str
    deleted_at: str | None = None


class DocumentListVO(BaseModel):
    total: int
    page: int
    size: int
    records: list[DocumentVO]
