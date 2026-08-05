"""add document status/deleted_at/updated_at (doc management soft-delete)

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
    )
    op.add_column(
        "documents",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_documents_status", "documents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_column("documents", "updated_at")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "status")
