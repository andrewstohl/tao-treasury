"""Add signal_runs table for Phase 3

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2024-01-26 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5f6g7h8i9j0'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'signal_runs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('signal_id', sa.String(length=64), nullable=False),
        sa.Column('signal_name', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('confidence', sa.String(length=32), nullable=False),
        sa.Column('confidence_reason', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('recommended_action', sa.Text(), nullable=False),
        sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('guardrails_triggered', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('full_output', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('inputs_hash', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_signal_runs_run_id', 'signal_runs', ['run_id'], unique=False)
    op.create_index('ix_signal_runs_signal_id', 'signal_runs', ['signal_id'], unique=False)
    op.create_index('ix_signal_runs_status', 'signal_runs', ['status'], unique=False)
    op.create_index('ix_signal_runs_signal_created', 'signal_runs', ['signal_id', 'created_at'], unique=False)
    op.create_index('ix_signal_runs_created', 'signal_runs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_signal_runs_created', table_name='signal_runs')
    op.drop_index('ix_signal_runs_signal_created', table_name='signal_runs')
    op.drop_index('ix_signal_runs_status', table_name='signal_runs')
    op.drop_index('ix_signal_runs_signal_id', table_name='signal_runs')
    op.drop_index('ix_signal_runs_run_id', table_name='signal_runs')
    op.drop_table('signal_runs')
