"""add user_id to conversations (team upgrade phase B)

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable：路由层始终注入非空 user_id；nullable 让直连服务测试无需传 user_id
    op.add_column(
        "conversations",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
    )
    # 回填存量会话到首个 admin（无 admin 则保持 null）
    op.execute(
        "UPDATE conversations SET user_id = "
        "(SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1) "
        "WHERE user_id IS NULL"
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_column("conversations", "user_id")
