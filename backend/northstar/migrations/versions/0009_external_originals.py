"""Contract schema after verified original export. No binary originals remain in PostgreSQL."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM knowledge_documents WHERE storage_key IS NULL")
    ):
        raise RuntimeError(
            "Original export required: upgrade to 0008, run "
            "python -m northstar.storage_admin export-legacy, then upgrade head. "
            "Stop API and worker first."
        )
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.drop_column("original")
        batch.alter_column("storage_key", existing_type=sa.String(100), nullable=False)


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM knowledge_documents")):
        raise RuntimeError(
            "Cannot restore database binaries by downgrade. "
            "Restore a coordinated pre-migration backup instead."
        )
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.add_column(sa.Column("original", sa.LargeBinary(), nullable=False))
        batch.alter_column("storage_key", existing_type=sa.String(100), nullable=True)
