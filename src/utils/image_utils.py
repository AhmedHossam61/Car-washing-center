from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def snapshot_path(base_dir: Path, event_type: str, plate_number: str, detected_at: datetime) -> Path:
    safe_plate = "".join(char for char in plate_number if char.isalnum()) or "unknown"
    timestamp = detected_at.strftime("%Y%m%d_%H%M%S_%f")
    directory = base_dir / event_type
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{timestamp}_{safe_plate}.jpg"


def save_snapshot(image: Any, path: Path) -> Path:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)
    return path
