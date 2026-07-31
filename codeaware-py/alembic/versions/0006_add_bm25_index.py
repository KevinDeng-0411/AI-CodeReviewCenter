"""add BM25 index via ParadeDB pg_search (C4-B)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-31

C4-B: 在 knowledge_chunks.chunk_content 上创建 BM25 索引（ParadeDB pg_search v0.12.0，
chinese_compatible tokenizer）。需要 BM25 镜像（codeaware/pgvector-pgsearch:pg16-v0.12.0）。
pg_trgm GIN 索引保留为回退后端；RAG_LEXICAL_BACKEND 默认仍 pg_trgm，C4-D 通过后切 bm25。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pg_search 扩展（需要镜像内置 + shared_preload_libraries）
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    # BM25 索引：chinese_compatible tokenizer 处理中文分词
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_kc_chunk_content_bm25 "
            "ON knowledge_chunks "
            "USING bm25 (chunk_content) "
            "WITH (key_field='id', text_fields='{\"chunk_content\": {\"tokenizer\": {\"type\": \"chinese_compatible\"}}}')"
        )
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kc_chunk_content_bm25")
    # 不自动 DROP EXTENSION pg_search——可能被其他索引使用
