from src.detection.ocr_engine import OCREngine, _paddle_payload


class PaddleResult:
    json = {"res": {"rec_texts": ["9977", "ZAD"], "rec_scores": [0.9, 0.8]}}


def test_paddle_payload_unwraps_v3_result_json() -> None:
    payload = _paddle_payload(PaddleResult())

    assert payload["rec_texts"] == ["9977", "ZAD"]
    assert payload["rec_scores"] == [0.9, 0.8]


def test_easyocr_backend_method_remains_available() -> None:
    assert hasattr(OCREngine, "_read_with_easyocr")
