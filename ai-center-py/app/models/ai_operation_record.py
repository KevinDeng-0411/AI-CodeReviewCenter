"""AiOperationRecord - 审计日志（ADR-0006）。

合并 CR/UT 记录；type 鉴别；result 多态；type 特有字段进 metadata JSON。
append-only，无生命周期。注意：列名 metadata 与 DeclarativeBase.metadata 冲突，
Python 属性用 meta，映射到列 metadata。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiOperationRecord(Base):
    __tablename__ = "ai_operation_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False, comment="CODE_REVIEW/UNIT_TEST")
    project_name: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False, comment="CR 评审 JSON / UT 测试代码")
    prompt_template_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("prompt_templates.id"), nullable=True
    )
    ai_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
