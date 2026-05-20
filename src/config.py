from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


CameraRole = Literal["entry", "exit", "both"]


class CameraConfig(BaseModel):
    id: int
    name: str
    rtsp_url: str
    role: CameraRole
    location: str | None = None
    is_active: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://carwash_user:change_me@localhost:5432/carwash"
    cameras_json: list[CameraConfig] = Field(default_factory=list, validation_alias="CAMERAS_JSON")

    plate_confidence: float = 0.5
    ocr_confidence: float = 0.70
    duplicate_guard_seconds: int = 30
    process_every_n_frames: int = 5
    ai_worker_count: int = 1
    yolo_plate_weights: Path = Path("./models/license_plate_yolov11.pt")

    snapshot_dir: Path = Path("./snapshots")
    report_dir: Path = Path("./reports")

    api_key: str | None = None
    api_port: int = 8000

    log_level: str = "INFO"
    log_file: Path = Path("./logs/carwash.log")

    @field_validator("cameras_json", mode="before")
    @classmethod
    def parse_cameras_json(cls, value: object) -> object:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return json.loads(value)
        return value

    @field_validator("process_every_n_frames", "ai_worker_count")
    @classmethod
    def must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("value must be >= 1")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
