from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Iterable
from urllib.request import Request, urlopen


SESSION_HEADERS = [
    "source",
    "plate_number",
    "numeric_part",
    "latin_part",
    "arabic_part",
    "entry_time",
    "last_seen",
    "exit_time",
    "duration_seconds",
    "visible_duration_seconds",
    "status",
    "observations",
]


@dataclass(frozen=True)
class GoogleSheetsConfig:
    apps_script_url: str
    token: str | None = None


@dataclass(frozen=True)
class SheetSessionRow:
    source: str
    plate_number: str
    entry_time: datetime
    last_seen_at: datetime | None
    exit_time: datetime | None
    duration_seconds: int | None
    visible_duration_seconds: int | None
    status: str
    numeric_part: str = ""
    latin_part: str = ""
    arabic_part: str = ""
    observations: int | None = None

    def values(self) -> list[Any]:
        return [
            self.source,
            self.plate_number,
            self.numeric_part,
            self.latin_part,
            self.arabic_part,
            _datetime_cell(self.entry_time),
            _datetime_cell(self.last_seen_at),
            _datetime_cell(self.exit_time),
            self.duration_seconds if self.duration_seconds is not None else "",
            self.visible_duration_seconds if self.visible_duration_seconds is not None else "",
            self.status,
            self.observations if self.observations is not None else "",
        ]


class GoogleSheetsSessionWriter:
    def __init__(self, config: GoogleSheetsConfig) -> None:
        self.config = config

    def append_sessions(self, rows: Iterable[SheetSessionRow]) -> int:
        row_list = list(rows)
        if not row_list:
            return 0
        body = {
            "token": self.config.token or "",
            "headers": SESSION_HEADERS,
            "rows": [row.values() for row in row_list],
        }
        request = Request(
            self.config.apps_script_url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            response.read()
        return len(row_list)


def session_writer_from_settings(settings: Any) -> GoogleSheetsSessionWriter | None:
    if not settings.google_sheets_enabled:
        return None
    if not settings.google_apps_script_url:
        raise ValueError("GOOGLE_APPS_SCRIPT_URL is required when Google Sheets output is enabled")
    return GoogleSheetsSessionWriter(
        GoogleSheetsConfig(
            apps_script_url=settings.google_apps_script_url,
            token=settings.google_apps_script_token,
        )
    )


def _datetime_cell(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""
