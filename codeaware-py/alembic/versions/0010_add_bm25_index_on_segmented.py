"""add BM25 index on chunk_content_segmented (jieba + default tokenizer)

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
    # ParadeDB 每表只允许一个 BM25 索引。替换 0006 旧索引（default on chunk_content）
    # 为新索引（default on chunk_content_segmented），保留 pg_trgm 回退路径。
    op.execute("DROP INDEX IF EXISTS ix_kc_chunk_content_bm25")
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_kc_chunk_content_segmented_bm25 "
            "ON knowledge_chunks USING bm25 (chunk_content_segmented) "
            "WITH (key_field='id', "
            "text_fields='{\"chunk_content_segmented\": "
            "{\"tokenizer\": {\"type\": \"default\"}}}')"
        )
    )


def downgrade() -> None:
    """回退：删新索引，重建旧索引（chunk_content + default tokenizer）。"""
    op.execute("DROP INDEX IF EXISTS ix_kc_chunk_content_segmented_bm25")
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_kc_chunk_content_bm25 "
            "ON knowledge_chunks USING bm25 (chunk_content) "
            "WITH (key_field='id', "
            "text_fields='{\"chunk_content\": {\"tokenizer\": {\"type\": \"default\"}}}')"
        )
    )
