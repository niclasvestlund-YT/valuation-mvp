"""add ocr_provider and ocr_text_found to valuations

Revision ID: 40aec0a6bc49
Revises: ebfc16bbbee6
Create Date: 2026-03-27 10:54:00.243304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '40aec0a6bc49'
down_revision: Union[str, Sequence[str], None] = 'ebfc16bbbee6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('valuations', sa.Column('ocr_provider', sa.String(length=50), nullable=True))
    op.add_column('valuations', sa.Column('ocr_text_found', sa.Boolean(), nullable=True))
    op.create_index('ix_valuations_ocr_provider', 'valuations', ['ocr_provider'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_valuations_ocr_provider', table_name='valuations')
    op.drop_column('valuations', 'ocr_text_found')
    op.drop_column('valuations', 'ocr_provider')
