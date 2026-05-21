from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.utils.plate_normalizer import parse_plate

logger = logging.getLogger(__name__)
_DLL_DIRECTORY_HANDLES: list[Any] = []


@dataclass(frozen=True)
class OCRResult:
    raw_text: str
    normalized_text: str
    confidence: float
    arabic_part: str = ""
    numeric_part: str = ""
    latin_part: str = ""


class OCREngine:
    """License-plate OCR with switchable backends.

    Supported backends
    ------------------
    ``paddle``  – PaddleOCR (recommended, best accuracy on Saudi plates)
    ``easyocr`` – EasyOCR  (good fallback, handles varied fonts)

    Set ``ocr_fallback`` to the same value as ``ocr_backend`` to disable fallback.
    """

    def __init__(
        self,
        confidence_threshold: float,
        use_gpu: bool = True,
        backend: str = "paddle",
        fallback: str = "easyocr",
        paddle_text_recognition_model_name: str = "PP-OCRv5_mobile_rec",
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.use_gpu = use_gpu
        self.backend = backend
        self.fallback = fallback
        self.paddle_text_recognition_model_name = paddle_text_recognition_model_name
        self._paddle: Any | None = None
        self._easyocr: Any | None = None

    # ------------------------------------------------------------------
    # Lazy model loaders
    # ------------------------------------------------------------------

    def _load_paddle(self) -> Any:
        if self._paddle is None:
            if self.use_gpu:
                _prepare_windows_paddle_gpu_dll_paths()
            from paddleocr import PaddleOCR

            self._paddle = PaddleOCR(
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name=self.paddle_text_recognition_model_name,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
                device="gpu:0" if self.use_gpu else "cpu",
            )
        return self._paddle

    def _load_easyocr(self) -> Any:
        if self._easyocr is None:
            import easyocr
            self._easyocr = easyocr.Reader(
                ["en"],
                gpu=self.use_gpu,
                verbose=False,
            )
        return self._easyocr

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self, image: Any) -> OCRResult | None:
        """Run primary backend; fall back if primary returns nothing."""
        result = self._run_backend(self.backend, image)
        if result is not None:
            return result
        if self.fallback != self.backend:
            result = self._run_backend(self.fallback, image)
        return result

    def _run_backend(self, name: str, image: Any) -> OCRResult | None:
        if name == "paddle":
            return self._read_with_paddle(image)
        if name == "easyocr":
            return self._read_with_easyocr(image)
        logger.warning("Unknown OCR backend %r — skipping.", name)
        return None

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def _read_with_paddle(self, image: Any) -> OCRResult | None:
        ocr = self._load_paddle()
        raw_result = ocr.predict(input=image)
        texts: list[str] = []
        confs: list[float] = []
        for result in raw_result or []:
            payload = _paddle_payload(result)
            texts.extend(str(text) for text in payload.get("rec_texts", []) if str(text).strip())
            confs.extend(float(confidence) for confidence in payload.get("rec_scores", []))

        raw_text = " ".join(texts).strip()
        confidence = sum(confs) / len(confs) if confs else 0.0

        if not raw_text or confidence < self.confidence_threshold:
            logger.debug("[PaddleOCR] rejected early: text=%r conf=%.3f threshold=%.3f", raw_text, confidence, self.confidence_threshold)
            return None

        parsed = parse_plate(arabic_raw="", numeric_raw=raw_text)
        logger.debug("[PaddleOCR] raw=%r → digits=%r latin=%r valid=%s conf=%.3f", raw_text, parsed.digits, parsed.latin, parsed.is_valid, confidence)
        if not parsed.is_valid:
            return None
        return OCRResult(
            raw_text=raw_text,
            normalized_text=parsed.canonical,
            confidence=confidence,
            arabic_part=parsed.arabic,
            numeric_part=parsed.digits,
            latin_part=parsed.latin,
        )
    def _read_with_easyocr(self, image: Any) -> OCRResult | None:
        reader = self._load_easyocr()
        results = reader.readtext(image, detail=1)
        if not results:
            return None

        texts: list[str] = []
        confs: list[float] = []
        for (_bbox, text, conf) in results:
            texts.append(text)
            confs.append(float(conf))

        raw_text = " ".join(texts).strip()
        confidence = sum(confs) / len(confs) if confs else 0.0

        if not raw_text or confidence < self.confidence_threshold:
            logger.debug("[EasyOCR  ] rejected early: text=%r conf=%.3f threshold=%.3f", raw_text, confidence, self.confidence_threshold)
            return None

        parsed = parse_plate(arabic_raw="", numeric_raw=raw_text)
        logger.debug("[EasyOCR  ] raw=%r → digits=%r latin=%r valid=%s conf=%.3f", raw_text, parsed.digits, parsed.latin, parsed.is_valid, confidence)
        if not parsed.is_valid:
            return None
        return OCRResult(
            raw_text=raw_text,
            normalized_text=parsed.canonical,
            confidence=confidence,
            arabic_part=parsed.arabic,
            numeric_part=parsed.digits,
            latin_part=parsed.latin,
        )


def _paddle_payload(result: Any) -> dict[str, Any]:
    data = getattr(result, "json", result)
    if callable(data):
        data = data()
    if not isinstance(data, dict):
        return {}
    payload = data.get("res", data)
    return payload if isinstance(payload, dict) else {}


def _prepare_windows_paddle_gpu_dll_paths() -> None:
    """Expose CUDA/cuDNN DLL folders installed by NVIDIA Python wheels."""
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return

    candidate_roots = [Path(path) / "nvidia" for path in sys.path if path]
    dll_dirs = (
        Path("cu13") / "bin" / "x86_64",
        Path("cudnn") / "bin",
    )
    for root in candidate_roots:
        for dll_dir in dll_dirs:
            path = root / dll_dir
            if path.is_dir():
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(path)))
