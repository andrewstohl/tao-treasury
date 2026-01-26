"""add_yield_and_pnl_fields

Revision ID: a1b2c3d4e5f6
Revises: dbe03dba9980
Create Date: 2026-01-25 18:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'dbe03dba9980'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add yield and P&L fields to positions table
    op.add_column('positions', sa.Column('unrealized_pnl_tao', sa.Numeric(precision=20, scale=9), server_default='0', nullable=False))
    op.add_column('positions', sa.Column('unrealized_pnl_pct', sa.Numeric(precision=10, scale=4), server_default='0', nullable=False))
    op.add_column('positions', sa.Column('current_apy', sa.Numeric(precision=10, scale=4), server_default='0', nullable=False))
    op.add_column('positions', sa.Column('apy_30d_avg', sa.Numeric(precision=10, scale=4), server_default='0', nullable=False))
    op.add_column('positions', sa.Column('daily_yield_tao', sa.Numeric(precision=20, scale=9), server_default='0', nullable=False))
    op.add_column('positions', sa.Column('weekly_yield_tao', sa.Numeric(precision=20, scale=9), server_default='0', nullable=False))

    # Add yield and P&L aggregate fields to portfolio_snapshots table
    op.add_column('portfolio_snapshots', sa.Column('portfolio_apy', sa.Numeric(precision=10, scale=4), server_default='0', nullable=False))
    op.add_column('portfolio_snapshots', sa.Column('daily_yield_tao', sa.Numeric(precision=20, scale=9), server_default='0', nullable=False))
    op.add_column('portfolio_snapshots', sa.Column('weekly_yield_tao', sa.Numeric(precision=20, scale=9), server_default='0', nullable=False))
    op.add_column('portfolio_snapshots', sa.Column('monthly_yield_tao', sa.Numeric(precision=20, scale=9), server_default='0', nullable=False))
    op.add_column('portfolio_snapshots', sa.Column('total_unrealized_pnl_tao', sa.Numeric(precision=20, scale=9), server_default='0', nullable=False))
    op.add_column('portfolio_snapshots', sa.Column('total_realized_pnl_tao', sa.Numeric(precision=20, scale=9), server_default='0', nullable=False))
    op.add_column('portfolio_snapshots', sa.Column('total_cost_basis_tao', sa.Numeric(precision=20, scale=9), server_default='0', nullable=False))


def downgrade() -> None:
    # Remove portfolio_snapshots columns
    op.drop_column('portfolio_snapshots', 'total_cost_basis_tao')
    op.drop_column('portfolio_snapshots', 'total_realized_pnl_tao')
    op.drop_column('portfolio_snapshots', 'total_unrealized_pnl_tao')
    op.drop_column('portfolio_snapshots', 'monthly_yield_tao')
    op.drop_column('portfolio_snapshots', 'weekly_yield_tao')
    op.drop_column('portfolio_snapshots', 'daily_yield_tao')
    op.drop_column('portfolio_snapshots', 'portfolio_apy')

    # Remove positions columns
    op.drop_column('positions', 'weekly_yield_tao')
    op.drop_column('positions', 'daily_yield_tao')
    op.drop_column('positions', 'apy_30d_avg')
    op.drop_column('positions', 'current_apy')
    op.drop_column('positions', 'unrealized_pnl_pct')
    op.drop_column('positions', 'unrealized_pnl_tao')
