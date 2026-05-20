from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import CameraConfig
from src.db.models import Camera


class CameraRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self) -> list[Camera]:
        result = await self.session.execute(select(Camera).where(Camera.is_active.is_(True)).order_by(Camera.id))
        return list(result.scalars())

    async def get(self, camera_id: int) -> Camera | None:
        return await self.session.get(Camera, camera_id)

    async def upsert_from_config(self, config: CameraConfig) -> Camera:
        camera = await self.get(config.id)
        if camera is None:
            camera = Camera(id=config.id)
            self.session.add(camera)

        camera.name = config.name
        camera.rtsp_url = config.rtsp_url
        camera.role = config.role
        camera.location = config.location
        camera.is_active = config.is_active
        await self.session.flush()
        return camera
