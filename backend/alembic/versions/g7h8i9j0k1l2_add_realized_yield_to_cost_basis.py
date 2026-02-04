"""Add realized_yield_tao and realized_yield_alpha to position_cost_basis

Tracks yield income separately from price gain so that yield data
survives position closure (Position rows get deleted on full unstake).

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2025-02-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, None] = 'f6g7h8i9j0k1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'position_cost_basis',
        sa.Column('realized_yield_tao', sa.Numeric(20, 9), server_default='0', nullable=False),
    )
    op.add_column(
        'position_cost_basis',
        sa.Column('realized_yield_alpha', sa.Numeric(20, 9), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('position_cost_basis', 'realized_yield_alpha')
    op.drop_column('position_cost_basis', 'realized_yield_tao')
