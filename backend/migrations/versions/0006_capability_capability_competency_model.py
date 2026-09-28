"""capability competency model

Revision ID: 6e95393b6688
Revises: 0005_odtqrc
Create Date: 2026-09-28 05:17:34.272837

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_capability'
down_revision: Union[str, Sequence[str], None] = '0005_odtqrc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('capability',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('person', sa.String(length=120), nullable=False),
    sa.Column('scorecard_id', sa.Integer(), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('set_by', sa.String(length=120), nullable=False),
    sa.Column('set_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('level between 1 and 6', name='ck_capability_level'),
    sa.ForeignKeyConstraint(['scorecard_id'], ['scorecard.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('capability', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_capability_person'), ['person'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('capability', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_capability_person'))

    op.drop_table('capability')
