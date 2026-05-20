from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DetectionEvent


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        event_type: str,
        camera_id: int | None,
        plate_number: str | None = None,
        plate_raw: str | None = None,
        confidence: float | None = None,
        snapshot_path: str | None = None,
        session_id: int | None = None,
        detected_at: datetime | None = None,
        processed: bool = False,
    ) -> DetectionEvent:
        event_data = {
            "event_type": event_type,
            "camera_id": camera_id,
            "session_id": session_id,
            "plate_number": plate_number,
            "plate_raw": plate_raw,
            "confidence": confidence,
            "snapshot_path": snapshot_path,
            "processed": processed,
        }
        if detected_at is not None:
            event_data["detected_at"] = detected_at

        event = DetectionEvent(
            **event_data,
        )
        self.session.add(event)
        await self.session.flush()
        return event
