"""Conversation - 多轮对话（ADR-0004）。

统一领域词 Conversation，标识 conversation_id（清除 session）。
summary 与 summary_message_count 承载增量摘要及已处理水位线（ADR-0003）。
user_id 承载会话归属（团队化升级阶段 B：按用户隔离）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="ADR-0003 摘要持久化")
    summary_message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="已纳入摘要的消息水位线",
    )
    # 团队化升级阶段 B：nullable 让直连服务测试（不经路由）无需传 user_id；
    # 路由层始终注入非空 user_id，生产中不为 null。
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True, comment="会话归属用户"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_conversations_user_id", "user_id"),)
