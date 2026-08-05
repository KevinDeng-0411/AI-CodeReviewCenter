"""KnowledgeChunk - 知识库分块子实体（ADR-0002）。

document_id FK 指向 documents.id，级联删除；embedding 内联 Vector(1024)（ADR-0001）。
混合检索（pg_trgm + pgvector）作用于此表。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_content: Mapped[str] = mapped_column(Text, nullable=False)
    # jieba 分词列（C4 中文优化：default tokenizer 不拆中文，应用层分词后空格连接）
    chunk_content_segmented: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_kc_document_id", "document_id"),
        # 向量检索 HNSW 索引（cosine）
        Index(
            "ix_kc_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # 关键词检索 pg_trgm GIN 索引（ADR-0001 改进②）
        Index(
            "ix_kc_chunk_content_trgm",
            "chunk_content",
            postgresql_using="gin",
            postgresql_ops={"chunk_content": "gin_trgm_ops"},
        ),
    )
