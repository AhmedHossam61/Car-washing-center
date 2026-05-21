from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


CameraRole = Literal["entry", "exit", "both"]
OCRBackend = Literal["paddle", "easyocr"]
PreprocessVariant = Literal[
    "current_pipeline",
    "up2_clahe",
    "up2_sharp",
    "up3_clahe",
    "up3_sharp",
    "up2_adaptive",
    "up3_adaptive",
    "ocr_lab",
]


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
    ocr_use_gpu: bool = True
    # Primary OCR engine: "paddle" | "easyocr"
    ocr_backend: OCRBackend = "paddle"
    # Fallback engine when primary returns nothing (set to same value to disable fallback).
    ocr_fallback: OCRBackend = "easyocr"
    paddle_text_recognition_model_name: str = "PP-OCRv5_mobile_rec"
    duplicate_guard_seconds: int = 30
    process_every_n_frames: int = 5
    ai_worker_count: int = 1
    # Plate must appear in this many sampled frames (fuzzy-matched) before being recorded.
    min_confirmation_hits: int = 3
    # Max Levenshtein distance between digit strings to be treated as the same plate.
    confirmation_fuzzy_threshold: int = 2
    # Minutes of no detection before a single-camera ("both") session is auto-closed.
    presence_timeout_minutes: int = 1
    # Offline video tests can use a shorter timeout than the live camera worker.
    video_absence_timeout_seconds: int = 40
    yolo_plate_weights: Path = Path("./models/license_plate_yolov11.pt")
    # Controls both the YOLO inference size and the width the frame is downscaled
    # to before detection. The OCR crop is always taken from the original full-res frame.
    yolo_imgsz: int = 1920
    # Plate crop preprocessing mode before OCR.
    preprocess_variant: PreprocessVariant = "ocr_lab"

    snapshot_dir: Path = Path("./snapshots")
    report_dir: Path = Path("./reports")
    google_sheets_enabled: bool = False
    google_apps_script_url: str | None = None
    google_apps_script_token: str | None = None

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
