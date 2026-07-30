"""AiReadmeDocument - AIReadMe 生成文档与输入快照追踪。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiReadmeDocument(Base):
    __tablename__ = "ai_readme_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(String(100), nullable=False)
    section: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    snapshot_truncated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_ard_project_name", "project_name"),
        Index(
            "uq_ard_project_name_version",
            "project_name",
            "version",
            unique=True,
        ),
    )
