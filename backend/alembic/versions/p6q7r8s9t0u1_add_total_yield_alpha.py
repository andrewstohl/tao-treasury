"""Add total_yield_alpha field for authoritative yield tracking.

This field stores the sum of daily_income from TaoStats accounting/tax API,
providing the authoritative yield value instead of deriving it.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-02-07 22:00:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "p6q7r8s9t0u1"
down_revision = "o5p6q7r8s9t0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add total_yield_alpha field to positions table
    # This is the authoritative sum of daily_income from accounting/tax API
    op.add_column(
        "positions",
        sa.Column("total_yield_alpha", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("positions", "total_yield_alpha")
