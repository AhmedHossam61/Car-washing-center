from src.session.matcher import is_fuzzy_match, levenshtein_distance


def test_levenshtein_distance() -> None:
    assert levenshtein_distance("ABC123", "ABC124") == 1
    assert levenshtein_distance("ABC123", "XYZ123") == 3


def test_is_fuzzy_match() -> None:
    assert is_fuzzy_match("ABC123", "ABC124")
    assert not is_fuzzy_match("ABC123", "XYZ123")
