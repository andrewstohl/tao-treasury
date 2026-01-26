"""add_delegation_events_tables

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-25 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create delegation_events table
    op.create_table(
        'delegation_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('wallet_address', sa.String(length=64), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('block_number', sa.BigInteger(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('netuid', sa.BigInteger(), nullable=False),
        sa.Column('hotkey', sa.String(length=64), nullable=True),
        sa.Column('amount_rao', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('amount_tao', sa.Numeric(precision=20, scale=9), nullable=False, server_default='0'),
        sa.Column('alpha_amount', sa.Numeric(precision=20, scale=9), nullable=True),
        sa.Column('tao_price_usd', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('usd_value', sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column('is_reward', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reward_source', sa.String(length=32), nullable=True),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id')
    )
    op.create_index('ix_delegation_events_wallet_address', 'delegation_events', ['wallet_address'], unique=False)
    op.create_index('ix_delegation_events_netuid', 'delegation_events', ['netuid'], unique=False)
    op.create_index('ix_delegation_events_timestamp', 'delegation_events', ['timestamp'], unique=False)
    op.create_index('ix_delegation_events_wallet_netuid', 'delegation_events', ['wallet_address', 'netuid'], unique=False)
    op.create_index('ix_delegation_events_wallet_type', 'delegation_events', ['wallet_address', 'event_type'], unique=False)

    # Create position_yield_history table
    op.create_table(
        'position_yield_history',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('wallet_address', sa.String(length=64), nullable=False),
        sa.Column('netuid', sa.BigInteger(), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('alpha_balance_start', sa.Numeric(precision=20, scale=9), nullable=False, server_default='0'),
        sa.Column('alpha_balance_end', sa.Numeric(precision=20, scale=9), nullable=False, server_default='0'),
        sa.Column('tao_value_start', sa.Numeric(precision=20, scale=9), nullable=False, server_default='0'),
        sa.Column('tao_value_end', sa.Numeric(precision=20, scale=9), nullable=False, server_default='0'),
        sa.Column('yield_alpha', sa.Numeric(precision=20, scale=9), nullable=False, server_default='0'),
        sa.Column('yield_tao', sa.Numeric(precision=20, scale=9), nullable=False, server_default='0'),
        sa.Column('net_stake_tao', sa.Numeric(precision=20, scale=9), nullable=False, server_default='0'),
        sa.Column('daily_apy', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_position_yield_wallet_netuid_date', 'position_yield_history', ['wallet_address', 'netuid', 'date'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_position_yield_wallet_netuid_date', table_name='position_yield_history')
    op.drop_table('position_yield_history')

    op.drop_index('ix_delegation_events_wallet_type', table_name='delegation_events')
    op.drop_index('ix_delegation_events_wallet_netuid', table_name='delegation_events')
    op.drop_index('ix_delegation_events_timestamp', table_name='delegation_events')
    op.drop_index('ix_delegation_events_netuid', table_name='delegation_events')
    op.drop_index('ix_delegation_events_wallet_address', table_name='delegation_events')
    op.drop_table('delegation_events')
