"""Expand schema for private objects and human-reviewed knowledge.

Existing versions become unclassified and unpublished. Stop writers during upgrade.
Run the verified original export at this revision before upgrading populated databases.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for name in ("created_at", "updated_at")
    ]


def upgrade():
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.add_column(sa.Column("storage_key", sa.String(100)))
        batch.create_unique_constraint("uq_knowledge_documents_storage_key", ["storage_key"])
        for name, length, default in [
            ("title", 160, "Legacy document"),
            ("sensitivity", 30, "UNCLASSIFIED"),
            ("publication_status", 30, "PENDING_REVIEW"),
            ("review_status", 20, "PENDING"),
        ]:
            batch.add_column(
                sa.Column(name, sa.String(length), nullable=False, server_default=default)
            )
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("review_lease_token", sa.String(36)))
        batch.add_column(sa.Column("review_lease_expires_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column("review_attempts", sa.Integer(), nullable=False, server_default="0")
        )
        batch.create_check_constraint(
            "sensitivity",
            "sensitivity IN ('UNCLASSIFIED','PUBLIC','INTERNAL',"
            "'CONFIDENTIAL','HIGHLY_RESTRICTED')",
        )
        batch.create_check_constraint(
            "publication_status",
            "publication_status IN ('PENDING_REVIEW','APPROVED','REJECTED',"
            "'CHANGES_REQUESTED','DELETED')",
        )
    op.create_table(
        "knowledge_stored_objects",
        sa.Column("key", sa.String(100), primary_key=True),
        *timestamps(),
    )
    op.create_table(
        "knowledge_review_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model_id", sa.String(100)),
        sa.Column("assessment_status", sa.String(20), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("review_reasons", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("supporting_references", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("prompt_version", sa.String(30), nullable=False),
        *timestamps(),
    )
    op.create_index(
        "ix_knowledge_review_assessments_document_id",
        "knowledge_review_assessments",
        ["document_id"],
    )
    op.create_table(
        "knowledge_document_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id"), nullable=False
        ),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        *timestamps(),
    )
    op.create_index(
        "ix_knowledge_document_events_document_id", "knowledge_document_events", ["document_id"]
    )
    # Old indexes may contain content with unknown sensitivity; never retain those embeddings.
    op.execute("DELETE FROM knowledge_retrieval_index")


def downgrade():
    for name in (
        "knowledge_document_events",
        "knowledge_review_assessments",
        "knowledge_stored_objects",
    ):
        op.drop_table(name)
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.drop_constraint(op.f("ck_knowledge_documents_sensitivity"), type_="check")
        batch.drop_constraint(op.f("ck_knowledge_documents_publication_status"), type_="check")
        batch.drop_constraint("uq_knowledge_documents_storage_key", type_="unique")
        for name in (
            "storage_key",
            "title",
            "sensitivity",
            "publication_status",
            "approved_at",
            "review_status",
            "review_lease_token",
            "review_lease_expires_at",
            "review_attempts",
        ):
            batch.drop_column(name)
