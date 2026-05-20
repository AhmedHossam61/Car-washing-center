from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from src.camera.frame_buffer import FrameBuffer, FrameItem
from src.config import CameraConfig


logger = logging.getLogger(__name__)


@dataclass
class CameraStatus:
    camera_id: int
    name: str
    role: str
    is_running: bool = False
    is_connected: bool = False
    last_frame_at: datetime | None = None
    last_error: str | None = None


class CameraStream(threading.Thread):
    def __init__(
        self,
        camera: CameraConfig,
        frame_buffer: FrameBuffer,
        *,
        process_every_n_frames: int = 5,
        reconnect_max_seconds: int = 60,
    ) -> None:
        super().__init__(name=f"camera-{camera.id}", daemon=True)
        self.camera = camera
        self.frame_buffer = frame_buffer
        self.process_every_n_frames = process_every_n_frames
        self.reconnect_max_seconds = reconnect_max_seconds
        self.status = CameraStatus(camera_id=camera.id, name=camera.name, role=camera.role)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        self.status.is_running = True
        retry_seconds = 2

        while not self._stop_event.is_set():
            cap = None
            try:
                import cv2

                cap = cv2.VideoCapture(self.camera.rtsp_url)
                if not cap.isOpened():
                    raise RuntimeError("unable to open RTSP stream")

                self.status.is_connected = True
                self.status.last_error = None
                retry_seconds = 2
                frame_count = 0

                while not self._stop_event.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        raise RuntimeError("failed to read frame")

                    captured_at = datetime.now(timezone.utc)
                    self.status.last_frame_at = captured_at
                    if frame_count % self.process_every_n_frames == 0:
                        self.frame_buffer.put_latest(FrameItem(self.camera.id, frame, captured_at))
                    frame_count += 1

            except Exception as exc:
                self.status.is_connected = False
                self.status.last_error = str(exc)
                logger.warning("camera %s stream error: %s", self.camera.id, exc)
                if self._stop_event.wait(retry_seconds):
                    break
                retry_seconds = min(retry_seconds * 2, self.reconnect_max_seconds)
            finally:
                if cap is not None:
                    cap.release()

        self.status.is_running = False
        self.status.is_connected = False
