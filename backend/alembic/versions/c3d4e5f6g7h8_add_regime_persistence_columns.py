"""Add regime persistence tracking columns to subnets.

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add regime persistence tracking columns."""
    # Add regime_candidate column
    op.add_column(
        'subnets',
        sa.Column('regime_candidate', sa.String(32), nullable=True)
    )
    # Add regime_candidate_days column
    op.add_column(
        'subnets',
        sa.Column('regime_candidate_days', sa.Integer(), server_default='0', nullable=False)
    )


def downgrade() -> None:
    """Remove regime persistence tracking columns."""
    op.drop_column('subnets', 'regime_candidate_days')
    op.drop_column('subnets', 'regime_candidate')
