from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.session.matcher import levenshtein_distance


@dataclass(frozen=True)
class PlateObservation:
    plate_number: str
    seen_at: datetime
    confidence: float
    plate_raw: str = ""
    numeric_part: str = ""
    latin_part: str = ""
    arabic_part: str = ""

    @property
    def key(self) -> str:
        return self.numeric_part or self.plate_number


@dataclass
class PresenceSession:
    plate_key: str
    plate_number: str
    entry_time: datetime
    last_seen_at: datetime
    confidence: float
    plate_raw: str = ""
    numeric_part: str = ""
    latin_part: str = ""
    arabic_part: str = ""
    exit_time: datetime | None = None
    status: str = "active"
    observations: int = 1

    @property
    def inferred_duration_seconds(self) -> int | None:
        if self.exit_time is None:
            return None
        return max(0, int((self.exit_time - self.entry_time).total_seconds()))

    @property
    def visible_duration_seconds(self) -> int:
        return max(0, int((self.last_seen_at - self.entry_time).total_seconds()))

    def update(self, observation: PlateObservation) -> None:
        self.last_seen_at = max(self.last_seen_at, observation.seen_at)
        self.observations += 1
        self.confidence = max(self.confidence, observation.confidence)


class PresenceTracker:
    """Infer single-camera car sessions from confirmed plate observations."""

    def __init__(self, absence_timeout_seconds: int, fuzzy_threshold: int = 1) -> None:
        if absence_timeout_seconds < 1:
            raise ValueError("absence_timeout_seconds must be >= 1")
        self.absence_timeout = timedelta(seconds=absence_timeout_seconds)
        self.fuzzy_threshold = fuzzy_threshold
        self._active: list[PresenceSession] = []
        self._completed: list[PresenceSession] = []

    def update(self, observations: list[PlateObservation], now: datetime) -> None:
        self.advance(now)
        for observation in observations:
            session = self._find_active(observation)
            if session is None:
                self._active.append(
                    PresenceSession(
                        plate_key=observation.key,
                        plate_number=observation.plate_number,
                        plate_raw=observation.plate_raw,
                        entry_time=observation.seen_at,
                        last_seen_at=observation.seen_at,
                        confidence=observation.confidence,
                        numeric_part=observation.numeric_part,
                        latin_part=observation.latin_part,
                        arabic_part=observation.arabic_part,
                    )
                )
                continue
            session.update(observation)

    def advance(self, now: datetime) -> None:
        still_active: list[PresenceSession] = []
        for session in self._active:
            exit_time = session.last_seen_at + self.absence_timeout
            if exit_time <= now:
                session.exit_time = exit_time
                session.status = "completed"
                self._completed.append(session)
            else:
                still_active.append(session)
        self._active = still_active

    def sessions(self, video_end: datetime | None = None) -> list[PresenceSession]:
        if video_end is not None:
            self.advance(video_end)
        return [*self._completed, *self._active]

    def complete_active(self, now: datetime) -> None:
        """Close active sessions at a known stream boundary."""
        for session in self._active:
            session.exit_time = max(session.last_seen_at, now)
            session.status = "completed"
            self._completed.append(session)
        self._active = []

    def drain_completed(self) -> list[PresenceSession]:
        """Return completed sessions once, for streaming exporters."""
        completed = self._completed
        self._completed = []
        return completed

    def _find_active(self, observation: PlateObservation) -> PresenceSession | None:
        plate_key = observation.key
        if not plate_key:
            return None

        latin_match = self._find_unique_latin_match(observation.latin_part)
        if latin_match is not None:
            return latin_match

        closest: PresenceSession | None = None
        closest_distance = self.fuzzy_threshold + 1
        for session in self._active:
            distance = levenshtein_distance(session.plate_key, plate_key)
            if distance <= self.fuzzy_threshold and distance < closest_distance:
                closest = session
                closest_distance = distance
        return closest

    def _find_unique_latin_match(self, latin_part: str) -> PresenceSession | None:
        """Use stable Saudi-plate Latin letters when digit OCR is wobbling.

        OCR commonly mutates the four digits while keeping the three Latin
        letters stable.  A same-letter match is only trusted when it selects one
        active session; if two active cars share those letters, digit matching
        remains the tie-breaker.
        """
        if len(latin_part) != 3:
            return None
        matches = [session for session in self._active if session.latin_part == latin_part]
        return matches[0] if len(matches) == 1 else None
