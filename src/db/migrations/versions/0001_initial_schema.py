"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("rtsp_url", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('entry', 'exit', 'both')", name="ck_cameras_role"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "daily_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("total_vehicles", sa.Integer(), nullable=False),
        sa.Column("completed_sessions", sa.Integer(), nullable=False),
        sa.Column("avg_duration_seconds", sa.Float(), nullable=True),
        sa.Column("min_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("max_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("peak_hour", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stat_date"),
    )
    op.create_table(
        "vehicle_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plate_number", sa.String(length=50), nullable=False),
        sa.Column("plate_raw", sa.String(length=100), nullable=True),
        sa.Column("plate_confidence", sa.Float(), nullable=True),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("entry_camera_id", sa.Integer(), nullable=True),
        sa.Column("exit_camera_id", sa.Integer(), nullable=True),
        sa.Column("entry_snapshot_path", sa.Text(), nullable=True),
        sa.Column("exit_snapshot_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('active', 'completed', 'manual_close')", name="ck_sessions_status"),
        sa.ForeignKeyConstraint(["entry_camera_id"], ["cameras.id"]),
        sa.ForeignKeyConstraint(["exit_camera_id"], ["cameras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sessions_entry_time", "vehicle_sessions", ["entry_time"], unique=False)
    op.create_index("idx_sessions_plate", "vehicle_sessions", ["plate_number"], unique=False)
    op.create_index("idx_sessions_status", "vehicle_sessions", ["status"], unique=False)
    op.create_table(
        "detection_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("plate_number", sa.String(length=50), nullable=True),
        sa.Column("plate_raw", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("snapshot_path", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.CheckConstraint("event_type IN ('entry', 'exit', 'unknown')", name="ck_events_type"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["vehicle_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("detection_events")
    op.drop_index("idx_sessions_status", table_name="vehicle_sessions")
    op.drop_index("idx_sessions_plate", table_name="vehicle_sessions")
    op.drop_index("idx_sessions_entry_time", table_name="vehicle_sessions")
    op.drop_table("vehicle_sessions")
    op.drop_table("daily_stats")
    op.drop_table("cameras")
