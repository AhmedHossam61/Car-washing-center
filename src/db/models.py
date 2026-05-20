from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rtsp_url: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (CheckConstraint("role IN ('entry', 'exit', 'both')", name="ck_cameras_role"),)


class VehicleSession(Base):
    __tablename__ = "vehicle_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate_number: Mapped[str] = mapped_column(String(50), nullable=False)
    plate_raw: Mapped[Optional[str]] = mapped_column(String(100))
    plate_confidence: Mapped[Optional[float]] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    entry_camera_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cameras.id"))
    exit_camera_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cameras.id"))
    entry_snapshot_path: Mapped[Optional[str]] = mapped_column(Text)
    exit_snapshot_path: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    entry_camera: Mapped[Optional[Camera]] = relationship(foreign_keys=[entry_camera_id])
    exit_camera: Mapped[Optional[Camera]] = relationship(foreign_keys=[exit_camera_id])

    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'manual_close')", name="ck_sessions_status"),
        Index("idx_sessions_plate", "plate_number"),
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_entry_time", "entry_time"),
    )


class DetectionEvent(Base):
    __tablename__ = "detection_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cameras.id"))
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicle_sessions.id"))
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    plate_number: Mapped[Optional[str]] = mapped_column(String(50))
    plate_raw: Mapped[Optional[str]] = mapped_column(String(100))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    snapshot_path: Mapped[Optional[str]] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    camera: Mapped[Optional[Camera]] = relationship()
    session: Mapped[Optional[VehicleSession]] = relationship()

    __table_args__ = (CheckConstraint("event_type IN ('entry', 'exit', 'unknown')", name="ck_events_type"),)


class DailyStats(Base):
    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stat_date: Mapped[datetime] = mapped_column(Date, unique=True, nullable=False)
    total_vehicles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    min_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    max_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    peak_hour: Mapped[Optional[int]] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
