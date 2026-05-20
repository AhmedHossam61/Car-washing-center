from src.utils.plate_normalizer import normalize_plate_text


def test_normalize_plate_text_removes_separators_and_converts_digits() -> None:
    assert normalize_plate_text(" أ ب ج - ١٢٣ ABC ") == "ابج123ABC"
