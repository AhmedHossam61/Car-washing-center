from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
