from datetime import datetime, timedelta, timezone

from src.session.duplicate_guard import DuplicateGuard


def test_duplicate_guard_window() -> None:
    guard = DuplicateGuard(window_seconds=30)
    now = datetime.now(timezone.utc)

    assert not guard.is_duplicate(1, "ABC123", now)
    assert guard.is_duplicate(1, "ABC123", now + timedelta(seconds=10))
    assert not guard.is_duplicate(1, "ABC123", now + timedelta(seconds=41))
