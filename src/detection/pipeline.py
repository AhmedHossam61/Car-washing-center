from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.detection.ocr_engine import OCREngine
from src.detection.plate_detector import PlateDetector


@dataclass(frozen=True)
class PlateReadEvent:
    camera_id: int
    plate_number: str
    plate_raw: str
    confidence: float
    detected_at: datetime
    crop: Any


class ALPRPipeline:
    def __init__(self, plate_detector: PlateDetector, ocr_engine: OCREngine) -> None:
        self.plate_detector = plate_detector
        self.ocr_engine = ocr_engine

    def process_frame(self, *, camera_id: int, frame: Any, captured_at: datetime) -> list[PlateReadEvent]:
        events: list[PlateReadEvent] = []
        for detection in self.plate_detector.detect(frame):
            x1, y1, x2, y2 = detection.bbox
            crop = frame[y1:y2, x1:x2]
            ocr = self.ocr_engine.read(crop)
            if ocr is None:
                continue
            events.append(
                PlateReadEvent(
                    camera_id=camera_id,
                    plate_number=ocr.normalized_text,
                    plate_raw=ocr.raw_text,
                    confidence=min(detection.confidence, ocr.confidence),
                    detected_at=captured_at,
                    crop=crop,
                )
            )
        return events
