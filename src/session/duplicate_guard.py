from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone


class DuplicateGuard:
    def __init__(self, window_seconds: int, max_items: int = 2048) -> None:
        self.window = timedelta(seconds=window_seconds)
        self.max_items = max_items
        self._seen: OrderedDict[tuple[int, str], datetime] = OrderedDict()

    def is_duplicate(self, camera_id: int, plate_number: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        key = (camera_id, plate_number)
        self._evict_old(now)

        last_seen = self._seen.get(key)
        self._seen[key] = now
        self._seen.move_to_end(key)
        while len(self._seen) > self.max_items:
            self._seen.popitem(last=False)

        return last_seen is not None and now - last_seen <= self.window

    def _evict_old(self, now: datetime) -> None:
        expired = [key for key, seen_at in self._seen.items() if now - seen_at > self.window]
        for key in expired:
            self._seen.pop(key, None)
