from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import VehicleSession


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_entry(
        self,
        *,
        plate_number: str,
        entry_time: datetime,
        entry_camera_id: int | None,
        plate_raw: str | None = None,
        plate_confidence: float | None = None,
        entry_snapshot_path: str | None = None,
    ) -> VehicleSession:
        vehicle_session = VehicleSession(
            plate_number=plate_number,
            plate_raw=plate_raw,
            plate_confidence=plate_confidence,
            entry_time=entry_time,
            entry_camera_id=entry_camera_id,
            entry_snapshot_path=entry_snapshot_path,
            status="active",
        )
        self.session.add(vehicle_session)
        await self.session.flush()
        return vehicle_session

    async def find_active_by_plate(self, plate_number: str) -> VehicleSession | None:
        result = await self.session.execute(
            select(VehicleSession)
            .where(VehicleSession.plate_number == plate_number, VehicleSession.status == "active")
            .order_by(VehicleSession.entry_time.desc())
        )
        return result.scalars().first()

    async def list_active(self) -> list[VehicleSession]:
        result = await self.session.execute(
            select(VehicleSession).where(VehicleSession.status == "active").order_by(VehicleSession.entry_time.desc())
        )
        return list(result.scalars())

    async def close_session(
        self,
        vehicle_session: VehicleSession,
        *,
        exit_time: datetime,
        exit_camera_id: int | None,
        exit_snapshot_path: str | None = None,
        status: str = "completed",
    ) -> VehicleSession:
        vehicle_session.exit_time = exit_time
        vehicle_session.exit_camera_id = exit_camera_id
        vehicle_session.exit_snapshot_path = exit_snapshot_path
        vehicle_session.status = status
        vehicle_session.updated_at = datetime.now(timezone.utc)
        vehicle_session.duration_seconds = int((exit_time - vehicle_session.entry_time).total_seconds())
        await self.session.flush()
        return vehicle_session
