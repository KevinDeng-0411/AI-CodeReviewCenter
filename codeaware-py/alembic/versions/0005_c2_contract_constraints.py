"""add C2 prompt version and memory type constraints

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 旧 manager 在并发下可能得到重复 version。按原 version/id 顺序确定性重排，
    # 再用数据库唯一索引把版本不变量固化。
    op.execute(
        """
        WITH numbered AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY type
                    ORDER BY version, id
                )::integer AS normalized_version
            FROM prompt_templates
        )
        UPDATE prompt_templates AS template
        SET version = numbered.normalized_version
        FROM numbered
        WHERE template.id = numbered.id
        """
    )
    op.create_index(
        "uq_prompt_templates_type_version",
        "prompt_templates",
        ["type", "version"],
        unique=True,
    )

    # ADR-0001：Memory 不再使用会与 Knowledge Document 混淆的 KNOWLEDGE 名称。
    op.execute(
        "UPDATE long_term_memories SET memory_type = 'REFERENCE' "
        "WHERE memory_type = 'KNOWLEDGE'"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM long_term_memories
                WHERE memory_type NOT IN ('REFERENCE', 'FACT')
            ) THEN
                RAISE EXCEPTION
                    'unsupported long_term_memories.memory_type blocks C2 migration';
            END IF;
        END
        $$;
        """
    )
    op.create_check_constraint(
        "ck_long_term_memories_memory_type",
        "long_term_memories",
        "memory_type IN ('REFERENCE', 'FACT')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_long_term_memories_memory_type",
        "long_term_memories",
        type_="check",
    )
    op.execute(
        "UPDATE long_term_memories SET memory_type = 'KNOWLEDGE' "
        "WHERE memory_type = 'REFERENCE'"
    )
    op.drop_index(
        "uq_prompt_templates_type_version",
        table_name="prompt_templates",
    )
