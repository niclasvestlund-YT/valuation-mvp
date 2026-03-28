"""add crawl scheduling and job queue fields

Revision ID: 4efbdf7064ea
Revises: b5f1e2c3d4a5
Create Date: 2026-03-28 01:40:31.712781

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '4efbdf7064ea'
down_revision: Union[str, Sequence[str], None] = 'b5f1e2c3d4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Agent job: queue + retry fields
    op.add_column('agent_job', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True))
    op.add_column('agent_job', sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agent_job', sa.Column('task_type', sa.Text(), server_default='crawl', nullable=True))
    op.add_column('agent_job', sa.Column('priority', sa.Integer(), server_default='5', nullable=True))
    op.add_column('agent_job', sa.Column('attempts', sa.Integer(), server_default='0', nullable=True))
    op.add_column('agent_job', sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=True))
    op.add_column('agent_job', sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('agent_job', sa.Column('last_error', sa.Text(), nullable=True))
    op.create_index('idx_agent_job_scheduled', 'agent_job', ['scheduled_for'], unique=False)
    op.create_index('idx_agent_job_status_priority', 'agent_job', ['status', 'priority'], unique=False)
    # Product: crawl tier + scheduling
    op.add_column('product', sa.Column('crawl_tier', sa.Text(), server_default='warm', nullable=True))
    op.add_column('product', sa.Column('last_crawled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('product', sa.Column('crawl_enabled', sa.Boolean(), server_default='true', nullable=True))
    # Backfill existing agent_job status from "running" default to "pending" for queue semantics
    op.execute("UPDATE agent_job SET status = 'completed' WHERE status = 'done'")


def downgrade() -> None:
    op.drop_column('product', 'crawl_enabled')
    op.drop_column('product', 'last_crawled_at')
    op.drop_column('product', 'crawl_tier')
    op.drop_index('idx_agent_job_status_priority', table_name='agent_job')
    op.drop_index('idx_agent_job_scheduled', table_name='agent_job')
    op.drop_column('agent_job', 'last_error')
    op.drop_column('agent_job', 'next_retry_at')
    op.drop_column('agent_job', 'max_attempts')
    op.drop_column('agent_job', 'attempts')
    op.drop_column('agent_job', 'priority')
    op.drop_column('agent_job', 'task_type')
    op.drop_column('agent_job', 'scheduled_for')
    op.drop_column('agent_job', 'created_at')
