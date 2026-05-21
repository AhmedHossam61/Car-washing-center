from datetime import datetime, timedelta, timezone

from src.session.presence_tracker import PlateObservation, PresenceTracker


def observation(plate: str, digits: str, seen_at: datetime) -> PlateObservation:
    return PlateObservation(
        plate_number=plate,
        numeric_part=digits,
        seen_at=seen_at,
        confidence=0.8,
    )


def test_presence_tracker_infers_exit_after_absence_timeout() -> None:
    start = datetime(2026, 5, 21, tzinfo=timezone.utc)
    tracker = PresenceTracker(absence_timeout_seconds=120)

    tracker.update([observation("3327 HGJ", "3327", start)], start)
    tracker.update([observation("3327 HGJ", "3327", start + timedelta(seconds=60))], start + timedelta(seconds=60))
    tracker.advance(start + timedelta(seconds=181))

    session = tracker.sessions()[0]
    assert session.status == "completed"
    assert session.exit_time == start + timedelta(seconds=180)
    assert session.inferred_duration_seconds == 180
    assert session.visible_duration_seconds == 60
    assert session.observations == 2


def test_presence_tracker_groups_fuzzy_digit_reads() -> None:
    start = datetime(2026, 5, 21, tzinfo=timezone.utc)
    tracker = PresenceTracker(absence_timeout_seconds=120, fuzzy_threshold=1)

    tracker.update([observation("3327 HGJ", "3327", start)], start)
    tracker.update([observation("3337 HGJ", "3337", start + timedelta(seconds=20))], start + timedelta(seconds=20))

    sessions = tracker.sessions()
    assert len(sessions) == 1
    assert sessions[0].observations == 2


def test_presence_tracker_uses_stable_latin_letters_without_replacing_entry_plate() -> None:
    start = datetime(2026, 5, 21, tzinfo=timezone.utc)
    tracker = PresenceTracker(absence_timeout_seconds=120, fuzzy_threshold=1)

    tracker.update(
        [PlateObservation("9977 ZAD", start, 0.46, numeric_part="9977", latin_part="ZAD", arabic_part="اد")],
        start,
    )
    tracker.update(
        [
            PlateObservation(
                "1399 ZAD",
                start + timedelta(seconds=20),
                0.64,
                numeric_part="1399",
                latin_part="ZAD",
                arabic_part="اد",
            )
        ],
        start + timedelta(seconds=20),
    )

    session = tracker.sessions()[0]
    assert session.plate_number == "9977 ZAD"
    assert session.numeric_part == "9977"
    assert session.observations == 2
    assert session.confidence == 0.64


def test_presence_tracker_can_close_active_session_at_stream_end() -> None:
    start = datetime(2026, 5, 21, tzinfo=timezone.utc)
    tracker = PresenceTracker(absence_timeout_seconds=120)

    tracker.update([observation("3327 HGJ", "3327", start)], start)
    tracker.update([observation("3327 HGJ", "3327", start + timedelta(seconds=60))], start + timedelta(seconds=60))
    tracker.complete_active(start + timedelta(seconds=90))

    session = tracker.sessions()[0]
    assert session.status == "completed"
    assert session.exit_time == start + timedelta(seconds=90)
    assert session.inferred_duration_seconds == 90
    assert session.visible_duration_seconds == 60
    assert session.observations == 2


def test_presence_tracker_drains_completed_sessions_once() -> None:
    start = datetime(2026, 5, 21, tzinfo=timezone.utc)
    tracker = PresenceTracker(absence_timeout_seconds=30)

    tracker.update([observation("3327 HGJ", "3327", start)], start)
    tracker.advance(start + timedelta(seconds=31))

    assert len(tracker.drain_completed()) == 1
    assert tracker.drain_completed() == []
