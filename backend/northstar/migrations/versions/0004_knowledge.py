"""Knowledge versions. Frozen migration definitions independent of runtime models."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.create_table(
        "knowledge_policies",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "policy_id", sa.String(100), sa.ForeignKey("knowledge_policies.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("original_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("original", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.String(100)),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("policy_id", "version"),
        sa.UniqueConstraint("content_hash"),
        sa.CheckConstraint("version > 0", name="positive_version"),
        sa.CheckConstraint("status IN ('READY', 'FAILED')", name="processing_status"),
        sa.CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="valid_period"),
    )
    op.create_index("ix_knowledge_documents_policy_id", "knowledge_documents", ["policy_id"])
    op.create_table(
        "knowledge_sections",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(500), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("document_id", "ordinal"),
    )
    op.create_index("ix_knowledge_sections_document_id", "knowledge_sections", ["document_id"])


def downgrade():
    op.drop_table("knowledge_sections")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_policies")
