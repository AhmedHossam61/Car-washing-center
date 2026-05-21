from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import cv2

from src.detection.ocr_engine import OCREngine
from src.detection.plate_detector import PlateDetector
from src.utils.image_utils import pad_bbox, preprocess_plate_crop_variants


@dataclass(frozen=True)
class PlateReadEvent:
    camera_id: int
    plate_number: str
    plate_raw: str
    confidence: float
    detected_at: datetime
    crop: Any
    arabic_part: str = ""
    numeric_part: str = ""
    latin_part: str = ""


class ALPRPipeline:
    def __init__(
        self,
        plate_detector: PlateDetector,
        ocr_engine: OCREngine,
        detect_width: int = 1920,
        preprocess_variant: str = "current_pipeline",
    ) -> None:
        self.plate_detector = plate_detector
        self.ocr_engine = ocr_engine
        self.detect_width = detect_width
        self.preprocess_variant = preprocess_variant

    def process_frame(self, *, camera_id: int, frame: Any, captured_at: datetime) -> list[PlateReadEvent]:
        events: list[PlateReadEvent] = []
        frame_h, frame_w = frame.shape[:2]

        # Downscale for YOLO only — shrinks the input tensor for high-res sources
        # (e.g. 4K) without discarding the original pixels needed for OCR quality.
        if frame_w > self.detect_width:
            scale = self.detect_width / frame_w
            detect_frame = cv2.resize(
                frame,
                (self.detect_width, int(frame_h * scale)),
                interpolation=cv2.INTER_LINEAR,
            )
            inv_scale = 1.0 / scale
        else:
            detect_frame = frame
            inv_scale = 1.0

        for detection in self.plate_detector.detect(detect_frame):
            x1, y1, x2, y2 = detection.bbox
            if inv_scale != 1.0:
                x1 = int(x1 * inv_scale)
                y1 = int(y1 * inv_scale)
                x2 = int(x2 * inv_scale)
                y2 = int(y2 * inv_scale)

            # Crop from the original high-res frame for best OCR quality.
            x1p, y1p, x2p, y2p = pad_bbox(x1, y1, x2, y2, frame_h=frame_h, frame_w=frame_w)
            raw_crop = frame[y1p:y2p, x1p:x2p]
            best_crop = None
            best_ocr = None
            for clean_crop in preprocess_plate_crop_variants(raw_crop, self.preprocess_variant).values():
                ocr = self.ocr_engine.read(clean_crop)
                if ocr is None:
                    continue
                if best_ocr is None or ocr.confidence > best_ocr.confidence:
                    best_ocr = ocr
                    best_crop = clean_crop

            if best_ocr is None or best_crop is None:
                continue
            events.append(
                PlateReadEvent(
                    camera_id=camera_id,
                    plate_number=best_ocr.normalized_text,
                    plate_raw=best_ocr.raw_text,
                    confidence=min(detection.confidence, best_ocr.confidence),
                    detected_at=captured_at,
                    crop=best_crop,
                    arabic_part=best_ocr.arabic_part,
                    numeric_part=best_ocr.numeric_part,
                    latin_part=best_ocr.latin_part,
                )
            )
        return events
