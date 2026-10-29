"""Independent extraction verification and immutable processing revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.add_column(
            sa.Column("extraction_status", sa.String(20), nullable=False, server_default="PENDING")
        )
        batch.add_column(
            sa.Column("extraction_revision", sa.Integer(), nullable=False, server_default="0")
        )
    op.create_table(
        "knowledge_extraction_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", "revision"),
    )
    op.create_index(
        "ix_knowledge_extraction_records_document_id",
        "knowledge_extraction_records",
        ["document_id"],
    )
    # Legacy content has no verification evidence. Reprocessing/review is required.
    op.execute(
        "UPDATE knowledge_documents SET extraction_status='HUMAN_REQUIRED' "
        "WHERE status IN ('READY','FAILED')"
    )
    op.execute("DELETE FROM knowledge_retrieval_index")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM knowledge_extraction_records")):
        raise RuntimeError("Cannot discard extraction provenance; restore a coordinated backup.")
    op.drop_table("knowledge_extraction_records")
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.drop_column("extraction_revision")
        batch.drop_column("extraction_status")
