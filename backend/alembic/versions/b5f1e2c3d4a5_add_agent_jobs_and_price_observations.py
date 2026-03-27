"""add VALOR tables: agent_jobs, price_observations, training_samples, valor_models, valor_estimates, price_statistics + valor columns on valuations

Revision ID: b5f1e2c3d4a5
Revises: 40aec0a6bc49
Create Date: 2026-03-27 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = 'b5f1e2c3d4a5'
down_revision: Union[str, Sequence[str], None] = '40aec0a6bc49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agent_job ---
    op.create_table(
        'agent_job',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('product_key', sa.Text(), nullable=False),
        sa.Column('search_terms', ARRAY(sa.Text()), nullable=True),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('observations_added', sa.Integer(), server_default='0'),
        sa.Column('observations_rejected', sa.Integer(), server_default='0'),
        sa.Column('status', sa.Text(), nullable=False, server_default='running'),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
    )
    op.create_index('idx_agent_job_started', 'agent_job', ['started_at'])
    op.create_index('idx_agent_job_product_started', 'agent_job', ['product_key', 'started_at'])

    # --- price_observation ---
    op.create_table(
        'price_observation',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('product_key', sa.Text(), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('price_sek', sa.Integer(), nullable=False),
        sa.Column('condition', sa.Text(), server_default='unknown'),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('agent_run_id', sa.Text(), nullable=True),
        sa.Column('is_sold', sa.Boolean(), server_default='false'),
        sa.Column('listing_type', sa.Text(), server_default='unknown'),
        sa.Column('final_price', sa.Boolean(), server_default='false'),
        sa.Column('days_since_listed', sa.Integer(), nullable=True),
        sa.Column('price_to_new_ratio', sa.Float(), nullable=True),
        sa.Column('new_price_at_observation', sa.Integer(), nullable=True),
        sa.Column('suspicious', sa.Boolean(), server_default='false'),
        sa.Column('suspicious_reason', sa.Text(), nullable=True),
        sa.Column('currency', sa.Text(), server_default='SEK'),
    )
    op.create_index('ix_price_observation_product_key', 'price_observation', ['product_key'])
    op.create_index('idx_obs_product_observed', 'price_observation', ['product_key', 'observed_at'])
    op.create_index('idx_obs_suspicious_product', 'price_observation', ['suspicious', 'product_key'])

    # --- training_sample ---
    op.create_table(
        'training_sample',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('product_key', sa.Text(), nullable=False),
        sa.Column('price_sek', sa.Integer(), nullable=False),
        sa.Column('condition', sa.Text(), server_default='unknown'),
        sa.Column('condition_encoded', sa.Float(), nullable=False),
        sa.Column('source_type', sa.Text(), nullable=False),
        sa.Column('source_id', sa.Text(), nullable=False, unique=True),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('listing_type', sa.Text(), server_default='unknown'),
        sa.Column('final_price', sa.Boolean(), server_default='false'),
        sa.Column('is_sold', sa.Boolean(), server_default='false'),
        sa.Column('price_to_new_ratio', sa.Float(), nullable=True),
        sa.Column('new_price_at_observation', sa.Integer(), nullable=True),
        sa.Column('days_since_observation', sa.Integer(), nullable=True),
        sa.Column('month_of_year', sa.Integer(), nullable=True),
        sa.Column('quality_score', sa.Float(), server_default='0.0'),
        sa.Column('included_in_training', sa.Boolean(), server_default='false'),
        sa.Column('excluded_reason', sa.Text(), nullable=True),
    )
    op.create_index('idx_training_product_included', 'training_sample', ['product_key', 'included_in_training'])

    # --- valor_model ---
    op.create_table(
        'valor_model',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('trained_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('model_version', sa.Text(), nullable=False, unique=True),
        sa.Column('model_filename', sa.Text(), nullable=False),
        sa.Column('training_samples', sa.Integer(), nullable=True),
        sa.Column('test_samples', sa.Integer(), nullable=True),
        sa.Column('mae_sek', sa.Float(), nullable=True),
        sa.Column('mape_pct', sa.Float(), nullable=True),
        sa.Column('within_10pct', sa.Float(), nullable=True),
        sa.Column('within_20pct', sa.Float(), nullable=True),
        sa.Column('vs_baseline_mae', sa.Float(), nullable=True),
        sa.Column('vs_baseline_improvement_pct', sa.Float(), nullable=True),
        sa.Column('feature_importance', JSONB(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='false'),
        sa.Column('min_samples_met', sa.Boolean(), server_default='false'),
        sa.Column('data_quality_warnings', ARRAY(sa.Text()), nullable=True),
        sa.Column('rolled_back_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rolled_back_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
    )
    op.create_index('idx_valor_model_active', 'valor_model', ['is_active', 'trained_at'])

    # --- valor_estimate ---
    op.create_table(
        'valor_estimate',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('valuation_id', sa.String(), nullable=False),
        sa.Column('model_version', sa.Text(), nullable=False),
        sa.Column('estimated_price_sek', sa.Integer(), nullable=False),
        sa.Column('confidence_label', sa.Text(), nullable=True),
        sa.Column('mae_at_prediction', sa.Float(), nullable=True),
        sa.Column('feature_values', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_valor_estimate_valuation_id', 'valor_estimate', ['valuation_id'])
    op.create_index('idx_valor_estimate_created', 'valor_estimate', ['created_at'])

    # --- price_statistic ---
    op.create_table(
        'price_statistic',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('product_key', sa.Text(), nullable=False),
        sa.Column('calculated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('median_price', sa.Integer(), nullable=True),
        sa.Column('p15_price', sa.Integer(), nullable=True),
        sa.Column('p85_price', sa.Integer(), nullable=True),
        sa.Column('sample_size', sa.Integer(), nullable=True),
        sa.Column('source_breakdown', JSONB(), nullable=True),
    )
    op.create_index('idx_price_stat_product', 'price_statistic', ['product_key', 'calculated_at'])

    # --- Add VALOR columns to valuations ---
    op.add_column('valuations', sa.Column('valor_estimate_sek', sa.Integer(), nullable=True))
    op.add_column('valuations', sa.Column('valor_model_version', sa.Text(), nullable=True))
    op.add_column('valuations', sa.Column('valor_confidence_label', sa.Text(), nullable=True))
    op.add_column('valuations', sa.Column('valor_mae_at_prediction', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('valuations', 'valor_mae_at_prediction')
    op.drop_column('valuations', 'valor_confidence_label')
    op.drop_column('valuations', 'valor_model_version')
    op.drop_column('valuations', 'valor_estimate_sek')

    op.drop_index('idx_price_stat_product', table_name='price_statistic')
    op.drop_table('price_statistic')

    op.drop_index('idx_valor_estimate_created', table_name='valor_estimate')
    op.drop_index('ix_valor_estimate_valuation_id', table_name='valor_estimate')
    op.drop_table('valor_estimate')

    op.drop_index('idx_valor_model_active', table_name='valor_model')
    op.drop_table('valor_model')

    op.drop_index('idx_training_product_included', table_name='training_sample')
    op.drop_table('training_sample')

    op.drop_index('idx_obs_suspicious_product', table_name='price_observation')
    op.drop_index('idx_obs_product_observed', table_name='price_observation')
    op.drop_index('ix_price_observation_product_key', table_name='price_observation')
    op.drop_table('price_observation')

    op.drop_index('idx_agent_job_product_started', table_name='agent_job')
    op.drop_index('idx_agent_job_started', table_name='agent_job')
    op.drop_table('agent_job')
