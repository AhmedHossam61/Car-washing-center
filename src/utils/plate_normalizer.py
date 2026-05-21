from __future__ import annotations

import re
from dataclasses import dataclass


ARABIC_NORMALIZATION = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
    }
)

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Mapping from the Latin transliterations used by fast-alpr / Saudi DMV back
# to their Arabic Unicode equivalents.  Only the 17 letters that appear on
# Saudi plates are included; anything not in this dict is dropped.
ENG_TO_ARABIC: dict[str, str] = {
    "A": "ا",
    "B": "ب",
    "J": "ح",
    "D": "د",
    "R": "ر",
    "S": "س",
    "X": "ص",
    "T": "ط",
    "E": "ع",
    "G": "ق",
    "K": "ك",
    "L": "ل",
    "M": "م",
    "N": "ن",
    "H": "ه",
    "V": "و",
    "Y": "ى",
    "Z": "ز",
}


def latin_to_arabic(latin: str) -> str:
    """Convert Saudi plate Latin transliteration characters to Arabic letters.

    Only characters present in *ENG_TO_ARABIC* are mapped; the rest are
    silently ignored.  The returned string preserves the original order.
    """
    return "".join(ENG_TO_ARABIC[c] for c in latin.upper() if c in ENG_TO_ARABIC)


# Saudi plate bottom row: exactly 4 digits then exactly 3 Latin letters (e.g. "3327 HGJ")
_DIGITS_RE = re.compile(r"\d{3,4}")
_LATIN_RE = re.compile(r"[A-Z]{3}")
# Saudi plate top row: 1-3 Arabic letters
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]{1,3}")


@dataclass(frozen=True)
class ParsedPlate:
    arabic: str          # normalised Arabic letters from top row
    digits: str          # 3-4 digit sequence from bottom row
    latin: str           # 1-3 Latin letters from bottom row (may be empty)
    is_valid: bool       # True when both arabic and digits were found

    @property
    def canonical(self) -> str:
        """Canonical exported plate number: digits latin (e.g. '3327 HGJ')."""
        parts = [p for p in (self.digits, self.latin) if p]
        return " ".join(parts)


def normalize_plate_text(raw_text: str) -> str:
    text = raw_text.translate(ARABIC_NORMALIZATION).translate(ARABIC_DIGITS).upper()
    return re.sub(r"[^0-9A-Z\u0600-\u06FF]", "", text)


def parse_plate(arabic_raw: str, numeric_raw: str) -> ParsedPlate:
    """Extract and validate the structured fields from raw OCR outputs.

    Strips artefacts by applying strict regex patterns against the known
    Saudi plate format (top: 1-3 Arabic letters, bottom: 3-4 digits + 0-3 Latin).
    """
    # --- Arabic part (top half) ---
    arabic_norm = normalize_plate_text(arabic_raw)
    arabic_only = "".join(re.findall(r"[\u0600-\u06FF]", arabic_norm))
    arabic_match = _ARABIC_RE.search(arabic_only)
    arabic = arabic_match.group() if arabic_match else ""

    # --- Numeric part (bottom half) ---
    numeric_norm = normalize_plate_text(numeric_raw).upper()
    digits_match = _DIGITS_RE.search(numeric_norm)
    digits = digits_match.group() if digits_match else ""

    # Latin letters are on the right side of the bottom row (e.g. "1311 XCR").
    # OCR may read them before or after the digits depending on crop angle, so
    # we search after the digits first and fall back to before them.
    if digits_match:
        after_digits = numeric_norm[digits_match.end():]
        latin_match = _LATIN_RE.search(after_digits)
        if not latin_match:
            before_digits = numeric_norm[: digits_match.start()]
            latin_match = _LATIN_RE.search(before_digits)
        latin = latin_match.group() if latin_match else ""
    else:
        latin = ""

    # If no explicit arabic_raw was supplied, recover Arabic from the Latin
    # suffix letters (the standard Saudi DMV transliteration, e.g. "HGJ" →
    # "هقح").  Only suffix letters are used; prefix artefacts are excluded.
    if not arabic:
        arabic = latin_to_arabic(latin)

    # Both exactly-4 digits and exactly-3 Latin letters are required.
    is_valid = len(digits) == 4 and len(latin) == 3
    return ParsedPlate(arabic=arabic, digits=digits, latin=latin, is_valid=is_valid)
