"""Durable extraction claims and byte-hash lookup."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.drop_constraint(op.f("ck_knowledge_documents_processing_status"), type_="check")
        batch.create_check_constraint(
            "processing_status", "status IN ('QUEUED','PROCESSING','READY','FAILED','DUPLICATE')"
        )
        batch.add_column(sa.Column("lease_token", sa.String(36)))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("duplicate_of", sa.String(36)))
        batch.create_index("ix_knowledge_documents_original_hash", ["original_hash"])


def downgrade():
    op.execute(
        "UPDATE knowledge_documents SET status='FAILED', error='worker_schema_downgrade' "
        "WHERE status IN ('QUEUED','PROCESSING','DUPLICATE')"
    )
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.drop_index("ix_knowledge_documents_original_hash")
        for column in ["duplicate_of", "attempts", "lease_expires_at", "lease_token"]:
            batch.drop_column(column)
        batch.drop_constraint(op.f("ck_knowledge_documents_processing_status"), type_="check")
        batch.create_check_constraint("processing_status", "status IN ('READY','FAILED')")
