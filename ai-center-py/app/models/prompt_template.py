"""PromptTemplate - 领域实体（ADR-0005）。

逻辑身份 = type；每行 = 一个版本；每 type 恰一 is_active=true（部分唯一索引）；
编辑 = 新增版本；回滚 = 激活旧版本。CHAT 纳入模板。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False, comment="CODE_REVIEW/UNIT_TEST/AI_README/CHAT")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="版本标签")
    role_setting: Mapped[str] = mapped_column(Text, nullable=False)
    template_body: Mapped[str] = mapped_column(Text, nullable=False)
    review_dimensions: Mapped[str | None] = mapped_column(String(255), nullable=True)
    severity_levels: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        # ADR-0005 激活不变量：每 type 恰一 is_active=true
        Index(
            "uq_prompt_templates_type_active",
            "type",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )
