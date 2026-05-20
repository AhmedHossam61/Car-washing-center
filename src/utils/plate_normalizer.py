from __future__ import annotations

import re


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


def normalize_plate_text(raw_text: str) -> str:
    text = raw_text.translate(ARABIC_NORMALIZATION).translate(ARABIC_DIGITS).upper()
    return re.sub(r"[^0-9A-Z\u0600-\u06FF]", "", text)
