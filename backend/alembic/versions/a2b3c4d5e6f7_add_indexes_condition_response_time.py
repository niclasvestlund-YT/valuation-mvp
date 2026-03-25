"""add indexes, condition and response_time_ms

Revision ID: a2b3c4d5e6f7
Revises: fb17b68a5734
Create Date: 2026-03-25 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str]] = 'fb17b68a5734'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FIX 3: Add missing indexes for admin dashboard performance
    op.create_index("ix_valuations_status", "valuations", ["status"])
    op.create_index("ix_valuations_brand", "valuations", ["brand"])
    op.create_index("ix_valuations_category", "valuations", ["category"])
    op.create_index("ix_price_snapshots_product_date", "price_snapshots", ["product_identifier", "snapshot_date"])

    # FIX 5: Add condition and response_time_ms columns
    op.add_column("valuations", sa.Column("condition", sa.String(), nullable=True))
    op.add_column("valuations", sa.Column("response_time_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("valuations", "response_time_ms")
    op.drop_column("valuations", "condition")
    op.drop_index("ix_price_snapshots_product_date", "price_snapshots")
    op.drop_index("ix_valuations_category", "valuations")
    op.drop_index("ix_valuations_brand", "valuations")
    op.drop_index("ix_valuations_status", "valuations")
