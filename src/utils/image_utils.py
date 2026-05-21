from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import cv2


# ---------------------------------------------------------------------------
# Plate crop pre-processing
# ---------------------------------------------------------------------------

_TARGET_HEIGHT = 256  # px — large enough so each character row is ~80 px for PaddleOCR
_PAD_FRACTION = 0.10  # 10 % padding on each side of the bbox


def preprocess_plate_crop(crop: Any) -> Any:
    """Return a cleaned-up BGR plate crop suitable for OCR.

    1. Upscale to at least _TARGET_HEIGHT with Lanczos (preserves fine strokes).
    2. Grayscale.
    3. Gentle CLAHE — normalises contrast without tile-boundary artefacts.
    4. Light unsharp mask — recovers motion blur without haloing.
    5. Back to BGR.

    NlMeans denoising was removed: on small crops it blurs character strokes
    more than it removes noise, consistently hurting PaddleOCR accuracy.
    """
    if crop is None or crop.size == 0:
        return crop

    # --- 1. Upscale ---
    h, w = crop.shape[:2]
    if h < _TARGET_HEIGHT:
        scale = _TARGET_HEIGHT / h
        new_w = max(1, int(w * scale))
        crop = cv2.resize(crop, (new_w, _TARGET_HEIGHT), interpolation=cv2.INTER_LANCZOS4)

    # --- 2. Grayscale ---
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # --- 3. CLAHE (larger tiles = less aggressive local adaptation) ---
    clahe_img = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(16, 16)).apply(gray)

    # --- 4. Unsharp mask ---
    blurred = cv2.GaussianBlur(clahe_img, (0, 0), 1.0)
    sharpened = cv2.addWeighted(clahe_img, 1.3, blurred, -0.3, 0)

    # --- 5. Back to BGR ---
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def preprocess_plate_crop_variant(crop: Any, variant: str = "current_pipeline") -> Any:
    """Apply a named preprocessing variant to a plate crop.

    Unknown variants fall back to ``current_pipeline`` for safety.
    """
    if crop is None or crop.size == 0:
        return crop

    if variant == "current_pipeline":
        return preprocess_plate_crop(crop)

    h, w = crop.shape[:2]
    if h == 0 or w == 0:
        return crop

    if variant.startswith("up3"):
        scale = 3.0
    else:
        scale = 2.0

    up = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(12, 12)).apply(gray)

    if variant.endswith("_clahe"):
        out = clahe
    elif variant.endswith("_sharp"):
        blur = cv2.GaussianBlur(clahe, (0, 0), 1.0)
        out = cv2.addWeighted(clahe, 1.45, blur, -0.45, 0)
    elif variant.endswith("_adaptive"):
        blur = cv2.GaussianBlur(clahe, (0, 0), 1.0)
        sharp = cv2.addWeighted(clahe, 1.45, blur, -0.45, 0)
        out = cv2.adaptiveThreshold(
            sharp,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            5,
        )
    else:
        out = preprocess_plate_crop(crop)
        return out

    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def preprocess_plate_crop_variants(crop: Any, variant: str = "current_pipeline") -> dict[str, Any]:
    """Return one or more OCR-ready crop variants.

    ``ocr_lab`` keeps the two crop-lab variants that have been selected for the
    runtime path and lets the main pipeline keep the best valid OCR read.
    """
    if variant != "ocr_lab":
        return {variant: preprocess_plate_crop_variant(crop, variant)}

    return {
        "up2_clahe": preprocess_plate_crop_variant(crop, "up2_clahe"),
        "up2_sharp": preprocess_plate_crop_variant(crop, "up2_sharp"),
    }


def pad_bbox(
    x1: int, y1: int, x2: int, y2: int,
    frame_h: int, frame_w: int,
    fraction: float = _PAD_FRACTION,
) -> tuple[int, int, int, int]:
    """Expand a bounding box by *fraction* on each side, clamped to frame bounds."""
    pw = int((x2 - x1) * fraction)
    ph = int((y2 - y1) * fraction)
    return (
        max(0, x1 - pw),
        max(0, y1 - ph),
        min(frame_w, x2 + pw),
        min(frame_h, y2 + ph),
    )


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
