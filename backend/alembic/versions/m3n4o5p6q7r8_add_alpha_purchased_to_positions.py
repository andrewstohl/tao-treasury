"""Add alpha_purchased to positions table.

Tracks alpha tokens from FIFO lots (excludes emission alpha).
Used for proper decomposition of yield vs alpha price gains.

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-02-05 20:00:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "m3n4o5p6q7r8"
down_revision = "l2m3n4o5p6q7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alpha tokens from FIFO lots (excludes emission alpha)
    # emission_alpha = alpha_balance - alpha_purchased
    op.add_column(
        "positions",
        sa.Column("alpha_purchased", sa.Numeric(20, 9), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("positions", "alpha_purchased")
