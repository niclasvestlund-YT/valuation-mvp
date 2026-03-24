"""initial_schema

Revision ID: fb17b68a5734
Revises: 
Create Date: 2026-03-24 20:25:04.017780

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fb17b68a5734'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "valuations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("product_name", sa.String(), nullable=True),
        sa.Column("product_identifier", sa.String(), nullable=True),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("vision_confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("estimated_value", sa.Integer(), nullable=True),
        sa.Column("value_range_low", sa.Integer(), nullable=True),
        sa.Column("value_range_high", sa.Integer(), nullable=True),
        sa.Column("new_price", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("num_comparables_raw", sa.Integer(), nullable=True),
        sa.Column("num_comparables_used", sa.Integer(), nullable=True),
        sa.Column("sources_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("market_data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("feedback", sa.String(), nullable=True),
        sa.Column("corrected_product", sa.String(), nullable=True),
        sa.Column("is_correction", sa.Boolean(), nullable=True),
        sa.Column("original_valuation_id", sa.String(), sa.ForeignKey("valuations.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_valuations_created_at", "valuations", ["created_at"])
    op.create_index("ix_valuations_product_name", "valuations", ["product_name"])
    op.create_index("ix_valuations_product_identifier", "valuations", ["product_identifier"])

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("product_identifier", sa.String(), nullable=True),
        sa.Column("estimated_value", sa.Integer(), nullable=True),
        sa.Column("value_range_low", sa.Integer(), nullable=True),
        sa.Column("value_range_high", sa.Integer(), nullable=True),
        sa.Column("new_price", sa.Integer(), nullable=True),
        sa.Column("num_comparables", sa.Integer(), nullable=True),
        sa.Column("sources_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("snapshot_date", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_snapshots_product_identifier", "price_snapshots", ["product_identifier"])
    op.create_index("ix_price_snapshots_snapshot_date", "price_snapshots", ["snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_price_snapshots_snapshot_date", "price_snapshots")
    op.drop_index("ix_price_snapshots_product_identifier", "price_snapshots")
    op.drop_table("price_snapshots")
    op.drop_index("ix_valuations_product_identifier", "valuations")
    op.drop_index("ix_valuations_product_name", "valuations")
    op.drop_index("ix_valuations_created_at", "valuations")
    op.drop_table("valuations")
