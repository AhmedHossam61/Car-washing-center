from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from src.api.routers import cameras, health, reports, sessions
from src.camera.manager import CameraManager
from src.config import get_settings
from src.utils.logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)

    manager = CameraManager(settings)
    app.state.camera_manager = manager
    # Streams are configured but not auto-started until the camera credentials are real.
    yield
    manager.stop_all()


def create_app() -> FastAPI:
    app = FastAPI(title="Smart Car Wash Monitoring API", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(cameras.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    return app
