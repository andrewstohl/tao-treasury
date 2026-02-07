"""Add decomposed yield and alpha P&L fields.

Adds fields for proper decomposition of P&L into:
- Yield: TAO earned from validator emissions
- Alpha P&L: Price movement on purchased alpha

These fields establish a ledger-based architecture where:
- All calculations happen once during data sync
- Position records contain pre-computed authoritative values
- Portfolio totals are pure sums of position values

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-02-07 15:00:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "o5p6q7r8s9t0"
down_revision = "n4o5p6q7r8s9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Position table: add decomposed yield and alpha P&L fields
    op.add_column(
        "positions",
        sa.Column("unrealized_yield_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )
    op.add_column(
        "positions",
        sa.Column("realized_yield_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )
    op.add_column(
        "positions",
        sa.Column("unrealized_alpha_pnl_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )
    op.add_column(
        "positions",
        sa.Column("realized_alpha_pnl_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )
    op.add_column(
        "positions",
        sa.Column("total_unrealized_pnl_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )
    op.add_column(
        "positions",
        sa.Column("total_realized_pnl_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )

    # PortfolioSnapshot table: add aggregated decomposed fields
    op.add_column(
        "portfolio_snapshots",
        sa.Column("total_unrealized_yield_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )
    op.add_column(
        "portfolio_snapshots",
        sa.Column("total_realized_yield_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )
    op.add_column(
        "portfolio_snapshots",
        sa.Column("total_unrealized_alpha_pnl_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )
    op.add_column(
        "portfolio_snapshots",
        sa.Column("total_realized_alpha_pnl_tao", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    # Remove from portfolio_snapshots
    op.drop_column("portfolio_snapshots", "total_realized_alpha_pnl_tao")
    op.drop_column("portfolio_snapshots", "total_unrealized_alpha_pnl_tao")
    op.drop_column("portfolio_snapshots", "total_realized_yield_tao")
    op.drop_column("portfolio_snapshots", "total_unrealized_yield_tao")

    # Remove from positions
    op.drop_column("positions", "total_realized_pnl_tao")
    op.drop_column("positions", "total_unrealized_pnl_tao")
    op.drop_column("positions", "realized_alpha_pnl_tao")
    op.drop_column("positions", "unrealized_alpha_pnl_tao")
    op.drop_column("positions", "realized_yield_tao")
    op.drop_column("positions", "unrealized_yield_tao")
