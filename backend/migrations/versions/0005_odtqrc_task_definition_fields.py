"""odtqrc task definition fields

Revision ID: f4f1499af68d
Revises: 0004_retention
Create Date: 2026-09-28 05:09:20.566659

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_odtqrc'
down_revision: Union[str, Sequence[str], None] = '0004_retention'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.add_column(sa.Column('objective', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('deliverable', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('quality_bar', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('risks', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('subject', schema=None) as batch_op:
        batch_op.drop_column('risks')
        batch_op.drop_column('quality_bar')
        batch_op.drop_column('deliverable')
        batch_op.drop_column('objective')
