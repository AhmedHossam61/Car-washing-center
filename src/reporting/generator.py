from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import VehicleSession


@dataclass(frozen=True)
class DailySummary:
    report_date: date
    total_vehicles: int
    completed_sessions: int
    active_sessions: int
    avg_duration_seconds: float | None
    min_duration_seconds: int | None
    max_duration_seconds: int | None


class ReportGenerator:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def daily_summary(self, report_date: date) -> DailySummary:
        # Sessions whose entry_time falls on the requested date (UTC)
        day_start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=timezone.utc)
        day_end = datetime(report_date.year, report_date.month, report_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

        base = select(VehicleSession).where(
            VehicleSession.entry_time >= day_start,
            VehicleSession.entry_time <= day_end,
        )

        total_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total = total_result.scalar_one()

        completed_result = await self.db.execute(
            select(func.count()).select_from(
                base.where(VehicleSession.status == "completed").subquery()
            )
        )
        completed = completed_result.scalar_one()

        active_result = await self.db.execute(
            select(func.count()).select_from(
                base.where(VehicleSession.status == "active").subquery()
            )
        )
        active = active_result.scalar_one()

        dur_result = await self.db.execute(
            select(
                func.avg(VehicleSession.duration_seconds),
                func.min(VehicleSession.duration_seconds),
                func.max(VehicleSession.duration_seconds),
            ).where(
                VehicleSession.entry_time >= day_start,
                VehicleSession.entry_time <= day_end,
                VehicleSession.status == "completed",
            )
        )
        avg_dur, min_dur, max_dur = dur_result.one()

        return DailySummary(
            report_date=report_date,
            total_vehicles=total,
            completed_sessions=completed,
            active_sessions=active,
            avg_duration_seconds=float(avg_dur) if avg_dur is not None else None,
            min_duration_seconds=int(min_dur) if min_dur is not None else None,
            max_duration_seconds=int(max_dur) if max_dur is not None else None,
        )

