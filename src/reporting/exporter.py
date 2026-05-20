from __future__ import annotations

from pathlib import Path

from src.reporting.generator import DailySummary


class ReportExporter:
    def __init__(self, report_dir: Path) -> None:
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def daily_summary_csv(self, summary: DailySummary) -> Path:
        path = self.report_dir / f"daily_summary_{summary.report_date.isoformat()}.csv"
        lines = [
            "field,value",
            f"report_date,{summary.report_date.isoformat()}",
            f"total_vehicles,{summary.total_vehicles}",
            f"completed_sessions,{summary.completed_sessions}",
            f"active_sessions,{summary.active_sessions}",
            f"avg_duration_seconds,{summary.avg_duration_seconds or ''}",
            f"min_duration_seconds,{summary.min_duration_seconds or ''}",
            f"max_duration_seconds,{summary.max_duration_seconds or ''}",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
