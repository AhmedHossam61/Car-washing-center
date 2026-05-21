from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import require_api_key
from src.config import get_settings
from src.db.connection import get_db_session
from src.reporting.exporter import ReportExporter
from src.reporting.generator import DailySummary, ReportGenerator


router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_api_key)])


@router.get("/daily", response_model=DailySummary)
async def daily_report(
    report_date: date = Query(default_factory=date.today, description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db_session),
) -> DailySummary:
    generator = ReportGenerator(db)
    return await generator.daily_summary(report_date)


@router.get("/daily/export")
async def daily_report_export(
    report_date: date = Query(default_factory=date.today, description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    settings = get_settings()
    generator = ReportGenerator(db)
    summary = await generator.daily_summary(report_date)
    exporter = ReportExporter(settings.report_dir)
    csv_path = exporter.daily_summary_csv(summary)
    return FileResponse(
        path=str(csv_path),
        media_type="text/csv",
        filename=csv_path.name,
    )

