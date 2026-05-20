from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.event_repo import EventRepository
from src.db.repositories.session_repo import SessionRepository
from src.session.duplicate_guard import DuplicateGuard
from src.session.matcher import is_fuzzy_match


@dataclass(frozen=True)
class SessionEvent:
    event_type: str
    camera_id: int
    plate_number: str
    plate_raw: str
    confidence: float
    detected_at: datetime
    snapshot_path: str | None = None


class SessionManager:
    def __init__(self, db: AsyncSession, duplicate_guard: DuplicateGuard) -> None:
        self.db = db
        self.duplicate_guard = duplicate_guard
        self.sessions = SessionRepository(db)
        self.events = EventRepository(db)

    async def handle_entry(self, event: SessionEvent) -> None:
        if self.duplicate_guard.is_duplicate(event.camera_id, event.plate_number, event.detected_at):
            await self.events.create(**self._event_kwargs(event, event_type="entry", processed=True))
            return

        existing = await self.sessions.find_active_by_plate(event.plate_number)
        if existing is not None:
            await self.events.create(**self._event_kwargs(event, event_type="entry", session_id=existing.id, processed=True))
            return

        vehicle_session = await self.sessions.create_entry(
            plate_number=event.plate_number,
            plate_raw=event.plate_raw,
            plate_confidence=event.confidence,
            entry_time=event.detected_at,
            entry_camera_id=event.camera_id,
            entry_snapshot_path=event.snapshot_path,
        )
        await self.events.create(**self._event_kwargs(event, event_type="entry", session_id=vehicle_session.id, processed=True))

    async def handle_exit(self, event: SessionEvent) -> None:
        match = await self.sessions.find_active_by_plate(event.plate_number)
        if match is None:
            active_sessions = await self.sessions.list_active()
            match = next(
                (session for session in active_sessions if is_fuzzy_match(session.plate_number, event.plate_number)),
                None,
            )

        if match is None:
            await self.events.create(**self._event_kwargs(event, event_type="unknown", processed=False))
            return

        await self.sessions.close_session(
            match,
            exit_time=event.detected_at,
            exit_camera_id=event.camera_id,
            exit_snapshot_path=event.snapshot_path,
        )
        await self.events.create(**self._event_kwargs(event, event_type="exit", session_id=match.id, processed=True))

    def _event_kwargs(
        self,
        event: SessionEvent,
        *,
        event_type: str,
        session_id: int | None = None,
        processed: bool,
    ) -> dict[str, object]:
        return {
            "event_type": event_type,
            "camera_id": event.camera_id,
            "session_id": session_id,
            "plate_number": event.plate_number,
            "plate_raw": event.plate_raw,
            "confidence": event.confidence,
            "snapshot_path": event.snapshot_path,
            "detected_at": event.detected_at,
            "processed": processed,
        }
