"""Add USD cost basis tracking to position_cost_basis.

Tracks USD values at stake time for conversion exposure analysis.
Enables decomposition of P&L into TAO/USD (FX) and Alpha/TAO effects.

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-02-05 18:00:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "l2m3n4o5p6q7"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # USD cost basis - sum of USD values for remaining FIFO lots
    op.add_column(
        "position_cost_basis",
        sa.Column("usd_cost_basis", sa.Numeric(20, 2), nullable=False, server_default="0"),
    )
    # Weighted average USD per alpha at entry
    op.add_column(
        "position_cost_basis",
        sa.Column("weighted_avg_entry_price_usd", sa.Numeric(20, 6), nullable=False, server_default="0"),
    )
    # Total USD ever staked into this position
    op.add_column(
        "position_cost_basis",
        sa.Column("total_staked_usd", sa.Numeric(20, 2), nullable=False, server_default="0"),
    )
    # Total USD received from unstaking
    op.add_column(
        "position_cost_basis",
        sa.Column("total_unstaked_usd", sa.Numeric(20, 2), nullable=False, server_default="0"),
    )
    # Realized P&L in USD terms
    op.add_column(
        "position_cost_basis",
        sa.Column("realized_pnl_usd", sa.Numeric(20, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("position_cost_basis", "realized_pnl_usd")
    op.drop_column("position_cost_basis", "total_unstaked_usd")
    op.drop_column("position_cost_basis", "total_staked_usd")
    op.drop_column("position_cost_basis", "weighted_avg_entry_price_usd")
    op.drop_column("position_cost_basis", "usd_cost_basis")
