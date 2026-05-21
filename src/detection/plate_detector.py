from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PlateDetection:
    bbox: tuple[int, int, int, int]
    confidence: float


class PlateDetector:
    def __init__(self, weights_path: Path, confidence_threshold: float, imgsz: int = 1280) -> None:
        self.weights_path = weights_path
        self.confidence_threshold = confidence_threshold
        self.imgsz = imgsz
        self._model: Any | None = None

    def load(self) -> None:
        from ultralytics import YOLO

        self._model = YOLO(str(self.weights_path))

    def detect(self, frame: Any) -> list[PlateDetection]:
        if self._model is None:
            self.load()

        results = self._model.predict(frame, conf=self.confidence_threshold, imgsz=self.imgsz, verbose=False)
        detections: list[PlateDetection] = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
                confidence = float(box.conf[0])
                detections.append(PlateDetection((x1, y1, x2, y2), confidence))
        return detections
