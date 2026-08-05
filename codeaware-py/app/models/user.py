"""User - 用户表（团队化升级阶段 A）。

实验室内部使用：admin/member 二分。admin 可建账号、改 Prompt；member 用所有功能。
会话/消息按 user_id 私有隔离；知识库/记忆全员共享（不加 user_id）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'member'"), comment="admin / member"
    )
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_users_username", "username"),)
