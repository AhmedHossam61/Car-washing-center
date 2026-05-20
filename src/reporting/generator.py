from __future__ import annotations

from dataclasses import dataclass
from datetime import date


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
    async def daily_summary(self, report_date: date) -> DailySummary:
        return DailySummary(
            report_date=report_date,
            total_vehicles=0,
            completed_sessions=0,
            active_sessions=0,
            avg_duration_seconds=None,
            min_duration_seconds=None,
            max_duration_seconds=None,
        )
