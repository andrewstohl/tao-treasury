"""add_image_url_to_validators

Revision ID: 18e68aa636e9
Revises: p6q7r8s9t0u1
Create Date: 2026-02-09 20:27:18.455083

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18e68aa636e9'
down_revision: Union[str, None] = 'p6q7r8s9t0u1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('validators', sa.Column('image_url', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('validators', 'image_url')
