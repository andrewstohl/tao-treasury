"""Add rank and market_cap_tao to subnets table

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2024-01-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6g7h8i9j0k1'
down_revision: Union[str, None] = 'e5f6g7h8i9j0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subnets', sa.Column('rank', sa.Integer(), nullable=True))
    op.add_column('subnets', sa.Column('market_cap_tao', sa.Numeric(20, 9), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('subnets', 'market_cap_tao')
    op.drop_column('subnets', 'rank')
