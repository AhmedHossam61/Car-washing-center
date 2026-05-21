"""add last_seen_at to vehicle_sessions

Revision ID: 0002_add_last_seen_at
Revises: 0001_initial_schema
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_add_last_seen_at"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vehicle_sessions",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vehicle_sessions", "last_seen_at")
