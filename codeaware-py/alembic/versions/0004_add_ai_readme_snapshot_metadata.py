"""add AIReadMe snapshot metadata and per-project versions

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_readme_documents",
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ai_readme_documents",
        sa.Column("snapshot_file_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_readme_documents",
        sa.Column("snapshot_generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_readme_documents",
        sa.Column("snapshot_truncated", sa.Boolean(), nullable=True),
    )

    # 旧实现始终写 version=1。先按同项目的插入顺序确定性地规范化历史，
    # 再增加唯一索引，避免既有重复数据阻止迁移。
    op.execute(
        """
        WITH numbered AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY project_name
                    ORDER BY id
                )::integer AS normalized_version
            FROM ai_readme_documents
        )
        UPDATE ai_readme_documents AS document
        SET version = numbered.normalized_version
        FROM numbered
        WHERE document.id = numbered.id
        """
    )
    op.create_index(
        "uq_ard_project_name_version",
        "ai_readme_documents",
        ["project_name", "version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ard_project_name_version",
        table_name="ai_readme_documents",
    )
    op.drop_column("ai_readme_documents", "snapshot_truncated")
    op.drop_column("ai_readme_documents", "snapshot_generated_at")
    op.drop_column("ai_readme_documents", "snapshot_file_count")
    op.drop_column("ai_readme_documents", "snapshot_hash")
