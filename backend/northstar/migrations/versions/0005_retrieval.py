"""Atomic local semantic index snapshot."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_retrieval_index",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("generation", sa.String(36), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 'active'", name="singleton"),
        sa.CheckConstraint("status IN ('EMPTY', 'READY')", name="index_status"),
    )


def downgrade():
    op.drop_table("knowledge_retrieval_index")
