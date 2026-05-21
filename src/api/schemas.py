from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


class HealthResponse(BaseModel):
    status: str
    database: str
    configured_cameras: int
    cameras: list["CameraHealth"]


class CameraHealth(BaseModel):
    id: int
    name: str
    role: str
    running: bool
    connected: bool
    last_frame_at: datetime | None = None
    last_error: str | None = None


# ---------------------------------------------------------------------------
# Session schemas
# ---------------------------------------------------------------------------


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate_number: str
    plate_raw: str | None
    plate_confidence: float | None
    entry_time: datetime
    exit_time: datetime | None
    duration_seconds: int | None
    status: str
    entry_camera_id: int | None
    exit_camera_id: int | None
    entry_snapshot_path: str | None
    exit_snapshot_path: str | None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_formatted(self) -> str | None:
        if self.duration_seconds is None:
            return None
        h, remainder = divmod(self.duration_seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


class SessionStatsResponse(BaseModel):
    total_vehicles: int
    active_sessions: int
    completed_sessions: int
    avg_duration_seconds: float | None
    min_duration_seconds: int | None
    max_duration_seconds: int | None


# ---------------------------------------------------------------------------
# Camera list schema
# ---------------------------------------------------------------------------


class CameraListResponse(BaseModel):
    id: int
    name: str
    role: str
    location: str | None
    is_active: bool
    running: bool
    connected: bool
    last_frame_at: datetime | None = None
    last_error: str | None = None
