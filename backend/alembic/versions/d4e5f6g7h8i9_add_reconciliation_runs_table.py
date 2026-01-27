"""Add reconciliation_runs table for Phase 2

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2024-01-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reconciliation_runs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('wallet_address', sa.String(length=128), nullable=False),
        sa.Column('netuids_checked', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=False, default=False),
        sa.Column('total_checks', sa.Integer(), nullable=False, default=0),
        sa.Column('passed_checks', sa.Integer(), nullable=False, default=0),
        sa.Column('failed_checks', sa.Integer(), nullable=False, default=0),
        sa.Column('total_stored_value_tao', sa.Numeric(precision=20, scale=9), nullable=False, default=0),
        sa.Column('total_live_value_tao', sa.Numeric(precision=20, scale=9), nullable=False, default=0),
        sa.Column('total_diff_tao', sa.Numeric(precision=20, scale=9), nullable=False, default=0),
        sa.Column('total_diff_pct', sa.Numeric(precision=10, scale=6), nullable=False, default=0),
        sa.Column('checks', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('absolute_tolerance_tao', sa.Numeric(precision=20, scale=9), nullable=False, default=0.0001),
        sa.Column('relative_tolerance_pct', sa.Numeric(precision=10, scale=6), nullable=False, default=0.1),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reconciliation_runs_run_id', 'reconciliation_runs', ['run_id'], unique=True)
    op.create_index('ix_reconciliation_runs_wallet_address', 'reconciliation_runs', ['wallet_address'], unique=False)
    op.create_index('ix_reconciliation_runs_wallet_created', 'reconciliation_runs', ['wallet_address', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_reconciliation_runs_wallet_created', table_name='reconciliation_runs')
    op.drop_index('ix_reconciliation_runs_wallet_address', table_name='reconciliation_runs')
    op.drop_index('ix_reconciliation_runs_run_id', table_name='reconciliation_runs')
    op.drop_table('reconciliation_runs')
