"""Document - 知识库父实体（ADR-0002）。

全文 content 只存一次（修 Java 按 chunk 重复存）；1 文档 -> N chunks，级联删除。
status 承载软删标记（ADR-0013）：ACTIVE=正常使用，DELETED=已软删（chunks 已物理删）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    project_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="全文，只存一次")
    # ADR-0013 文档管理：软删标记 + 时间戳
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ACTIVE", comment="ACTIVE/DELETED"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_documents_status", "status"),)
