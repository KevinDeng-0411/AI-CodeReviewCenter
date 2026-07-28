"""实体 Pydantic schemas - Create/Read，P1 数据层用。

注：ORM 中 AiOperationRecord/LongTermMemory 的列名为 metadata（与 DeclarativeBase.metadata
冲突），Python 属性用 meta；schema 对外用 metadata，转 ORM 时映射到 meta。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- PromptTemplate ----------
class PromptTemplateRead(ORMBase):
    id: int
    type: str
    version: int
    name: str
    role_setting: str
    template_body: str
    review_dimensions: str | None = None
    severity_levels: str | None = None
    is_active: bool
    created_at: datetime


# ---------- AiOperationRecord ----------
class AiOperationRecordRead(ORMBase):
    id: int
    type: str
    project_name: str
    file_path: str
    source_code: str
    result: str
    prompt_template_id: int | None = None
    ai_model: str | None = None
    metadata: dict | None = None
    created_at: datetime


# ---------- Conversation ----------
class ConversationCreate(BaseModel):
    conversation_id: str
    title: str | None = None


class ConversationRead(ORMBase):
    id: int
    conversation_id: str
    title: str | None = None
    summary: str | None = None
    created_at: datetime


# ---------- Message ----------
class MessageCreate(BaseModel):
    conversation_id: str
    role: str
    content: str
    token_count: int = 0


class MessageRead(ORMBase):
    id: int
    conversation_id: str
    role: str
    content: str
    token_count: int
    created_at: datetime


# ---------- Document ----------
class DocumentCreate(BaseModel):
    title: str
    source_type: str
    project_name: str | None = None
    content: str


class DocumentRead(ORMBase):
    id: int
    title: str
    source_type: str
    project_name: str | None = None
    content: str
    created_at: datetime


# ---------- KnowledgeChunk ----------
class KnowledgeChunkRead(ORMBase):
    id: int
    document_id: int
    chunk_index: int
    chunk_content: str
    created_at: datetime


# ---------- LongTermMemory ----------
class LongTermMemoryCreate(BaseModel):
    content: str
    memory_type: str
    conversation_id: str | None = None
    metadata: dict | None = None


class LongTermMemoryRead(ORMBase):
    id: int
    conversation_id: str | None = None
    content: str
    memory_type: str
    metadata: dict | None = None
    created_at: datetime
