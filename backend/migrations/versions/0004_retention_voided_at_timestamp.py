"""voided at timestamp

Revision ID: 0004_retention
Revises: 0003_phase2
Create Date: 2026-09-28 04:45:35.054826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004_retention'
down_revision: Union[str, Sequence[str], None] = '0003_phase2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('evaluation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True))

    # Backfill: existing void rows predate this column. We don't know exactly when they were voided, so use the
    # best available proxy (completed_at if it was completed before voiding, else created_at) rather than leaving
    # retention unable to ever purge them.
    conn = op.get_bind()
    evaluation = sa.table("evaluation", sa.column("id", sa.Integer), sa.column("status", sa.String),
                          sa.column("created_at", sa.DateTime), sa.column("completed_at", sa.DateTime),
                          sa.column("voided_at", sa.DateTime))
    conn.execute(
        evaluation.update().where(evaluation.c.status == "void")
        .values(voided_at=sa.func.coalesce(evaluation.c.completed_at, evaluation.c.created_at))
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('evaluation', schema=None) as batch_op:
        batch_op.drop_column('voided_at')
