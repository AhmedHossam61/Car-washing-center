from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from queue import Full, Queue
from typing import Any


@dataclass(frozen=True)
class FrameItem:
    camera_id: int
    frame: Any
    captured_at: datetime


class FrameBuffer:
    def __init__(self, max_size: int = 128) -> None:
        self._queue: Queue[FrameItem] = Queue(maxsize=max_size)

    def put_latest(self, item: FrameItem) -> None:
        try:
            self._queue.put_nowait(item)
        except Full:
            self._queue.get_nowait()
            self._queue.put_nowait(item)

    def get(self, timeout: float | None = None) -> FrameItem:
        return self._queue.get(timeout=timeout)

    def qsize(self) -> int:
        return self._queue.qsize()
