"""Add viability scoring columns to subnets.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-02-04 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, None] = 'h8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add viability scoring columns."""
    op.add_column(
        'subnets',
        sa.Column('viability_score', sa.Numeric(5, 1), nullable=True)
    )
    op.add_column(
        'subnets',
        sa.Column('viability_tier', sa.String(16), nullable=True)
    )
    op.add_column(
        'subnets',
        sa.Column('viability_factors', sa.Text(), nullable=True)
    )
    op.add_column(
        'subnets',
        sa.Column('startup_mode', sa.Boolean(), nullable=True)
    )
    op.add_column(
        'subnets',
        sa.Column('price_trend_7d', sa.Numeric(10, 6), nullable=True)
    )
    op.add_column(
        'subnets',
        sa.Column('max_drawdown_30d', sa.Numeric(10, 6), nullable=True)
    )
    op.create_index('ix_subnets_viability_tier', 'subnets', ['viability_tier'])


def downgrade() -> None:
    """Remove viability scoring columns."""
    op.drop_index('ix_subnets_viability_tier', table_name='subnets')
    op.drop_column('subnets', 'max_drawdown_30d')
    op.drop_column('subnets', 'price_trend_7d')
    op.drop_column('subnets', 'startup_mode')
    op.drop_column('subnets', 'viability_factors')
    op.drop_column('subnets', 'viability_tier')
    op.drop_column('subnets', 'viability_score')
