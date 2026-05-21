from src.utils.plate_normalizer import normalize_plate_text, parse_plate


def test_normalize_plate_text_removes_separators_and_converts_digits() -> None:
    assert normalize_plate_text(" أ ب ج - ١٢٣ ABC ") == "ابج123ABC"


def test_canonical_plate_number_keeps_only_digits_and_latin_letters() -> None:
    parsed = parse_plate(arabic_raw="", numeric_raw="9977 ZAD")

    assert parsed.canonical == "9977 ZAD"
    assert parsed.arabic
