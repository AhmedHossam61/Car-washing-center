from __future__ import annotations

from src.camera.frame_buffer import FrameBuffer
from src.camera.stream import CameraStatus, CameraStream
from src.config import CameraConfig, Settings


class CameraManager:
    def __init__(self, settings: Settings, frame_buffer: FrameBuffer | None = None) -> None:
        self.settings = settings
        self.frame_buffer = frame_buffer or FrameBuffer()
        self._streams: dict[int, CameraStream] = {}

    def load_configured_cameras(self) -> list[CameraConfig]:
        return [camera for camera in self.settings.cameras_json if camera.is_active]

    def start_all(self) -> None:
        for camera in self.load_configured_cameras():
            if camera.id in self._streams and self._streams[camera.id].is_alive():
                continue
            stream = CameraStream(
                camera,
                self.frame_buffer,
                process_every_n_frames=self.settings.process_every_n_frames,
            )
            self._streams[camera.id] = stream
            stream.start()

    def stop_all(self) -> None:
        for stream in self._streams.values():
            stream.stop()
        for stream in self._streams.values():
            stream.join(timeout=5)

    def statuses(self) -> list[CameraStatus]:
        running = {camera_id: stream.status for camera_id, stream in self._streams.items()}
        statuses: list[CameraStatus] = []
        for camera in self.settings.cameras_json:
            statuses.append(
                running.get(
                    camera.id,
                    CameraStatus(
                        camera_id=camera.id,
                        name=camera.name,
                        role=camera.role,
                        is_running=False,
                        is_connected=False,
                    ),
                )
            )
        return statuses
