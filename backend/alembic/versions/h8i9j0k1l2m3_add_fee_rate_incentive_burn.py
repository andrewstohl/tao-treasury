"""Add fee_rate and incentive_burn columns to subnets.

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-02-04 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, None] = 'g7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add fee_rate and incentive_burn columns."""
    op.add_column(
        'subnets',
        sa.Column('fee_rate', sa.Numeric(20, 18), nullable=False, server_default='0')
    )
    op.add_column(
        'subnets',
        sa.Column('incentive_burn', sa.Numeric(20, 18), nullable=False, server_default='0')
    )


def downgrade() -> None:
    """Remove fee_rate and incentive_burn columns."""
    op.drop_column('subnets', 'incentive_burn')
    op.drop_column('subnets', 'fee_rate')
