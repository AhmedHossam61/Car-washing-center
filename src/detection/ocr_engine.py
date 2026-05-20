from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.utils.plate_normalizer import normalize_plate_text


@dataclass(frozen=True)
class OCRResult:
    raw_text: str
    normalized_text: str
    confidence: float


class OCREngine:
    def __init__(self, confidence_threshold: float) -> None:
        self.confidence_threshold = confidence_threshold
        self._paddle: Any | None = None
        self._easyocr: Any | None = None

    def _load_paddle(self) -> Any:
        if self._paddle is None:
            from paddleocr import PaddleOCR

            self._paddle = PaddleOCR(use_angle_cls=True, lang="arabic", show_log=False)
        return self._paddle

    def _load_easyocr(self) -> Any:
        if self._easyocr is None:
            import easyocr

            self._easyocr = easyocr.Reader(["ar", "en"], gpu=False)
        return self._easyocr

    def read(self, image: Any) -> OCRResult | None:
        result = self._read_with_paddle(image)
        if result is None or result.confidence < self.confidence_threshold:
            result = self._read_with_easyocr(image)
        if result is None or result.confidence < self.confidence_threshold or len(result.normalized_text) < 3:
            return None
        return result

    def _read_with_paddle(self, image: Any) -> OCRResult | None:
        paddle = self._load_paddle()
        output = paddle.ocr(image, cls=True)
        texts: list[str] = []
        confidences: list[float] = []
        for page in output or []:
            for line in page or []:
                text, confidence = line[1]
                texts.append(text)
                confidences.append(float(confidence))
        return _combine_ocr(texts, confidences)

    def _read_with_easyocr(self, image: Any) -> OCRResult | None:
        reader = self._load_easyocr()
        output = reader.readtext(image)
        texts = [item[1] for item in output]
        confidences = [float(item[2]) for item in output]
        return _combine_ocr(texts, confidences)


def _combine_ocr(texts: list[str], confidences: list[float]) -> OCRResult | None:
    raw_text = "".join(texts).strip()
    if not raw_text:
        return None
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return OCRResult(raw_text=raw_text, normalized_text=normalize_plate_text(raw_text), confidence=confidence)
