"""add chunk_content_segmented column for jieba-segmented BM25 (C4 Chinese optimization)

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("chunk_content_segmented", sa.Text(), nullable=True),
    )
    # 回填：存量 chunk 先 COPY 原文（后续可 offline jieba 分词重填）
    op.execute(
        "UPDATE knowledge_chunks SET chunk_content_segmented = chunk_content "
        "WHERE chunk_content_segmented IS NULL"
    )


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "chunk_content_segmented")
