from datetime import datetime, timezone

from src.reporting.google_sheets import SESSION_HEADERS, SheetSessionRow


def test_sheet_session_row_matches_session_columns() -> None:
    start = datetime(2026, 5, 21, 10, tzinfo=timezone.utc)
    row = SheetSessionRow(
        source="recorded_video",
        plate_number="9977 ZAD",
        numeric_part="9977",
        latin_part="ZAD",
        arabic_part="اد",
        entry_time=start,
        last_seen_at=start,
        exit_time=start,
        duration_seconds=40,
        visible_duration_seconds=0,
        status="completed",
        observations=3,
    )

    values = row.values()
    assert len(values) == len(SESSION_HEADERS)
    assert values[:5] == ["recorded_video", "9977 ZAD", "9977", "ZAD", "اد"]
    assert values[8:] == [40, 0, "completed", 3]
