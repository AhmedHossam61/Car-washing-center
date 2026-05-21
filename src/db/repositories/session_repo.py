from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
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

    async def find_active_by_plate(self, plate_key: str) -> VehicleSession | None:
        """Find an active session whose plate_number contains plate_key.

        When plate_key is the digits-only portion (e.g. '3327'), this matches
        the canonical English-only plate form (e.g. '3327 HGJ') even if the
        OCR Latin suffix varies between reads.
        """
        result = await self.session.execute(
            select(VehicleSession)
            .where(
                VehicleSession.plate_number.contains(plate_key),
                VehicleSession.status == "active",
            )
            .order_by(VehicleSession.entry_time.desc())
        )
        return result.scalars().first()

    async def list_active(self) -> list[VehicleSession]:
        result = await self.session.execute(
            select(VehicleSession).where(VehicleSession.status == "active").order_by(VehicleSession.entry_time.desc())
        )
        return list(result.scalars())

    async def update_last_seen(self, vehicle_session: VehicleSession, seen_at: datetime) -> None:
        """Refresh the last_seen_at timestamp for a single-camera presence tracking."""
        vehicle_session.last_seen_at = seen_at
        await self.session.flush()

    async def find_timed_out_sessions(self, timeout_minutes: int) -> list[VehicleSession]:
        """Return active sessions whose last_seen_at (or entry_time) is older than timeout."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        result = await self.session.execute(
            select(VehicleSession)
            .where(
                VehicleSession.status == "active",
                # last_seen_at takes priority; fall back to entry_time for sessions
                # that were created before this column existed.
                func.coalesce(VehicleSession.last_seen_at, VehicleSession.entry_time) < cutoff,
            )
        )
        return list(result.scalars())

    async def list_all(
        self,
        *,
        status: str | None = None,
        plate: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VehicleSession]:
        query = select(VehicleSession).order_by(VehicleSession.entry_time.desc())
        if status is not None:
            query = query.where(VehicleSession.status == status)
        if plate is not None:
            query = query.where(VehicleSession.plate_number.ilike(f"%{plate}%"))
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars())

    async def get(self, session_id: int) -> VehicleSession | None:
        return await self.session.get(VehicleSession, session_id)

    async def manual_close(self, vehicle_session: VehicleSession) -> VehicleSession:
        now = datetime.now(timezone.utc)
        vehicle_session.exit_time = now
        vehicle_session.status = "manual_close"
        vehicle_session.updated_at = now

        def _naive(dt: datetime) -> datetime:
            return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

        vehicle_session.duration_seconds = int((_naive(now) - _naive(vehicle_session.entry_time)).total_seconds())
        await self.session.flush()
        return vehicle_session

    async def stats(self) -> dict[str, object]:
        total_result = await self.session.execute(select(func.count()).select_from(VehicleSession))
        total = total_result.scalar_one()

        active_result = await self.session.execute(
            select(func.count()).select_from(VehicleSession).where(VehicleSession.status == "active")
        )
        active = active_result.scalar_one()

        completed_result = await self.session.execute(
            select(func.count()).select_from(VehicleSession).where(VehicleSession.status == "completed")
        )
        completed = completed_result.scalar_one()

        duration_result = await self.session.execute(
            select(
                func.avg(VehicleSession.duration_seconds),
                func.min(VehicleSession.duration_seconds),
                func.max(VehicleSession.duration_seconds),
            ).where(VehicleSession.status == "completed")
        )
        avg_dur, min_dur, max_dur = duration_result.one()

        return {
            "total_vehicles": total,
            "active_sessions": active,
            "completed_sessions": completed,
            "avg_duration_seconds": float(avg_dur) if avg_dur is not None else None,
            "min_duration_seconds": int(min_dur) if min_dur is not None else None,
            "max_duration_seconds": int(max_dur) if max_dur is not None else None,
        }

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

        # For single-camera ("both") sessions the exit_time is set to
        # last_seen_at + presence_timeout, so it overshoots the real departure.
        # Use last_seen_at as the end of service when available — it is the
        # last moment the car was actually confirmed in frame.
        service_end = vehicle_session.last_seen_at or exit_time

        # Normalise both sides to UTC-naive so this works with both PostgreSQL
        # (tz-aware) and SQLite (naive).
        def _naive(dt: datetime) -> datetime:
            return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

        vehicle_session.duration_seconds = int((_naive(service_end) - _naive(vehicle_session.entry_time)).total_seconds())
        await self.session.flush()
        return vehicle_session
