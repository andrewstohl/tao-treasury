"""Widen price_trend_7d precision to avoid overflow.

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-02-04 20:45:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "j0k1l2m3n4o5"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "subnets",
        "price_trend_7d",
        type_=sa.Numeric(20, 6),
        existing_type=sa.Numeric(10, 6),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "subnets",
        "price_trend_7d",
        type_=sa.Numeric(10, 6),
        existing_type=sa.Numeric(20, 6),
        existing_nullable=True,
    )
