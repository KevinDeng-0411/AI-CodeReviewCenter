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
    # jieba 分词列 + default tokenizer：jieba 加空格分割中文词，default 以空格切分
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
    op.execute("DROP INDEX IF EXISTS ix_kc_chunk_content_segmented_bm25")
