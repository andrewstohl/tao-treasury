"""Add viability_configs table for UI-adjustable scoring parameters.

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-02-04 22:00:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "viability_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("config_name", sa.String(255), nullable=False, server_default="default"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        # Hard failure thresholds
        sa.Column("min_tao_reserve", sa.Numeric(20, 6), nullable=False),
        sa.Column("min_emission_share", sa.Numeric(10, 6), nullable=False),
        sa.Column("min_age_days", sa.Integer, nullable=False),
        sa.Column("min_holders", sa.Integer, nullable=False),
        sa.Column("max_drawdown_30d", sa.Numeric(10, 6), nullable=False),
        sa.Column("max_negative_flow_ratio", sa.Numeric(10, 6), nullable=False),
        # Scored metric weights
        sa.Column("weight_tao_reserve", sa.Numeric(5, 4), nullable=False),
        sa.Column("weight_net_flow_7d", sa.Numeric(5, 4), nullable=False),
        sa.Column("weight_emission_share", sa.Numeric(5, 4), nullable=False),
        sa.Column("weight_price_trend_7d", sa.Numeric(5, 4), nullable=False),
        sa.Column("weight_subnet_age", sa.Numeric(5, 4), nullable=False),
        sa.Column("weight_max_drawdown_30d", sa.Numeric(5, 4), nullable=False),
        # Tier boundaries
        sa.Column("tier_1_min", sa.Integer, nullable=False),
        sa.Column("tier_2_min", sa.Integer, nullable=False),
        sa.Column("tier_3_min", sa.Integer, nullable=False),
        # Age cap
        sa.Column("age_cap_days", sa.Integer, nullable=False),
        # Feature flag
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_viability_configs_is_active", "viability_configs", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_viability_configs_is_active", table_name="viability_configs")
    op.drop_table("viability_configs")
